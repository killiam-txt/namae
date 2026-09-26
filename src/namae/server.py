import argparse
import asyncio
import logging
import time

from namae.client import DnsError, query_udp
from namae.message import Header, Message, Record

logger = logging.getLogger("namae.server")


class Cache:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, int, int], tuple[float, list[Record]]] = {}

    def get(self, name: str, qtype: int, qclass: int) -> list[Record] | None:
        key = (name.lower(), qtype, qclass)
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, records = entry
        if time.monotonic() >= expires_at:
            del self._entries[key]
            return None
        remaining = expires_at - time.monotonic()
        return [_with_ttl(record, remaining) for record in records]

    def set(self, name: str, qtype: int, qclass: int, records: list[Record]) -> None:
        if not records:
            return
        ttl = min(record.ttl for record in records)
        if ttl <= 0:
            return
        key = (name.lower(), qtype, qclass)
        self._entries[key] = (time.monotonic() + ttl, records)


def _with_ttl(record: Record, remaining: float) -> Record:
    return Record(record.name, record.rtype, max(0, int(remaining)), record.rdata, record.rclass)


class ForwardingProtocol(asyncio.DatagramProtocol):
    def __init__(
        self, upstream: str, upstream_port: int, timeout: float, cache: Cache
    ) -> None:
        self.upstream = upstream
        self.upstream_port = upstream_port
        self.timeout = timeout
        self.cache = cache
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        asyncio.ensure_future(self._handle(data, addr))

    async def _handle(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            query = Message.unpack(data)
        except ValueError:
            logger.warning("dropping malformed query from %s", addr)
            return

        if query.questions:
            question = query.questions[0]
            cached = self.cache.get(question.name, question.qtype, question.qclass)
            if cached is not None:
                assert self.transport is not None
                self.transport.sendto(_answer_response(query, cached).pack(), addr)
                return

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, self._resolve, query
            )
        except DnsError as exc:
            logger.warning("upstream failure for %s: %s", query.questions, exc)
            response = _error_response(query)
        else:
            if query.questions and response.answers:
                question = query.questions[0]
                self.cache.set(question.name, question.qtype, question.qclass, response.answers)

        assert self.transport is not None
        self.transport.sendto(response.pack(), addr)

    def _resolve(self, query: Message) -> Message:
        return query_udp(self.upstream, query, self.upstream_port, self.timeout)


def _answer_response(query: Message, answers: list[Record]) -> Message:
    header = Header(
        id=query.header.id,
        qr=True,
        rd=query.header.rd,
        ra=True,
        qdcount=len(query.questions),
        ancount=len(answers),
    )
    return Message(header, query.questions, answers, [], [])


def _error_response(query: Message) -> Message:
    header = Header(
        id=query.header.id,
        qr=True,
        rd=query.header.rd,
        ra=True,
        rcode=2,
        qdcount=len(query.questions),
    )
    return Message(header, query.questions, [], [], [])


async def serve(
    host: str = "127.0.0.1",
    port: int = 5353,
    upstream: str = "8.8.8.8",
    upstream_port: int = 53,
    timeout: float = 5.0,
) -> None:
    cache = Cache()
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: ForwardingProtocol(upstream, upstream_port, timeout, cache),
        local_addr=(host, port),
    )
    logger.info("listening on %s:%d, forwarding to %s:%d", host, port, upstream, upstream_port)
    try:
        await asyncio.Future()
    finally:
        transport.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="namae-server", description="DNS forwarding server")
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on")
    parser.add_argument("--port", type=int, default=5300, help="port to listen on")
    parser.add_argument("--upstream", default="8.8.8.8", help="upstream dns server")
    parser.add_argument("--upstream-port", type=int, default=53, help="upstream dns port")
    parser.add_argument("--timeout", type=float, default=5.0, help="upstream query timeout")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(
            serve(args.host, args.port, args.upstream, args.upstream_port, args.timeout)
        )
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())