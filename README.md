# namae (名前)

a DNS resolver: wire format, caching, DoT/DoH and full recursion, no external dependencies.

## install

```bash
git clone https://github.com/killiam-txt/namae
cd namae
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## usage

replace `example.com` with any domain you want to resolve.

```bash
namae example.com                          # resolve A record via 8.8.8.8
namae example.com -t MX                    # query a different record type
namae example.com -s 1.1.1.1               # use a different dns server
namae example.com -r                       # resolve recursively from root servers
namae example.com --dot -s 1.1.1.1         # dns over tls
namae example.com --doh <url>              # dns over https
python -m namae.server                     # run a forwarding server with ttl cache
```

namae parses and builds DNS messages byte by byte per RFC 1035, handles name compression pointers, and follows real referrals from the 13 root servers to resolve a domain without depending on any external resolver. it also implements DNS's own framing over TCP and TLS.

## development

```bash
pip install -e ".[dev]"
pytest
```

## structure

```
namae/
├── src/namae/
│   ├── __init__.py
│   ├── __main__.py     # cli entrypoint
│   ├── message.py      # wire format: header, name compression, records
│   ├── client.py       # udp/tcp client
│   ├── resolver.py     # recursive resolution from root servers
│   ├── secure.py       # dns over tls / https
│   └── server.py       # asyncio forwarding server with ttl cache
└── tests/
    ├── test_message.py
    ├── test_client.py
    ├── test_resolver.py
    ├── test_secure.py
    ├── test_server.py
    └── test_cli.py
```

## license

MIT