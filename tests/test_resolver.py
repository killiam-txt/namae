import pytest

import namae.resolver as resolver_module
from namae.message import Header, Message, Record, RecordType
from namae.resolver import ResolutionError, resolve_recursive

ROOT_IP = "198.41.0.4"
TLD_IP = "192.0.2.1"
AUTH_IP = "192.0.2.2"
TARGET_IP = "93.184.216.34"


def _referral(query, ns_name, ns_ip):
    ns_record = Record("com", RecordType.NS, 3600, ns_name)
    glue = Record(ns_name, RecordType.A, 3600, ns_ip)
    header = Header(id=query.header.id, qr=True, qdcount=1)
    return Message(header, query.questions, [], [ns_record], [glue])


def _answer(query):
    answer = Record(query.questions[0].name, RecordType.A, 300, TARGET_IP)
    header = Header(id=query.header.id, qr=True, qdcount=1, ancount=1)
    return Message(header, query.questions, [answer], [], [])


def fake_query_udp(server, query, port=53, timeout=5.0):
    if server == ROOT_IP:
        return _referral(query, "tld1.example-tld.net", TLD_IP)
    if server == TLD_IP:
        return _referral(query, "ns1.example.com", AUTH_IP)
    if server == AUTH_IP:
        return _answer(query)
    raise AssertionError(f"unexpected server {server}")


def test_resolve_recursive_follows_referrals(monkeypatch):
    monkeypatch.setattr(resolver_module, "ROOT_SERVERS", [ROOT_IP])
    monkeypatch.setattr(resolver_module, "query_udp", fake_query_udp)

    response = resolve_recursive("example.com")
    assert response.answers[0].rdata == TARGET_IP


def test_resolve_recursive_follows_cname(monkeypatch):
    def fake(server, query, port=53, timeout=5.0):
        name = query.questions[0].name
        if name == "www.example.com":
            cname = Record("www.example.com", RecordType.CNAME, 300, "example.com")
            header = Header(id=query.header.id, qr=True, qdcount=1, ancount=1)
            return Message(header, query.questions, [cname], [], [])
        if name == "example.com":
            return _answer(query)
        raise AssertionError(f"unexpected name {name}")

    monkeypatch.setattr(resolver_module, "ROOT_SERVERS", [ROOT_IP])
    monkeypatch.setattr(resolver_module, "query_udp", fake)

    response = resolve_recursive("www.example.com")
    assert response.answers[0].rdata == TARGET_IP


def test_resolve_recursive_gives_up_after_too_many_referrals(monkeypatch):
    def loop_query(server, query, port=53, timeout=5.0):
        return _referral(query, "ns1.example.com", "192.0.2.9")

    monkeypatch.setattr(resolver_module, "ROOT_SERVERS", [ROOT_IP])
    monkeypatch.setattr(resolver_module, "query_udp", loop_query)

    with pytest.raises(ResolutionError):
        resolve_recursive("example.com")


def test_resolve_recursive_no_response(monkeypatch):
    from namae.client import Timeout

    def failing_query(server, query, port=53, timeout=5.0):
        raise Timeout("no response")

    monkeypatch.setattr(resolver_module, "ROOT_SERVERS", [ROOT_IP])
    monkeypatch.setattr(resolver_module, "query_udp", failing_query)

    with pytest.raises(ResolutionError):
        resolve_recursive("example.com")