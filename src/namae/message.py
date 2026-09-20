import struct
from dataclasses import dataclass

HEADER_FORMAT = "!HHHHHH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


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