"""Record-level COMP-3 checks through parser + codec."""
import pytest

from kopybook import codec, parser
from kopybook.model import DecodeError


def _rec(pic):
    return parser.parse(f"       01  R.\n           05  A  PIC {pic} COMP-3.\n").record()


def test_unsigned_negative_sign_rejected_in_record():
    with pytest.raises(DecodeError):
        codec.decode(_rec("9(3)"), bytes.fromhex("123D"))


def test_signed_negative_sign_decodes_in_record():
    assert codec.decode(_rec("S9(3)"), bytes.fromhex("123D"))["a"] == -123


def test_too_many_digits_rejected_in_record():
    with pytest.raises(DecodeError):
        codec.decode(_rec("9(2)"), bytes.fromhex("123C"))
    with pytest.raises(DecodeError):
        codec.decode(_rec("S9(18)"), bytes.fromhex("9" * 19 + "C"))
