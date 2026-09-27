import random

from namae.client import DnsError, query_udp
from namae.message import Header, Message, Question, Record, RecordType

ROOT_SERVERS = [
    "198.41.0.4",
    "170.247.170.2",
    "192.33.4.12",
    "199.7.91.13",
    "192.203.230.10",
    "192.5.5.241",
    "192.112.36.4",
    "198.97.190.53",
    "192.36.148.17",
    "192.58.128.30",
    "193.0.14.129",
    "199.7.83.42",
    "202.12.27.33",
]

MAX_REFERRALS = 20
MAX_CNAME_CHAIN = 10


class ResolutionError(DnsError):
    pass


def _build_query(name: str, qtype: int) -> Message:
    header = Header(id=random.randint(0, 0xFFFF), rd=False, qdcount=1)
    return Message(header, [Question(name, qtype)], [], [], [])


def _query_one(server: str, name: str, qtype: int, timeout: float) -> Message:
    query = _build_query(name, qtype)
    return query_udp(server, query, timeout=timeout)


def _glue_addresses(response: Message, ns_names: set[str]) -> list[str]:
    addresses = []
    for record in response.additionals:
        if record.rtype == RecordType.A and record.name.lower() in ns_names:
            addresses.append(record.rdata)
    return addresses


def resolve_recursive(
    name: str,
    qtype: int = RecordType.A,
    timeout: float = 3.0,
) -> Message:
    servers = list(ROOT_SERVERS)
    current_name = name
    cname_hops = 0

    for _ in range(MAX_REFERRALS):
        response = None
        errors = []
        for server in servers:
            try:
                response = _query_one(server, current_name, qtype, timeout)
                break
            except DnsError as exc:
                errors.append(str(exc))
                continue
        if response is None:
            raise ResolutionError(f"no server responded for {current_name}: {errors}")

        direct = [a for a in response.answers if a.rtype == qtype]
        if direct:
            return response

        cnames = [a for a in response.answers if a.rtype == RecordType.CNAME]
        if cnames:
            cname_hops += 1
            if cname_hops > MAX_CNAME_CHAIN:
                raise ResolutionError("cname chain too long")
            current_name = cnames[0].rdata
            servers = list(ROOT_SERVERS)
            continue

        ns_records = [a for a in response.authorities if a.rtype == RecordType.NS]
        if not ns_records:
            return response

        ns_names = {r.rdata.lower() for r in ns_records}
        glue = _glue_addresses(response, ns_names)
        if glue:
            servers = glue
            continue

        resolved = []
        for ns_name in ns_names:
            try:
                ns_response = resolve_recursive(ns_name, RecordType.A, timeout)
            except ResolutionError:
                continue
            resolved += [a.rdata for a in ns_response.answers if a.rtype == RecordType.A]
        if not resolved:
            raise ResolutionError(f"could not resolve nameservers for {current_name}")
        servers = resolved

    raise ResolutionError(f"too many referrals resolving {name}")