import random
import socket
import struct

from namae.message import Header, Message, Question, RecordType

DEFAULT_TIMEOUT = 5.0
DEFAULT_PORT = 53


class DnsError(Exception):
    pass


class Timeout(DnsError):
    pass


class IdMismatch(DnsError):
    pass


def build_query(name: str, qtype: int = RecordType.A) -> Message:
    header = Header(id=random.randint(0, 0xFFFF), rd=True, qdcount=1)
    return Message(header, [Question(name, qtype)], [], [], [])


def query_udp(
    server: str,
    message: Message,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> Message:
    payload = message.pack()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(payload, (server, port))
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout as exc:
            raise Timeout(f"no response from {server}:{port}") from exc
    response = Message.unpack(data)
    if response.header.id != message.header.id:
        raise IdMismatch(
            f"expected id {message.header.id}, got {response.header.id}"
        )
    return response


def query_tcp(
    server: str,
    message: Message,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> Message:
    payload = message.pack()
    framed = struct.pack("!H", len(payload)) + payload
    with socket.create_connection((server, port), timeout=timeout) as sock:
        sock.sendall(framed)
        length_bytes = _recv_exact(sock, 2)
        (length,) = struct.unpack("!H", length_bytes)
        data = _recv_exact(sock, length)
    response = Message.unpack(data)
    if response.header.id != message.header.id:
        raise IdMismatch(
            f"expected id {message.header.id}, got {response.header.id}"
        )
    return response


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise DnsError("connection closed before receiving full message")
        chunks += chunk
    return bytes(chunks)


def resolve(
    name: str,
    qtype: int = RecordType.A,
    server: str = "8.8.8.8",
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> Message:
    message = build_query(name, qtype)
    response = query_udp(server, message, port, timeout)
    if response.header.tc:
        response = query_tcp(server, message, port, timeout)
    return response