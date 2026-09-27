import argparse
import random
import sys

from namae.client import DnsError, resolve
from namae.message import Header, Message, Question, RecordType
from namae.resolver import ResolutionError, resolve_recursive
from namae.secure import SecureDnsError, query_doh, query_dot

TYPE_NAMES = {
    "A": RecordType.A,
    "AAAA": RecordType.AAAA,
    "CNAME": RecordType.CNAME,
    "MX": RecordType.MX,
    "NS": RecordType.NS,
    "TXT": RecordType.TXT,
}


def format_rdata(rtype: int, rdata) -> str:
    if rtype == RecordType.MX:
        preference, name = rdata
        return f"{preference} {name}"
    if rtype == RecordType.TXT:
        return " ".join(chunk.decode("ascii", errors="replace") for chunk in rdata)
    return str(rdata)


def _build_query(name: str, qtype: int) -> Message:
    header = Header(id=random.randint(0, 0xFFFF), rd=True, qdcount=1)
    return Message(header, [Question(name, qtype)], [], [], [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="namae", description="DNS resolver")
    parser.add_argument("name", help="domain name to resolve")
    parser.add_argument(
        "-t", "--type", default="A", type=str.upper, choices=sorted(TYPE_NAMES), help="record type"
    )
    parser.add_argument("-s", "--server", default="8.8.8.8", help="dns server")
    parser.add_argument("-p", "--port", type=int, default=53, help="dns server port")
    parser.add_argument("--timeout", type=float, default=5.0, help="query timeout in seconds")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="resolve recursively from root servers instead of using --server",
    )
    mode.add_argument(
        "--dot",
        action="store_true",
        help="query --server over DNS-over-TLS (port 853 unless --port is set)",
    )
    mode.add_argument(
        "--doh",
        metavar="URL",
        help="query a DNS-over-HTTPS endpoint, e.g. https://cloudflare-dns.com/dns-query",
    )
    args = parser.parse_args(argv)

    qtype = TYPE_NAMES[args.type]
    try:
        if args.recursive:
            response = resolve_recursive(args.name, qtype, args.timeout)
        elif args.dot:
            port = args.port if args.port != 53 else 853
            response = query_dot(args.server, _build_query(args.name, qtype), port, args.timeout)
        elif args.doh:
            response = query_doh(args.doh, _build_query(args.name, qtype), args.timeout)
        else:
            response = resolve(args.name, qtype, args.server, args.port, args.timeout)
    except (DnsError, ResolutionError, SecureDnsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not response.answers:
        print(f"no {args.type} records found for {args.name}")
        return 0

    for record in response.answers:
        print(f"{record.name}\t{record.ttl}\t{args.type}\t{format_rdata(record.rtype, record.rdata)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())