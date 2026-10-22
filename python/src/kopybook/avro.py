"""Copybook -> Avro schema."""
from __future__ import annotations

import json
from typing import List, Optional

from .codec import _filler_name
from .model import Node
from .types import cobol_meta, ltype, pascal


def _leaf_type(n: Node, trunc: str):
    t = ltype(n, trunc)
    if t.kind == "string":
        return "string"
    if t.kind in ("int", "long", "double"):
        return t.kind
    return {"type": "bytes", "logicalType": "decimal", "precision": t.precision, "scale": t.scale}


class AvroBuilder:
    def __init__(self, namespace: Optional[str], meta: bool, nullable_all: bool,
                 redefines: str, keep_filler: bool, trunc: str):
        self.ns, self.meta, self.nullable_all = namespace, meta, nullable_all
        self.redefines, self.keep_filler, self.trunc = redefines, keep_filler, trunc

    def record(self, node: Node, path: List[str]) -> dict:
        name = pascal(node.name) if not path else "_".join(pascal(p) for p in path)
        rec = {"type": "record", "name": name}
        if not path and self.ns:
            rec["namespace"] = self.ns
        fields = []
        kids = node.children
        for idx, c in enumerate(kids):
            in_chain = bool(c.redefines) or c.is_redefined
            if c.redefines and self.redefines == "first":
                continue
            if c.is_filler and not self.keep_filler:
                continue
            fname = _filler_name(c) if c.is_filler else c.out_name
            t = self.type_of(c, path + [c.name if not c.is_filler else fname])
            nullable = self.nullable_all or (in_chain and self.redefines == "all")
            f = {"name": fname, "type": ["null", t] if nullable else t}
            if nullable:
                f["default"] = None
            if self.meta:
                f["cobol"] = cobol_meta(c)
            fields.append(f)
        rec["fields"] = fields
        if self.meta and not path:
            rec["cobol"] = {"copybookRecord": node.name, "recordLength": node.size,
                            "minRecordLength": node.min_size}
            if node.renames:
                rec["cobol"]["renames66"] = [{"name": r.name, "from": r.start, "thru": r.end} for r in node.renames]
        return rec

    def type_of(self, n: Node, path: List[str]):
        t = self.record(n, path) if n.children else _leaf_type(n, self.trunc)
        if n.is_array:
            return {"type": "array", "items": t}
        return t


def to_avro(root: Node, namespace: Optional[str] = None, meta: bool = True, nullable_all: bool = False,
            redefines: str = "all", keep_filler: bool = False, trunc: str = "std") -> dict:
    return AvroBuilder(namespace, meta, nullable_all, redefines, keep_filler, trunc).record(root, [])


def dumps(schema: dict) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False)
