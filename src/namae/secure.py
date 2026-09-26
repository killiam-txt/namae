import socket
import ssl
import struct
import urllib.error
import urllib.request

from namae.message import Message

DEFAULT_DOT_PORT = 853
DEFAULT_TIMEOUT = 5.0
DOH_CONTENT_TYPE = "application/dns-message"


class SecureDnsError(Exception):
    pass


def query_dot(
    server: str,
    message: Message,
    port: int = DEFAULT_DOT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> Message:
    payload = message.pack()
    framed = struct.pack("!H", len(payload)) + payload

    context = ssl.create_default_context()
    with socket.create_connection((server, port), timeout=timeout) as raw_sock:
        with context.wrap_socket(raw_sock, server_hostname=server) as sock:
            sock.sendall(framed)
            length_bytes = _recv_exact(sock, 2)
            (length,) = struct.unpack("!H", length_bytes)
            data = _recv_exact(sock, length)

    response = Message.unpack(data)
    if response.header.id != message.header.id:
        raise SecureDnsError(
            f"expected id {message.header.id}, got {response.header.id}"
        )
    return response


def _recv_exact(sock: ssl.SSLSocket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise SecureDnsError("connection closed before receiving full message")
        chunks += chunk
    return bytes(chunks)


def query_doh(
    url: str,
    message: Message,
    timeout: float = DEFAULT_TIMEOUT,
) -> Message:
    payload = message.pack()
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": DOH_CONTENT_TYPE,
            "Accept": DOH_CONTENT_TYPE,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if DOH_CONTENT_TYPE not in content_type:
                raise SecureDnsError(f"unexpected content-type: {content_type!r}")
            data = resp.read()
    except urllib.error.URLError as exc:
        raise SecureDnsError(f"doh request failed: {exc}") from exc

    response = Message.unpack(data)
    if response.header.id != message.header.id:
        raise SecureDnsError(
            f"expected id {message.header.id}, got {response.header.id}"
        )
    return response