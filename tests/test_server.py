import asyncio
import socket

import pytest

from namae.message import Header, Message, Question, Record, RecordType
from namae.server import ForwardingProtocol, _error_response


def _upstream_response(query: Message) -> Message:
    question = query.questions[0]
    answer = Record(question.name, RecordType.A, 300, "93.184.216.34")
    header = Header(id=query.header.id, qr=True, ra=True, qdcount=1, ancount=1)
    return Message(header, [question], [answer], [], [])


def _run_fake_upstream(port_holder: list[int], stop: asyncio.Event) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(0.2)
    port_holder.append(sock.getsockname()[1])
    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        query = Message.unpack(data)
        sock.sendto(_upstream_response(query).pack(), addr)
    sock.close()


@pytest.mark.asyncio
async def test_server_forwards_and_responds():
    import threading

    stop = threading.Event()
    port_holder: list[int] = []
    thread = threading.Thread(target=_run_fake_upstream, args=(port_holder, stop), daemon=True)
    thread.start()
    while not port_holder:
        await asyncio.sleep(0.01)
    upstream_port = port_holder[0]

    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: ForwardingProtocol("127.0.0.1", upstream_port, 2.0),
        local_addr=("127.0.0.1", 0),
    )
    server_port = transport.get_extra_info("sockname")[1]

    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(2.0)
    query = Message(Header(id=99, qdcount=1), [Question("example.com")], [], [], [])
    client.sendto(query.pack(), ("127.0.0.1", server_port))
    data, _ = await loop.run_in_executor(None, client.recvfrom, 65535)
    response = Message.unpack(data)

    client.close()
    transport.close()
    stop.set()
    thread.join()

    assert response.header.id == 99
    assert response.answers[0].rdata == "93.184.216.34"


def test_error_response_sets_servfail():
    query = Message(Header(id=1, qdcount=1), [Question("example.com")], [], [], [])
    response = _error_response(query)
    assert response.header.rcode == 2
    assert response.header.qr is True
    assert response.answers == []