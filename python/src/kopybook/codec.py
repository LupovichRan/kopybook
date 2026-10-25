"""Record-level decoder and encoder driven by a parsed copybook tree.

Decoding walks the tree with a moving cursor, so OCCURS DEPENDING ON tables and
items that follow them (variable-location items) are handled naturally.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterator, List, Optional, Tuple

from . import fields as F
from .model import (ALNUM, BINARY, COMP1, DISPLAY, EDITED, FLOAT, NATIVE, NUMERIC, PACKED,
                    DecodeError, Node)


@dataclass
class Options:
    codepage: str = "cp037"
    trim: str = "right"            # right | both | none (PIC X handling)
    keep_filler: bool = False
    redefines: str = "all"         # all | first
    trunc: str = "std"             # std: COMP/COMP-4 limited to PIC digits; bin: storage size
    allow_trailing: bool = False   # accept bytes after the end of the record
    odo_strict: bool = True        # error when the ODO count is out of range
    # REDEFINES view selection: {"PAYMENT-DATA": "IS-PAYMENT", "REFUND-DATA": "REC-TYPE:R|X"}
    redefines_when: Optional[Dict[str, str]] = None


def parse_when(spec) -> Dict[str, str]:
    """'ALT=COND,ALT2=COND2' or a list of 'ALT=COND' -> dict. COND is an 88-level name or FIELD:V1|V2."""
    items = spec.split(",") if isinstance(spec, str) else list(spec or [])
    out = {}
    for it in items:
        it = it.strip()
        if not it:
            continue
        alt, sep, cond = it.partition("=")
        if not sep or not cond:
            raise ValueError(f"bad REDEFINES rule {it!r}: expected VIEW=88-NAME or VIEW=FIELD:VALUE[|VALUE]")
        out[alt.strip().upper()] = cond.strip()
    return out


class _Rule:
    def __init__(self, root: Node, alt: str, cond: str):
        names = {n.name: n for n in root.walk()}
        if alt not in names or not (names[alt].redefines or names[alt].is_redefined):
            raise ValueError(f"REDEFINES rule: {alt} is not part of a REDEFINES group")
        self.alt = alt
        if ":" in cond:
            field, _, vals = cond.partition(":")
            field = field.strip().upper()
            if field not in names:
                raise ValueError(f"REDEFINES rule for {alt}: field {field} not found")
            self.field, self.values = field, vals.split("|")
        else:
            c88 = None
            for n in root.walk():
                for c in n.conditions:
                    if c.name == cond.upper():
                        c88, owner = c, n
            if c88 is None:
                raise ValueError(f"REDEFINES rule for {alt}: no 88-level named {cond}")
            self.field, self.values = owner.name, c88.values
        self.node = names[self.field]

    def _eq(self, v, lit) -> bool:
        if isinstance(v, str):
            return v.rstrip(" ") == str(lit).rstrip(" ")
        try:
            return Decimal(v) == Decimal(str(lit))
        except Exception:
            return False

    def _cmp(self, v, lit):
        if isinstance(v, str):
            a, b = v.rstrip(" "), str(lit).rstrip(" ")
        else:
            a, b = Decimal(v), Decimal(str(lit))
        return (a > b) - (a < b)

    def matches(self, vals: Dict[str, Any]) -> bool:
        if self.field not in vals:
            raise DecodeError(self.alt, 0, f"REDEFINES rule field {self.field} is not decoded before the view")
        v = vals[self.field]
        for lit in self.values:
            if isinstance(lit, list) and lit and lit[0] == "THRU":
                if self._cmp(v, lit[1]) >= 0 and self._cmp(v, lit[2]) <= 0:
                    return True
            elif self._eq(v, lit):
                return True
        return False


def _lt(node: Node, trunc: str):
    key = "_lt_" + trunc
    t = node.__dict__.get(key)
    if t is None:
        from .types import ltype
        t = ltype(node, trunc)
        node.__dict__[key] = t
    return t


def _filler_name(n: Node) -> str:
    return f"filler_{n.offset}"


class _Decoder:
    def __init__(self, opts: Options, root: Optional[Node] = None):
        self.o = opts
        self.ctx: Dict[str, int] = {}
        self.vals: Dict[str, Any] = {}
        self.rules: Dict[str, _Rule] = {}
        if opts.redefines_when and root is not None:
            if opts.redefines != "all":
                raise ValueError("redefines_when needs the 'all' REDEFINES strategy")
            self.rules = {alt: _Rule(root, alt, cond) for alt, cond in opts.redefines_when.items()}

    def group(self, node: Node, data: bytes, pos: int) -> Tuple[Dict[str, Any], int]:
        out: Dict[str, Any] = {}
        kids = node.children
        i = 0
        while i < len(kids):
            c = kids[i]
            j = i + 1
            while j < len(kids) and kids[j].redefines:
                j += 1
            chain = kids[i:j]
            if len(chain) == 1:
                val, pos = self.item(c, data, pos)
                self._put(out, c, val)
            else:
                start, end = pos, pos
                selected = None
                if any(a.name in self.rules for a in chain):
                    hit = {a.name for a in chain if a.name in self.rules and self.rules[a.name].matches(self.vals)}
                    selected = hit or {a.name for a in chain if a.name not in self.rules}
                for k, alt in enumerate(chain):
                    width = alt.size * (alt.occurs_max or 1)
                    end = max(end, start + width)
                    if self.o.redefines == "first" and k > 0:
                        continue
                    if selected is not None:
                        val = self.item(alt, data, start)[0] if alt.name in selected else None
                    elif self.o.redefines == "first":
                        val, _ = self.item(alt, data, start)
                    else:
                        try:
                            val, _ = self.item(alt, data, start)
                        except (F.FieldError, DecodeError, UnicodeDecodeError):
                            val = None
                    self._put(out, alt, val)
                if end > len(data):
                    raise DecodeError(node.path(), end, "record too short")
                pos = end
            i = j
        return out, pos

    def _put(self, out, c: Node, val):
        if c.is_filler:
            if self.o.keep_filler:
                out[_filler_name(c)] = val
            return
        out[c.out_name] = val

    def item(self, node: Node, data: bytes, pos: int):
        if not node.is_array:
            return self.single(node, data, pos)
        if node.depending_on:
            if node.depending_on not in self.ctx:
                raise DecodeError(node.path(), pos, f"DEPENDING ON {node.depending_on} not decoded before table")
            n = self.ctx[node.depending_on]
            if n < node.occurs_min or n > node.occurs_max:
                if self.o.odo_strict:
                    raise DecodeError(node.path(), pos,
                                      f"{node.depending_on} value outside {node.occurs_min}..{node.occurs_max}")
                n = max(node.occurs_min, min(n, node.occurs_max))
        else:
            n = node.occurs_max
        vals = []
        for _ in range(n):
            v, pos = self.single(node, data, pos)
            vals.append(v)
        return vals, pos

    def single(self, node: Node, data: bytes, pos: int):
        if node.children:
            return self.group(node, data, pos)
        end = pos + node.size
        if end > len(data):
            raise DecodeError(node.path(), pos, f"record too short (need {end} bytes, have {len(data)})")
        b = data[pos:end]
        try:
            v = self.leaf(node, b)
        except F.FieldError as e:
            raise DecodeError(node.path(), pos, str(e)) from None
        self.vals[node.name] = v
        if isinstance(v, int):
            self.ctx[node.name] = v
            if node.pic is not None and node.pic.scale == 0 and _lt(node, self.o.trunc).kind == "decimal":
                v = Decimal(v)
        return v, end

    def leaf(self, n: Node, b: bytes):
        o = self.o
        if n.kind in (ALNUM, EDITED):
            return F.decode_text(b, o.codepage, o.trim)
        if n.kind == FLOAT:
            return F.decode_hfp(b)
        p = n.pic
        u = n.eff_usage
        if u == DISPLAY:
            return F.decode_zoned(b, p.digits, p.scale, p.signed, bool(n.sign_leading), bool(n.sign_separate))
        if u == PACKED:
            return F.decode_packed(b, p.digits, p.scale, p.signed)
        if u in (BINARY, NATIVE):
            return F.decode_binary(b, p.digits, p.scale, p.signed, u == BINARY and o.trunc == "std")
        raise DecodeError(n.path(), 0, f"unsupported usage {u}")


def decode(root: Node, data: bytes, opts: Optional[Options] = None) -> Dict[str, Any]:
    opts = opts or Options()
    d = _Decoder(opts, root)
    if root.children:
        val, pos = d.group(root, data, 0)
    else:
        v, pos = d.single(root, data, 0)
        val = {root.out_name: v}
    if pos != len(data) and not opts.allow_trailing:
        raise DecodeError(root.path(), pos, f"{len(data) - pos} trailing bytes after record (record ends at {pos})")
    return val


def decode_with_length(root: Node, data: bytes, opts: Optional[Options] = None) -> Tuple[Dict[str, Any], int]:
    opts = opts or Options()
    d = _Decoder(opts, root)
    val, pos = d.group(root, data, 0)
    return val, pos


# ----------------------------------------------------------------------------- encode

class _Encoder:
    def __init__(self, opts: Options):
        self.o = opts
        self.ctx: Dict[str, int] = {}

    def group(self, node: Node, value: Optional[dict]) -> bytes:
        value = value or {}
        out = bytearray()
        kids = node.children
        i = 0
        while i < len(kids):
            c = kids[i]
            j = i + 1
            while j < len(kids) and kids[j].redefines:
                j += 1
            chain = kids[i:j]
            if len(chain) == 1:
                out += self.item(c, value.get(c.out_name) if not c.is_filler else None)
            else:
                width = max(a.size * (a.occurs_max or 1) for a in chain)
                active = next((a for a in chain if value.get(a.out_name) is not None), chain[0])
                b = self.item(active, value.get(active.out_name))
                out += b + F.encode_text("", width - len(b), self.o.codepage)
            i = j
        return bytes(out)

    def item(self, node: Node, value):
        if not node.is_array:
            return self.single(node, value)
        if node.depending_on:
            n = self.ctx.get(node.depending_on)
            if n is None:
                raise F.FieldError(f"{node.path()}: ODO object {node.depending_on} not encoded first")
            vals = value or []
            if len(vals) != n:
                raise F.FieldError(f"{node.path()}: {len(vals)} items do not match {node.depending_on}")
        else:
            n = node.occurs_max
            vals = value if value is not None else [None] * n
            if len(vals) != n:
                raise F.FieldError(f"{node.path()}: expected {n} items, got {len(vals)}")
        return b"".join(self.single(node, v) for v in vals)

    def single(self, node: Node, value) -> bytes:
        if node.children:
            return self.group(node, value)
        o = self.o
        if node.kind in (ALNUM, EDITED):
            return F.encode_text(value or "", node.size, o.codepage)
        if node.kind == FLOAT:
            return F.encode_hfp(float(value or 0.0), node.size)
        p = node.pic
        v = value if value is not None else 0
        if isinstance(v, str):
            v = Decimal(v)
        if p.scale == 0 and isinstance(v, Decimal):
            v = int(v)
        if isinstance(v, int):
            self.ctx[node.name] = v
        u = node.eff_usage
        if u == DISPLAY:
            return F.encode_zoned(v, p.digits, p.scale, p.signed, bool(node.sign_leading), bool(node.sign_separate))
        if u == PACKED:
            return F.encode_packed(v, p.digits, p.scale, p.signed, node.size)
        return F.encode_binary(v, p.digits, p.scale, p.signed, node.size, u == BINARY and o.trunc == "std")


def encode(root: Node, value: Dict[str, Any], opts: Optional[Options] = None) -> bytes:
    return _Encoder(opts or Options()).group(root, value)


# ----------------------------------------------------------------------------- files

def iter_fixed(data: bytes, length: int) -> Iterator[bytes]:
    if length <= 0 or len(data) % length:
        raise ValueError(f"file size {len(data)} is not a multiple of record length {length}")
    for i in range(0, len(data), length):
        yield data[i:i + length]


def iter_rdw(data: bytes) -> Iterator[bytes]:
    """IBM variable-length records: 4-byte RDW (2-byte big-endian length incl. RDW, 2 zero bytes)."""
    i = 0
    while i < len(data):
        if i + 4 > len(data):
            raise ValueError(f"truncated RDW at {i}")
        n = int.from_bytes(data[i:i + 2], "big")
        if n < 4 or data[i + 2:i + 4] != b"\x00\x00" or i + n > len(data):
            raise ValueError(f"invalid RDW {data[i:i + 4].hex()} at {i}")
        yield data[i + 4:i + n]
        i += n


def write_rdw(records: List[bytes]) -> bytes:
    return b"".join((len(r) + 4).to_bytes(2, "big") + b"\x00\x00" + r for r in records)


def to_jsonable(v):
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, dict):
        return {k: to_jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [to_jsonable(x) for x in v]
    return v
