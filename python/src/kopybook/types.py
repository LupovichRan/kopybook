"""Logical type mapping shared by the Avro and JSON Schema emitters (and mirrored in Java)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .model import ALNUM, BINARY, EDITED, FLOAT, NATIVE, NUMERIC, Node


@dataclass
class LType:
    kind: str                 # string | int | long | decimal | double
    precision: int = 0
    scale: int = 0
    minimum: Optional[int] = None   # unscaled bounds
    maximum: Optional[int] = None
    max_length: int = 0


def ltype(n: Node, trunc: str = "std") -> LType:
    if n.kind in (ALNUM, EDITED):
        return LType("string", max_length=n.size)
    if n.kind == FLOAT:
        return LType("double")
    assert n.kind == NUMERIC
    p = n.pic
    u = n.eff_usage
    if u == NATIVE or (u == BINARY and trunc == "bin"):
        bits = n.size * 8
        if p.signed:
            lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
        else:
            lo, hi = 0, (1 << bits) - 1
        precision = len(str(hi))
    else:
        hi = 10 ** p.digits - 1
        lo = -hi if p.signed else 0
        precision = p.digits
    if p.scale == 0:
        if lo >= -(1 << 31) and hi <= (1 << 31) - 1:
            return LType("int", precision=precision, minimum=lo, maximum=hi)
        if lo >= -(1 << 63) and hi <= (1 << 63) - 1:
            return LType("long", precision=precision, minimum=lo, maximum=hi)
    return LType("decimal", precision=max(precision, p.scale, 1), scale=p.scale, minimum=lo, maximum=hi)


def pascal(name: str) -> str:
    parts = [x for x in name.replace("-", "_").split("_") if x]
    s = "".join(x[:1].upper() + x[1:].lower() for x in parts) or "Filler"
    return s if not s[0].isdigit() else "F" + s


def cobol_meta(n: Node) -> dict:
    m = {"level": n.level, "name": n.name, "offset": n.offset, "size": n.size}
    if n.pic is not None:
        m["pic"] = n.pic.raw
    if n.children == []:
        m["usage"] = n.eff_usage
        if n.pic is not None and n.pic.signed and n.eff_usage == "DISPLAY":
            m["sign"] = ("LEADING" if n.sign_leading else "TRAILING") + (" SEPARATE" if n.sign_separate else "")
    if n.occurs_max is not None:
        m["occurs"] = [n.occurs_min, n.occurs_max]
    if n.depending_on:
        m["dependingOn"] = n.depending_on
    if n.redefines:
        m["redefines"] = n.redefines
    if n.conditions:
        m["conditions88"] = {c.name: c.values for c in n.conditions}
    return m
