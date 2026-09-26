import socket

import pytest

from namae.message import Header, Message, Question
from namae.secure import SecureDnsError, query_doh, query_dot


def _has_network() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 853), timeout=2.0).close()
        return True
    except OSError:
        return False


requires_network = pytest.mark.skipif(not _has_network(), reason="no network access")


@requires_network
def test_query_dot_against_cloudflare():
    query = Message(Header(id=1, qdcount=1), [Question("example.com")], [], [], [])
    response = query_dot("1.1.1.1", query, timeout=5.0)
    assert response.header.id == 1
    assert response.answers


def test_query_doh_content_type_rejected(monkeypatch):
    query = Message(Header(id=1, qdcount=1), [Question("example.com")], [], [], [])

    class FakeResponse:
        headers = {"Content-Type": "text/plain"}

        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(SecureDnsError):
        query_doh("https://example.invalid/dns-query", query)


def test_query_doh_roundtrip(monkeypatch):
    from namae.message import Record, RecordType

    query = Message(Header(id=3, qdcount=1), [Question("example.com")], [], [], [])
    answer = Record("example.com", RecordType.A, 300, "93.184.216.34")
    header = Header(id=3, qr=True, ra=True, qdcount=1, ancount=1)
    expected = Message(header, query.questions, [answer], [], []).pack()

    class FakeResponse:
        headers = {"Content-Type": "application/dns-message"}

        def read(self):
            return expected

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        assert request.get_header("Content-type") == "application/dns-message"
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    response = query_doh("https://example.invalid/dns-query", query)
    assert response.answers[0].rdata == "93.184.216.34"