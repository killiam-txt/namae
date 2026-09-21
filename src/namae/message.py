import struct
from dataclasses import dataclass
from enum import IntEnum

HEADER_FORMAT = "!HHHHHH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
QUESTION_FORMAT = "!HH"
QUESTION_SIZE = struct.calcsize(QUESTION_FORMAT)
MAX_LABEL = 63
MAX_NAME = 255
CLASS_IN = 1


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