import pytest

from namae.message import (
    HEADER_SIZE,
    Header,
    Question,
    RecordType,
    decode_name,
    encode_name,
)


def test_pack_standard_query():
    header = Header(id=0x1234, qdcount=1)
    assert header.pack() == bytes.fromhex("123401000001000000000000")


def test_unpack_response_flags():
    data = bytes.fromhex("123481800001000100000000")
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


def test_encode_name():
    assert encode_name("www.example.com") == b"\x03www\x07example\x03com\x00"


def test_encode_name_trailing_dot():
    assert encode_name("example.com.") == encode_name("example.com")


def test_encode_root():
    assert encode_name("") == b"\x00"
    assert encode_name(".") == b"\x00"


def test_encode_label_too_long():
    with pytest.raises(ValueError):
        encode_name("a" * 64 + ".com")


def test_encode_empty_label():
    with pytest.raises(ValueError):
        encode_name("example..com")


def test_decode_name():
    data = b"\x03www\x07example\x03com\x00"
    assert decode_name(data, 0) == ("www.example.com", len(data))


def test_decode_name_truncated():
    with pytest.raises(ValueError):
        decode_name(b"\x03ww", 0)


def test_decode_name_pointer_unsupported():
    with pytest.raises(ValueError):
        decode_name(b"\xc0\x0c", 0)


def test_question_pack():
    question = Question("example.com", RecordType.AAAA)
    assert question.pack() == b"\x07example\x03com\x00\x00\x1c\x00\x01"


def test_question_roundtrip_after_header():
    data = Header(id=1, qdcount=1).pack() + Question("example.com").pack()
    question, end = Question.unpack(data, HEADER_SIZE)
    assert question == Question("example.com", RecordType.A)
    assert end == len(data)


def test_question_too_short():
    with pytest.raises(ValueError):
        Question.unpack(b"\x03com\x00\x00", 0)