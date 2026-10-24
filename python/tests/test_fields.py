"""Known-answer tests: byte patterns written by hand from IBM Enterprise COBOL rules."""
from decimal import Decimal as D

import pytest

from kopybook import fields as F

PACKED = [  # value, digits, scale, signed, hex
    (123, 3, 0, True, "123C"), (-123, 3, 0, True, "123D"), (123, 3, 0, False, "123F"),
    (1234, 4, 0, True, "01234C"), (-1, 1, 0, True, "1D"), (0, 5, 0, True, "00000C"),
    (D("-1234.50"), 9, 2, True, "000123450D"), (D("99999.99"), 7, 2, True, "9999999C"),
    (D("0.00001"), 5, 5, True, "00001C"),
    (10 ** 31 - 1, 31, 0, True, "9" * 31 + "C"),
]


@pytest.mark.parametrize("v,d,s,sg,hx", PACKED)
def test_packed_known(v, d, s, sg, hx):
    size = d // 2 + 1
    assert F.encode_packed(v, d, s, sg, size).hex().upper() == hx
    assert F.decode_packed(bytes.fromhex(hx), d, s, sg) == v


def test_packed_alt_signs():
    assert F.decode_packed(bytes.fromhex("123B"), 3, 0, True) == -123
    assert F.decode_packed(bytes.fromhex("123A"), 3, 0, True) == 123
    assert F.decode_packed(bytes.fromhex("123E"), 3, 0, True) == 123


@pytest.mark.parametrize("hx", ["1235", "1A3C", "F23C"])
def test_packed_invalid(hx):
    with pytest.raises(F.FieldError):
        F.decode_packed(bytes.fromhex(hx), 3, 0, True)


def test_packed_unsigned_rejects_negative_sign():
    for hx in ("123D", "123B"):
        with pytest.raises(F.FieldError):
            F.decode_packed(bytes.fromhex(hx), 3, 0, False)
    assert F.decode_packed(bytes.fromhex("123F"), 3, 0, False) == 123
    assert F.decode_packed(bytes.fromhex("123C"), 3, 0, False) == 123
    assert F.decode_packed(bytes.fromhex("123D"), 3, 0, True) == -123


def test_packed_empty():
    with pytest.raises(F.FieldError):
        F.decode_packed(b"", 1, 0, True)


def test_packed_negative_zero():
    assert F.decode_packed(bytes.fromhex("0D"), 1, 0, True) == 0


@pytest.mark.parametrize("hx,d", [
    ("123C", 2),            # PIC 9(2): spare leading nibble must be 0 (would give 123)
    ("9" * 39 + "C", 38),   # S9(38): 39 digits
    ("9" * 19 + "C", 18),   # S9(18): 19 digits
    ("00123C", 3),          # 3 bytes for 3 digits
    ("3C", 3),              # 1 byte for 3 digits
])
def test_packed_too_many_digits_or_wrong_length(hx, d):
    with pytest.raises(F.FieldError):
        F.decode_packed(bytes.fromhex(hx), d, 0, True)


def test_packed_even_digits_ok():
    assert F.decode_packed(bytes.fromhex("012F"), 2, 0, False) == 12
    assert F.decode_packed(bytes.fromhex("099D"), 2, 0, True) == -99
    assert F.decode_packed(bytes.fromhex("0" + "9" * 38 + "C"), 38, 0, True) == 10 ** 38 - 1


ZONED = [  # value, digits, scale, signed, leading, separate, hex
    (123, 3, 0, False, False, False, "F1F2F3"),
    (123, 3, 0, True, False, False, "F1F2C3"),
    (-123, 3, 0, True, False, False, "F1F2D3"),
    (-123, 3, 0, True, True, False, "D1F2F3"),
    (123, 3, 0, True, True, False, "C1F2F3"),
    (-123, 3, 0, True, False, True, "F1F2F360"),
    (123, 3, 0, True, True, True, "4EF1F2F3"),
    (D("-12.34"), 4, 2, True, False, False, "F1F2F3D4"),
    (0, 2, 0, True, False, False, "F0C0"),
]


@pytest.mark.parametrize("v,d,s,sg,ld,sep,hx", ZONED)
def test_zoned_known(v, d, s, sg, ld, sep, hx):
    assert F.encode_zoned(v, d, s, sg, ld, sep).hex().upper() == hx
    assert F.decode_zoned(bytes.fromhex(hx), d, s, sg, ld, sep) == v


def test_zoned_unsigned_accepts_c_zone_on_last_byte():
    assert F.decode_zoned(bytes.fromhex("F1F2C3"), 3, 0, False, False, False) == 123


@pytest.mark.parametrize("hx", ["F1FAF3", "40F2F3", "F1D2F3"])
def test_zoned_invalid(hx):
    with pytest.raises(F.FieldError):
        F.decode_zoned(bytes.fromhex(hx), 3, 0, False, False, False)


def test_zoned_bad_separate_sign():
    with pytest.raises(F.FieldError):
        F.decode_zoned(bytes.fromhex("F1F2F3F0"), 3, 0, True, False, True)


BINARY = [  # value, digits, signed, size, hex
    (-1, 4, True, 2, "FFFF"), (9999, 4, False, 2, "270F"), (123456789, 9, True, 4, "075BCD15"),
    (-2, 18, True, 8, "FFFFFFFFFFFFFFFE"),
]


@pytest.mark.parametrize("v,d,sg,sz,hx", BINARY)
def test_binary_known(v, d, sg, sz, hx):
    assert F.encode_binary(v, d, 0, sg, sz, True).hex().upper() == hx
    assert F.decode_binary(bytes.fromhex(hx), d, 0, sg, True) == v


def test_binary_trunc_std_vs_comp5():
    with pytest.raises(F.FieldError):
        F.decode_binary(bytes.fromhex("FFFF"), 4, 0, False, True)       # 65535 > PIC 9(4)
    assert F.decode_binary(bytes.fromhex("FFFF"), 4, 0, False, False) == 65535  # COMP-5


HFP = [(1.0, 4, "41100000"), (-118.625, 4, "C276A000"), (0.0, 4, "00000000"),
       (1.0, 8, "4110000000000000"), (0.5, 4, "40800000"), (256.0, 4, "43100000")]


@pytest.mark.parametrize("v,sz,hx", HFP)
def test_hfp_known(v, sz, hx):
    assert F.encode_hfp(v, sz).hex().upper() == hx
    assert F.decode_hfp(bytes.fromhex(hx)) == v


def test_hfp_unnormalised_decodes():
    assert F.decode_hfp(bytes.fromhex("42010000")) == 1.0


@pytest.mark.parametrize("cp,text,hx", [
    ("cp037", "A", "C1"), ("cp037", "a", "81"), ("cp037", "[", "BA"), ("cp500", "[", "4A"),
    ("cp037", "¢", "4A"), ("cp1140", "€", "9F"), ("cp037", "¤", "9F"), ("cp037", " ", "40"),
])
def test_codepages(cp, text, hx):
    assert F.encode_text(text, 1, cp).hex().upper() == hx
    assert F.decode_text(bytes.fromhex(hx), cp) == text.rstrip(" ")


def test_text_trim_modes():
    b = F.encode_text("  AB", 6, "cp037")
    assert F.decode_text(b, "cp037", "right") == "  AB"
    assert F.decode_text(b, "cp037", "both") == "AB"
    assert F.decode_text(b, "cp037", "none") == "  AB  "
