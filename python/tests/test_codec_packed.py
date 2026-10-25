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


def test_short_buffer_is_field_or_decode_error_not_index_error():
    from kopybook import fields as F
    with pytest.raises(F.FieldError):
        F.decode_packed(bytes.fromhex("12"), 3, 0, True)
    with pytest.raises(DecodeError):
        codec.decode(_rec("S9(3)"), bytes.fromhex("12"))


def test_field_errors_do_not_include_raw_bytes():
    from kopybook import fields as F
    for b, d, sg in [("987654321A5B", 11, True), ("987654321D", 9, False), ("987654321E3A", 11, True)]:
        with pytest.raises(F.FieldError) as e:
            F.decode_packed(bytes.fromhex(b), d, 0, sg)
        assert "98765" not in str(e.value).lower() and f"{len(b) // 2}-byte field" in str(e.value)
    with pytest.raises(F.FieldError) as e:
        F.decode_zoned(bytes.fromhex("F9F8F7F6F5FA"), 6, 0, False, False, False)
    assert "f9f8f7" not in str(e.value).lower()
    with pytest.raises(DecodeError) as e:
        codec.decode(_rec("S9(9)"), bytes.fromhex("98765432A5"))
    assert "offset 0" in str(e.value) and "98765" not in str(e.value)
