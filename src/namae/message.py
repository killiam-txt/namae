import ipaddress
import struct
from dataclasses import dataclass
from enum import IntEnum

HEADER_FORMAT = "!HHHHHH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
QUESTION_FORMAT = "!HH"
QUESTION_SIZE = struct.calcsize(QUESTION_FORMAT)
RECORD_FORMAT = "!HHIH"
RECORD_SIZE = struct.calcsize(RECORD_FORMAT)
MAX_LABEL = 63
MAX_NAME = 255
CLASS_IN = 1

RData = str | tuple[int, str] | list[bytes] | bytes


class RecordType(IntEnum):
    A = 1
    NS = 2
    CNAME = 5
    MX = 15
    TXT = 16
    AAAA = 28


@dataclass
class Header:
    id: int
    qr: bool = False
    opcode: int = 0
    aa: bool = False
    tc: bool = False
    rd: bool = True
    ra: bool = False
    z: int = 0
    rcode: int = 0
    qdcount: int = 0
    ancount: int = 0
    nscount: int = 0
    arcount: int = 0

    def pack(self) -> bytes:
        flags = (
            (int(self.qr) << 15)
            | (self.opcode << 11)
            | (int(self.aa) << 10)
            | (int(self.tc) << 9)
            | (int(self.rd) << 8)
            | (int(self.ra) << 7)
            | (self.z << 4)
            | self.rcode
        )
        return struct.pack(
            HEADER_FORMAT,
            self.id,
            flags,
            self.qdcount,
            self.ancount,
            self.nscount,
            self.arcount,
        )

    @classmethod
    def unpack(cls, data: bytes) -> "Header":
        if len(data) < HEADER_SIZE:
            raise ValueError("header too short")
        id_, flags, qd, an, ns, ar = struct.unpack_from(HEADER_FORMAT, data)
        return cls(
            id=id_,
            qr=bool((flags >> 15) & 1),
            opcode=(flags >> 11) & 0xF,
            aa=bool((flags >> 10) & 1),
            tc=bool((flags >> 9) & 1),
            rd=bool((flags >> 8) & 1),
            ra=bool((flags >> 7) & 1),
            z=(flags >> 4) & 0x7,
            rcode=flags & 0xF,
            qdcount=qd,
            ancount=an,
            nscount=ns,
            arcount=ar,
        )


def encode_name(name: str) -> bytes:
    name = name.rstrip(".")
    if not name:
        return b"\x00"
    out = bytearray()
    for label in name.split("."):
        raw = label.encode("ascii")
        if not raw or len(raw) > MAX_LABEL:
            raise ValueError(f"invalid label: {label!r}")
        out.append(len(raw))
        out += raw
    out.append(0)
    if len(out) > MAX_NAME:
        raise ValueError("name too long")
    return bytes(out)


def decode_name(data: bytes, offset: int) -> tuple[str, int]:
    labels = []
    end = None
    seen = set()
    total = 1
    while True:
        if offset >= len(data):
            raise ValueError("truncated name")
        length = data[offset]
        if length & 0xC0 == 0xC0:
            if offset + 2 > len(data):
                raise ValueError("truncated pointer")
            target = ((length & 0x3F) << 8) | data[offset + 1]
            if end is None:
                end = offset + 2
            if target in seen:
                raise ValueError("compression loop")
            seen.add(target)
            offset = target
            continue
        if length & 0xC0:
            raise ValueError("invalid label type")
        offset += 1
        if length == 0:
            break
        total += length + 1
        if total > MAX_NAME:
            raise ValueError("name too long")
        label_end = offset + length
        if label_end > len(data):
            raise ValueError("truncated label")
        labels.append(data[offset:label_end].decode("ascii"))
        offset = label_end
    return ".".join(labels), end if end is not None else offset


@dataclass
class Question:
    name: str
    qtype: int = RecordType.A
    qclass: int = CLASS_IN

    def pack(self) -> bytes:
        return encode_name(self.name) + struct.pack(QUESTION_FORMAT, self.qtype, self.qclass)

    @classmethod
    def unpack(cls, data: bytes, offset: int) -> tuple["Question", int]:
        name, offset = decode_name(data, offset)
        if offset + QUESTION_SIZE > len(data):
            raise ValueError("question too short")
        qtype, qclass = struct.unpack_from(QUESTION_FORMAT, data, offset)
        return cls(name, qtype, qclass), offset + QUESTION_SIZE


def decode_rdata(rtype: int, data: bytes, offset: int, end: int) -> RData:
    if rtype == RecordType.A:
        if end - offset != 4:
            raise ValueError("invalid A rdata")
        return str(ipaddress.IPv4Address(data[offset:end]))
    if rtype == RecordType.AAAA:
        if end - offset != 16:
            raise ValueError("invalid AAAA rdata")
        return str(ipaddress.IPv6Address(data[offset:end]))
    if rtype in (RecordType.CNAME, RecordType.NS):
        name, after = decode_name(data, offset)
        if after > end:
            raise ValueError("name exceeds rdata")
        return name
    if rtype == RecordType.MX:
        if end - offset < 3:
            raise ValueError("invalid MX rdata")
        (preference,) = struct.unpack_from("!H", data, offset)
        name, after = decode_name(data, offset + 2)
        if after > end:
            raise ValueError("name exceeds rdata")
        return preference, name
    if rtype == RecordType.TXT:
        strings = []
        while offset < end:
            length = data[offset]
            offset += 1
            if offset + length > end:
                raise ValueError("truncated txt string")
            strings.append(data[offset : offset + length])
            offset += length
        return strings
    return data[offset:end]


def encode_rdata(rtype: int, rdata: RData) -> bytes:
    if rtype == RecordType.A:
        return ipaddress.IPv4Address(rdata).packed
    if rtype == RecordType.AAAA:
        return ipaddress.IPv6Address(rdata).packed
    if rtype in (RecordType.CNAME, RecordType.NS):
        return encode_name(rdata)
    if rtype == RecordType.MX:
        preference, name = rdata
        return struct.pack("!H", preference) + encode_name(name)
    if rtype == RecordType.TXT:
        out = bytearray()
        for chunk in rdata:
            if len(chunk) > 255:
                raise ValueError("txt string too long")
            out.append(len(chunk))
            out += chunk
        return bytes(out)
    return bytes(rdata)


@dataclass
class Record:
    name: str
    rtype: int
    ttl: int
    rdata: RData
    rclass: int = CLASS_IN

    def pack(self) -> bytes:
        payload = encode_rdata(self.rtype, self.rdata)
        return (
            encode_name(self.name)
            + struct.pack(RECORD_FORMAT, self.rtype, self.rclass, self.ttl, len(payload))
            + payload
        )

    @classmethod
    def unpack(cls, data: bytes, offset: int) -> tuple["Record", int]:
        name, offset = decode_name(data, offset)
        if offset + RECORD_SIZE > len(data):
            raise ValueError("record too short")
        rtype, rclass, ttl, rdlength = struct.unpack_from(RECORD_FORMAT, data, offset)
        offset += RECORD_SIZE
        end = offset + rdlength
        if end > len(data):
            raise ValueError("rdata too short")
        rdata = decode_rdata(rtype, data, offset, end)
        return cls(name, rtype, ttl, rdata, rclass), end


@dataclass
class Message:
    header: Header
    questions: list[Question]
    answers: list[Record]
    authorities: list[Record]
    additionals: list[Record]

    def pack(self) -> bytes:
        header = Header(
            id=self.header.id,
            qr=self.header.qr,
            opcode=self.header.opcode,
            aa=self.header.aa,
            tc=self.header.tc,
            rd=self.header.rd,
            ra=self.header.ra,
            z=self.header.z,
            rcode=self.header.rcode,
            qdcount=len(self.questions),
            ancount=len(self.answers),
            nscount=len(self.authorities),
            arcount=len(self.additionals),
        )
        out = bytearray(header.pack())
        for question in self.questions:
            out += question.pack()
        for record in self.answers + self.authorities + self.additionals:
            out += record.pack()
        return bytes(out)

    @classmethod
    def unpack(cls, data: bytes) -> "Message":
        header = Header.unpack(data)
        offset = HEADER_SIZE
        questions = []
        for _ in range(header.qdcount):
            question, offset = Question.unpack(data, offset)
            questions.append(question)
        answers, offset = _unpack_records(data, offset, header.ancount)
        authorities, offset = _unpack_records(data, offset, header.nscount)
        additionals, offset = _unpack_records(data, offset, header.arcount)
        return cls(header, questions, answers, authorities, additionals)


def _unpack_records(data: bytes, offset: int, count: int) -> tuple[list[Record], int]:
    records = []
    for _ in range(count):
        record, offset = Record.unpack(data, offset)
        records.append(record)
    return records, offset