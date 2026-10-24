"""Byte-level codecs for elementary COBOL items (IBM Enterprise COBOL semantics)."""
from __future__ import annotations

import math
import struct
from decimal import Context, Decimal

_CTX = Context(prec=100)
from typing import Union

Number = Union[int, Decimal]

EBCDIC_PLUS = 0x4E
EBCDIC_MINUS = 0x60
POS_ZONES = (0xC, 0xF, 0xA, 0xE)
NEG_ZONES = (0xD, 0xB)


class FieldError(ValueError):
    pass


def _scaled(unscaled: int, scale: int) -> Number:
    if scale == 0:
        return unscaled
    return Decimal(unscaled).scaleb(-scale, _CTX)


def _unscaled(value: Number, scale: int) -> int:
    if scale == 0:
        if isinstance(value, Decimal):
            if value != value.to_integral_value():
                raise FieldError(f"{value} has a fraction but field has no decimals")
            return int(value)
        return int(value)
    d = Decimal(value).scaleb(scale, _CTX)
    if d != d.to_integral_value():
        raise FieldError(f"{value} has more than {scale} decimals")
    return int(d)


# ---------------------------------------------------------------- packed (COMP-3)

def decode_packed(b: bytes, digits: int, scale: int, signed: bool) -> Number:
    if not b:
        raise FieldError("empty packed field")
    if len(b) != digits // 2 + 1:
        raise FieldError(f"packed field of {digits} digits must be {digits // 2 + 1} bytes, got {len(b)}")
    nibbles = []
    for x in b:
        nibbles.append(x >> 4)
        nibbles.append(x & 0xF)
    sign = nibbles.pop()
    for d in nibbles:
        if d > 9:
            raise FieldError(f"invalid packed digit nibble {d:X} in {b.hex()}")
    if len(nibbles) > digits and nibbles[0] != 0:
        raise FieldError(f"packed value in {b.hex()} has more than {digits} digits")
    if sign in NEG_ZONES:
        if not signed:
            raise FieldError(f"negative packed sign nibble {sign:X} in unsigned field {b.hex()}")
        neg = True
    elif sign in POS_ZONES:
        neg = False
    else:
        raise FieldError(f"invalid packed sign nibble {sign:X} in {b.hex()}")
    v = 0
    for d in nibbles:
        v = v * 10 + d
    if neg:
        v = -v
    return _scaled(v, scale)


def encode_packed(value: Number, digits: int, scale: int, signed: bool, size: int) -> bytes:
    u = _unscaled(value, scale)
    if u < 0 and not signed:
        raise FieldError(f"negative value {value} for unsigned field")
    if abs(u) >= 10 ** digits:
        raise FieldError(f"{value} does not fit {digits} digits")
    s = str(abs(u)).rjust(size * 2 - 1, "0")
    sign = 0xF if not signed else (0xD if u < 0 else 0xC)
    nib = [int(c) for c in s] + [sign]
    return bytes((nib[i] << 4) | nib[i + 1] for i in range(0, len(nib), 2))


# ---------------------------------------------------------------- zoned (DISPLAY)

def decode_zoned(b: bytes, digits: int, scale: int, signed: bool,
                 leading: bool, separate: bool) -> Number:
    neg = False
    if signed and separate:
        sc = b[0] if leading else b[-1]
        body = b[1:] if leading else b[:-1]
        if sc == EBCDIC_MINUS:
            neg = True
        elif sc != EBCDIC_PLUS:
            raise FieldError(f"invalid separate sign byte {sc:02X}")
    else:
        body = b
    v = 0
    n = len(body)
    for i, x in enumerate(body):
        zone, d = x >> 4, x & 0xF
        sign_pos = (i == 0) if leading else (i == n - 1)
        if d > 9:
            raise FieldError(f"invalid zoned digit {x:02X} in {b.hex()}")
        if signed and not separate and sign_pos:
            if zone in NEG_ZONES:
                neg = True
            elif zone not in POS_ZONES:
                raise FieldError(f"invalid zoned sign {x:02X} in {b.hex()}")
        elif zone != 0xF:
            # unsigned fields written by some tools carry C zone on the last byte
            if not (sign_pos and zone in POS_ZONES):
                raise FieldError(f"invalid zoned byte {x:02X} in {b.hex()}")
        v = v * 10 + d
    return _scaled(-v if neg else v, scale)


def encode_zoned(value: Number, digits: int, scale: int, signed: bool,
                 leading: bool, separate: bool) -> bytes:
    u = _unscaled(value, scale)
    if u < 0 and not signed:
        raise FieldError(f"negative value {value} for unsigned field")
    if abs(u) >= 10 ** digits:
        raise FieldError(f"{value} does not fit {digits} digits")
    body = bytearray(0xF0 | int(c) for c in str(abs(u)).rjust(digits, "0"))
    if signed and separate:
        sc = EBCDIC_MINUS if u < 0 else EBCDIC_PLUS
        return bytes([sc]) + bytes(body) if leading else bytes(body) + bytes([sc])
    if signed:
        idx = 0 if leading else len(body) - 1
        zone = 0xD0 if u < 0 else 0xC0
        body[idx] = zone | (body[idx] & 0xF)
    return bytes(body)


# ---------------------------------------------------------------- binary

def decode_binary(b: bytes, digits: int, scale: int, signed: bool, truncate_to_pic: bool) -> Number:
    v = int.from_bytes(b, "big", signed=signed)
    if truncate_to_pic and abs(v) >= 10 ** digits:
        raise FieldError(f"binary value {v} exceeds PIC digits ({digits}); use COMP-5 or trunc=bin")
    return _scaled(v, scale)


def encode_binary(value: Number, digits: int, scale: int, signed: bool, size: int,
                  truncate_to_pic: bool) -> bytes:
    u = _unscaled(value, scale)
    if truncate_to_pic and abs(u) >= 10 ** digits:
        raise FieldError(f"{value} does not fit {digits} digits")
    try:
        return u.to_bytes(size, "big", signed=signed)
    except OverflowError:
        raise FieldError(f"{value} does not fit {size} bytes")


# ---------------------------------------------------------------- IBM hex float

def decode_hfp(b: bytes) -> float:
    n = len(b)
    word = int.from_bytes(b, "big")
    frac_bits = n * 8 - 8
    sign = word >> (n * 8 - 1)
    exp = (word >> frac_bits) & 0x7F
    frac = word & ((1 << frac_bits) - 1)
    if frac == 0:
        return -0.0 if sign else 0.0
    v = math.ldexp(frac, 4 * (exp - 64) - frac_bits)
    return -v if sign else v


def encode_hfp(value: float, size: int) -> bytes:
    frac_bits = size * 8 - 8
    if value == 0:
        return (b"\x80" if math.copysign(1, value) < 0 else b"\x00") + bytes(size - 1)
    sign = 1 if value < 0 else 0
    m, e = math.frexp(abs(value))  # abs = m * 2**e, 0.5 <= m < 1
    # want abs = f * 16**(E-64), 1/16 <= f < 1
    q = -((-e) // 4)  # ceil(e/4)
    f = m * 2.0 ** (e - 4 * q)
    while f < 1 / 16:
        f *= 16
        q -= 1
    exp = q + 64
    if not 0 <= exp <= 127:
        raise FieldError(f"{value} out of HFP range")
    frac = int(f * (1 << frac_bits))
    if frac / (1 << frac_bits) != f:
        raise FieldError(f"{value} not exactly representable in {size}-byte HFP")
    word = (sign << (size * 8 - 1)) | (exp << frac_bits) | frac
    return word.to_bytes(size, "big")


# ---------------------------------------------------------------- text

def decode_text(b: bytes, codepage: str, trim: str = "right") -> str:
    s = b.decode(codepage)
    if trim == "right":
        return s.rstrip(" ")
    if trim == "both":
        return s.strip(" ")
    return s


def encode_text(s: str, size: int, codepage: str) -> bytes:
    b = s.encode(codepage)
    if len(b) > size:
        raise FieldError(f"text {s!r} longer than {size}")
    return b + " ".encode(codepage) * (size - len(b))
