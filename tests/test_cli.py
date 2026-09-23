import pytest

from namae.__main__ import format_rdata, main
from namae.message import RecordType


def test_format_rdata_a():
    assert format_rdata(RecordType.A, "1.2.3.4") == "1.2.3.4"


def test_format_rdata_mx():
    assert format_rdata(RecordType.MX, (10, "mail.example.com")) == "10 mail.example.com"


def test_format_rdata_txt():
    assert format_rdata(RecordType.TXT, [b"v=spf1", b"-all"]) == "v=spf1 -all"


def test_main_requires_name():
    with pytest.raises(SystemExit):
        main([])


def test_main_rejects_bad_type():
    with pytest.raises(SystemExit):
        main(["example.com", "-t", "INVALID"])