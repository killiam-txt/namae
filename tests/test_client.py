import socket
import struct
import threading

import pytest

from namae.client import DnsError, IdMismatch, Timeout, query_tcp, query_udp, resolve
from namae.message import Header, Message, Question, Record, RecordType


def _response_for(message: Message, tc: bool = False) -> Message:
    question = message.questions[0]
    answer = Record(question.name, RecordType.A, 300, "93.184.216.34")
    header = Header(id=message.header.id, qr=True, ra=True, tc=tc, qdcount=1, ancount=0 if tc else 1)
    return Message(header, [question], [] if tc else [answer], [], [])


def test_query_udp_roundtrip():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]

    def respond():
        data, addr = server.recvfrom(65535)
        message = Message.unpack(data)
        server.sendto(_response_for(message).pack(), addr)

    thread = threading.Thread(target=respond, daemon=True)
    thread.start()

    query = Message(Header(id=1, qdcount=1), [Question("example.com")], [], [], [])
    response = query_udp("127.0.0.1", query, port=port, timeout=2.0)

    thread.join()
    server.close()
    assert response.answers[0].rdata == "93.184.216.34"


def test_query_udp_timeout():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]

    query = Message(Header(id=1, qdcount=1), [Question("example.com")], [], [], [])
    with pytest.raises(Timeout):
        query_udp("127.0.0.1", query, port=port, timeout=0.2)

    server.close()


def test_query_udp_id_mismatch():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]

    def respond():
        data, addr = server.recvfrom(65535)
        message = Message.unpack(data)
        wrong = _response_for(message)
        wrong.header.id = message.header.id ^ 1
        server.sendto(wrong.pack(), addr)

    thread = threading.Thread(target=respond, daemon=True)
    thread.start()

    query = Message(Header(id=1, qdcount=1), [Question("example.com")], [], [], [])
    with pytest.raises(IdMismatch):
        query_udp("127.0.0.1", query, port=port, timeout=2.0)

    thread.join()
    server.close()


def test_query_tcp_roundtrip():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def respond():
        conn, _ = server.accept()
        with conn:
            length_bytes = conn.recv(2)
            (length,) = struct.unpack("!H", length_bytes)
            data = b""
            while len(data) < length:
                data += conn.recv(length - len(data))
            message = Message.unpack(data)
            payload = _response_for(message).pack()
            conn.sendall(struct.pack("!H", len(payload)) + payload)

    thread = threading.Thread(target=respond, daemon=True)
    thread.start()

    query = Message(Header(id=5, qdcount=1), [Question("example.com")], [], [], [])
    response = query_tcp("127.0.0.1", query, port=port, timeout=2.0)

    thread.join()
    server.close()
    assert response.answers[0].rdata == "93.184.216.34"


def test_resolve_falls_back_to_tcp_on_truncation():
    udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_server.bind(("127.0.0.1", 0))
    udp_port = udp_server.getsockname()[1]

    tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_server.bind(("127.0.0.1", udp_port))
    tcp_server.listen(1)

    def respond_udp():
        data, addr = udp_server.recvfrom(65535)
        message = Message.unpack(data)
        udp_server.sendto(_response_for(message, tc=True).pack(), addr)

    def respond_tcp():
        conn, _ = tcp_server.accept()
        with conn:
            length_bytes = conn.recv(2)
            (length,) = struct.unpack("!H", length_bytes)
            data = b""
            while len(data) < length:
                data += conn.recv(length - len(data))
            message = Message.unpack(data)
            payload = _response_for(message).pack()
            conn.sendall(struct.pack("!H", len(payload)) + payload)

    udp_thread = threading.Thread(target=respond_udp, daemon=True)
    tcp_thread = threading.Thread(target=respond_tcp, daemon=True)
    udp_thread.start()
    tcp_thread.start()

    response = resolve("example.com", server="127.0.0.1", port=udp_port, timeout=2.0)

    udp_thread.join()
    tcp_thread.join()
    udp_server.close()
    tcp_server.close()
    assert response.answers[0].rdata == "93.184.216.34"