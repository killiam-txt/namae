import pytest

from namae.message import HEADER_SIZE, Header


def test_pack_standard_query():
    header = Header(id=0x1234, qdcount=1)
    assert header.pack() == bytes.fromhex("123401000001000000000000")


def test_unpack_response_flags():
    data = bytes.fromhex("1234818000010001000000 00".replace(" ", ""))
    header = Header.unpack(data)
    assert header.qr is True
    assert header.rd is True
    assert header.ra is True
    assert header.rcode == 0
    assert header.qdcount == 1
    assert header.ancount == 1


def test_roundtrip():
    header = Header(id=7, qr=True, aa=True, tc=True, rcode=3, qdcount=1, arcount=2)
    assert Header.unpack(header.pack()) == header


def test_unpack_too_short():
    with pytest.raises(ValueError):
        Header.unpack(b"\x00" * (HEADER_SIZE - 1))