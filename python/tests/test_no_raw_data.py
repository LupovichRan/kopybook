"""No field error may echo field data: raw bytes (hex, decimal or as a character) or values."""
import re
from decimal import Decimal

import pytest

from kopybook import codec, parser
from kopybook import fields as F
from kopybook.model import DecodeError


def _assert_no_raw(msg, data=b"", values=(), nibbles=""):
    low = msg.lower()
    for n in nibbles.lower():
        # a single offending nibble, e.g. the sign nibble "7" of 987657
        assert not re.search(f"(?<![0-9a-z]){n}(?![0-9a-z])", low), msg
    if data:
        assert data.hex() not in low, msg
    for x in data:
        # hex pair not inside an ordinary word ("ff" in "offset" is fine, "ff" or "f9f8" is not)
        assert not re.search(f"(?<![g-z]){x:02x}(?![g-z])", low), msg
        if x >= 100:
            assert str(x) not in msg, msg
        ch = bytes([x]).decode("cp037")
        if not ch.isalnum() and not ch.isspace():
            assert ch not in msg, msg
    for v in values:
        assert v not in msg, msg


H = bytes.fromhex

# (call, raw bytes fed in, decoded values that must not appear, offending nibbles)
DECODE = [
    ("packed digit nibble", lambda: F.decode_packed(H("98765A3C"), 7, 0, True), H("98765A3C"), ["98765"], "a"),
    ("packed too many digits", lambda: F.decode_packed(H("98765C"), 4, 0, True), H("98765C"), ["98765"], "9"),
    ("packed negative unsigned", lambda: F.decode_packed(H("98765D"), 5, 0, False), H("98765D"), ["98765"], "d"),
    ("packed sign nibble", lambda: F.decode_packed(H("987657"), 5, 0, True), H("987657"), ["98765"], "7"),
    ("separate sign", lambda: F.decode_zoned(H("F9F8F7F67B"), 4, 0, True, False, True), H("F9F8F7F67B"), ["9876"], ""),
    ("separate sign leading", lambda: F.decode_zoned(H("7BF9F8F7F6"), 4, 0, True, True, True), H("7BF9F8F7F6"), ["9876"], ""),
    ("zoned digit nibble", lambda: F.decode_zoned(H("F9F8F7F6FA"), 5, 0, False, False, False), H("F9F8F7F6FA"), ["9876"], "a"),
    ("zoned sign zone", lambda: F.decode_zoned(H("F9F8F7F679"), 5, 0, True, False, False), H("F9F8F7F679"), ["9876"], "7"),
    ("zoned zone nibble", lambda: F.decode_zoned(H("F939F7F6F5"), 5, 0, False, False, False), H("F939F7F6F5"), ["99765", "9765"], "3"),
    ("binary exceeds PIC", lambda: F.decode_binary(H("000181CD"), 4, 0, True, True), H("000181CD"), ["98765"], ""),
    ("text not valid", lambda: F.decode_text(H("C1FA"), "ascii"), H("C1FA"), [], ""),
]

ENCODE = [
    ("fraction", lambda: F.encode_zoned(Decimal("98765.5"), 9, 0, True, False, False), ["98765"]),
    ("too many decimals", lambda: F.encode_zoned(Decimal("9876.54321"), 9, 2, True, False, False), ["9876", "54321"]),
    ("packed negative unsigned", lambda: F.encode_packed(-98765, 5, 0, False, 3), ["98765"]),
    ("packed does not fit", lambda: F.encode_packed(987654, 5, 0, True, 3), ["98765"]),
    ("zoned negative unsigned", lambda: F.encode_zoned(-98765, 5, 0, False, False, False), ["98765"]),
    ("zoned does not fit", lambda: F.encode_zoned(987654, 5, 0, True, False, False), ["98765"]),
    ("binary does not fit digits", lambda: F.encode_binary(98765, 4, 0, True, 4, True), ["98765"]),
    ("binary does not fit bytes", lambda: F.encode_binary(98765, 9, 0, True, 2, False), ["98765"]),
    ("hfp out of range", lambda: F.encode_hfp(9.8765e300, 4), ["9.8765", "8765"]),
    ("hfp not exact", lambda: F.encode_hfp(0.98765, 4), ["98765"]),
    ("text too long", lambda: F.encode_text("SECRETMARKERXYZ", 4, "cp037"), ["SECRET", "MARKER"]),
    ("text not representable", lambda: F.encode_text("\u20acMARK", 10, "cp037"), ["\u20ac", "20ac", "MARK"]),
]


@pytest.mark.parametrize("name,call,data,values,nibbles", DECODE, ids=[c[0] for c in DECODE])
def test_decode_errors_have_no_raw_data(name, call, data, values, nibbles):
    with pytest.raises(F.FieldError) as e:
        call()
    _assert_no_raw(str(e.value), data, values, nibbles)
    assert "-byte field" in str(e.value)


@pytest.mark.parametrize("name,call,values", ENCODE, ids=[c[0] for c in ENCODE])
def test_encode_errors_have_no_raw_data(name, call, values):
    with pytest.raises(F.FieldError) as e:
        call()
    _assert_no_raw(str(e.value), values=values)


def test_record_level_binary_exceeds_has_no_value():
    root = parser.parse("       01  R.\n           05  A  PIC S9(4) COMP.\n").record()
    with pytest.raises(DecodeError) as e:
        codec.decode(root, H("7FFF"))
    assert "offset 0" in str(e.value) and "exceeds PIC" in str(e.value)
    _assert_no_raw(str(e.value), H("7FFF"), ["32767"])
