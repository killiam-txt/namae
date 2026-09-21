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


def test_decode_name_pointer_only():
    data = b"\x07example\x03com\x00\xc0\x00"
    assert decode_name(data, 13) == ("example.com", 15)


def test_decode_name_labels_then_pointer():
    data = b"\x07example\x03com\x00\x03www\xc0\x00"
    assert decode_name(data, 13) == ("www.example.com", len(data))


def test_decode_name_self_loop():
    with pytest.raises(ValueError):
        decode_name(b"\xc0\x00", 0)


def test_decode_name_mutual_loop():
    with pytest.raises(ValueError):
        decode_name(b"\xc0\x02\xc0\x00", 0)


def test_decode_name_pointer_out_of_range():
    with pytest.raises(ValueError):
        decode_name(b"\xc0\x10", 0)


def test_decode_name_truncated_pointer():
    with pytest.raises(ValueError):
        decode_name(b"\xc0", 0)


def test_decode_name_reserved_label_type():
    with pytest.raises(ValueError):
        decode_name(b"\x80\x00", 0)


def test_decode_name_max_length():
    data = (b"\x3f" + b"a" * 63) * 3 + b"\x3d" + b"a" * 61 + b"\x00"
    assert len(data) == 255
    name, end = decode_name(data, 0)
    assert end == 255
    assert len(name) == 253


def test_decode_name_too_long():
    data = (b"\x3f" + b"a" * 63) * 4 + b"\x01a\x00"
    with pytest.raises(ValueError):
        decode_name(data, 0)


def test_decode_name_too_long_via_pointers():
    label = b"\x3f" + b"a" * 63
    data = label * 2 + b"\x00" + label * 2 + b"\xc0\x00"
    with pytest.raises(ValueError):
        decode_name(data, 129)


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