"""Copybook -> JSON Schema (draft 2020-12). Decimals are strings to stay lossless."""
from __future__ import annotations

from typing import Optional

from .codec import _filler_name
from .model import Node
from .types import cobol_meta, ltype, pascal


def _leaf(n: Node, trunc: str) -> dict:
    t = ltype(n, trunc)
    if t.kind == "string":
        return {"type": "string", "maxLength": t.max_length}
    if t.kind in ("int", "long"):
        return {"type": "integer", "minimum": t.minimum, "maximum": t.maximum}
    if t.kind == "double":
        return {"type": "number"}
    ip = max(t.precision - t.scale, 1)
    sign = "-?" if (t.minimum or 0) < 0 else ""
    frac = rf"\.[0-9]{{{t.scale}}}" if t.scale else ""
    return {"type": "string", "pattern": rf"^{sign}[0-9]{{1,{ip}}}{frac}$",
            "x-decimal": {"precision": t.precision, "scale": t.scale}}


def _nullable(s: dict) -> dict:
    t = s.get("type")
    if isinstance(t, str):
        s = dict(s)
        s["type"] = [t, "null"]
        return s
    return {"anyOf": [s, {"type": "null"}]}


def _obj(node: Node, opts) -> dict:
    props, req = {}, []
    for c in node.children:
        in_chain = bool(c.redefines) or c.is_redefined
        if c.redefines and opts["redefines"] == "first":
            continue
        if c.is_filler and not opts["keep_filler"]:
            continue
        name = _filler_name(c) if c.is_filler else c.out_name
        s = _obj(c, opts) if c.children else _leaf(c, opts["trunc"])
        if c.is_array:
            s = {"type": "array", "items": s, "minItems": c.occurs_min, "maxItems": c.occurs_max}
        if opts["meta"]:
            s["x-cobol"] = cobol_meta(c)
        if opts["nullable_all"] or (in_chain and opts["redefines"] == "all"):
            s = _nullable(s)
        else:
            req.append(name)
        props[name] = s
    return {"type": "object", "properties": props, "required": req, "additionalProperties": False}


def to_json_schema(root: Node, meta: bool = True, nullable_all: bool = False, redefines: str = "all",
                   keep_filler: bool = False, trunc: str = "std", schema_id: Optional[str] = None) -> dict:
    s = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": pascal(root.name)}
    if schema_id:
        s["$id"] = schema_id
    s.update(_obj(root, dict(meta=meta, nullable_all=nullable_all, redefines=redefines,
                             keep_filler=keep_filler, trunc=trunc)))
    if meta:
        s["x-cobol-record"] = {"name": root.name, "recordLength": root.size, "minRecordLength": root.min_size}
    return s
