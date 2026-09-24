import argparse
import asyncio
import logging

from namae.client import DnsError, resolve
from namae.message import Header, Message

logger = logging.getLogger("namae.server")


class ForwardingProtocol(asyncio.DatagramProtocol):
    def __init__(self, upstream: str, upstream_port: int, timeout: float) -> None:
        self.upstream = upstream
        self.upstream_port = upstream_port
        self.timeout = timeout
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

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, self._resolve, query
            )
        except DnsError as exc:
            logger.warning("upstream failure for %s: %s", query.questions, exc)
            response = _error_response(query)

        assert self.transport is not None
        self.transport.sendto(response.pack(), addr)

    def _resolve(self, query: Message) -> Message:
        from namae.client import query_udp

        return query_udp(self.upstream, query, self.upstream_port, self.timeout)


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
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: ForwardingProtocol(upstream, upstream_port, timeout),
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
    parser.add_argument("--port", type=int, default=5353, help="port to listen on")
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