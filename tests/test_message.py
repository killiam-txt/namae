import pytest

from namae.message import (
    HEADER_SIZE,
    Header,
    Question,
    Record,
    Message,
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


def test_record_pack_a():
    record = Record("example.com", RecordType.A, 300, "93.184.216.34")
    expected = b"\x07example\x03com\x00" + bytes.fromhex("0001 0001 0000012c 0004 5db8d822")
    assert record.pack() == expected


@pytest.mark.parametrize(
    "record",
    [
        Record("example.com", RecordType.A, 300, "93.184.216.34"),
        Record("example.com", RecordType.AAAA, 60, "2001:db8::1"),
        Record("www.example.com", RecordType.CNAME, 60, "example.com"),
        Record("example.com", RecordType.NS, 3600, "ns1.example.com"),
        Record("example.com", RecordType.MX, 300, (10, "mail.example.com")),
        Record("example.com", RecordType.TXT, 120, [b"v=spf1 -all", b"hello"]),
        Record("example.com", 99, 5, b"\x01\x02\x03"),
    ],
)


def test_record_roundtrip(record):
    data = record.pack()
    parsed, end = Record.unpack(data, 0)
    assert parsed == record
    assert end == len(data)


def test_record_unpack_compressed_answer():
    question = Question("example.com").pack()
    answer = bytes.fromhex("c00c 0001 0001 0000012c 0004 5db8d822")
    data = Header(id=1, qr=True, qdcount=1, ancount=1).pack() + question + answer
    record, end = Record.unpack(data, HEADER_SIZE + len(question))
    assert record == Record("example.com", RecordType.A, 300, "93.184.216.34")
    assert end == len(data)


def test_record_unpack_cname_rdata_pointer():
    data = (
        b"\x07example\x03com\x00"
        + b"\x03www\xc0\x00"
        + bytes.fromhex("0005 0001 0000003c 0002 c000")
    )
    record, end = Record.unpack(data, 13)
    assert record == Record("www.example.com", RecordType.CNAME, 60, "example.com")
    assert end == len(data)


def test_record_too_short():
    data = Record("example.com", RecordType.A, 300, "1.2.3.4").pack()
    with pytest.raises(ValueError):
        Record.unpack(data[:-1], 0)


def test_record_invalid_a_length():
    data = b"\x00" + bytes.fromhex("0001 0001 00000000 0003 010203")
    with pytest.raises(ValueError):
        Record.unpack(data, 0)


def test_record_name_exceeds_rdata():
    data = b"\x00" + bytes.fromhex("0005 0001 00000000 0001") + b"\x01a\x00"
    with pytest.raises(ValueError):
        Record.unpack(data, 0)


def test_record_txt_truncated_string():
    data = b"\x00" + bytes.fromhex("0010 0001 00000000 0003") + b"\x05ab"
    with pytest.raises(ValueError):
        Record.unpack(data, 0)


def test_message_pack_fixes_counts():
    header = Header(id=1, qdcount=99, ancount=99)
    message = Message(header, [Question("example.com")], [], [], [])
    parsed = Message.unpack(message.pack())
    assert parsed.header.qdcount == 1
    assert parsed.header.ancount == 0


def test_message_roundtrip_query():
    message = Message(Header(id=42, qdcount=1), [Question("example.com")], [], [], [])
    parsed = Message.unpack(message.pack())
    assert parsed.header.id == 42
    assert parsed.questions == [Question("example.com")]
    assert parsed.answers == []


def test_message_roundtrip_response():
    question = Question("example.com")
    answer = Record("example.com", RecordType.A, 300, "93.184.216.34")
    header = Header(id=42, qr=True, ra=True, qdcount=1, ancount=1)
    message = Message(header, [question], [answer], [], [])
    parsed = Message.unpack(message.pack())
    assert parsed.header.qr is True
    assert parsed.questions == [question]
    assert parsed.answers == [answer]


def test_message_multiple_questions_and_answers():
    questions = [Question("example.com"), Question("example.org")]
    answers = [
        Record("example.com", RecordType.A, 300, "93.184.216.34"),
        Record("example.org", RecordType.A, 60, "1.2.3.4"),
    ]
    header = Header(id=1, qr=True, qdcount=2, ancount=2)
    message = Message(header, questions, answers, [], [])
    parsed = Message.unpack(message.pack())
    assert parsed.questions == questions
    assert parsed.answers == answers


def test_message_with_authority_and_additional():
    header = Header(id=1, qr=True, qdcount=0, nscount=1, arcount=1)
    authority = Record("example.com", RecordType.NS, 3600, "ns1.example.com")
    additional = Record("ns1.example.com", RecordType.A, 3600, "192.0.2.1")
    message = Message(header, [], [], [authority], [additional])
    parsed = Message.unpack(message.pack())
    assert parsed.authorities == [authority]
    assert parsed.additionals == [additional]


def test_message_truncated():
    data = Header(id=1, qdcount=1).pack()
    with pytest.raises(ValueError):
        Message.unpack(data)