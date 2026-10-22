#!/usr/bin/env python3
"""Synthetic EBCDIC regression corpus generator.

For every copybook in corpus/copybooks it:
  1. generates N records of random-but-valid values (seeded, deterministic), with
     edge records first (maxima, minima, zeros);
  2. encodes them to EBCDIC with the kopybook encoder;
  3. decodes the bytes with the kopybook decoder and ASSERTS that every generated value
     comes back unchanged (generator values are independent of the decoder);
  4. writes data/<case>.bin, expected/<case>.jsonl and schemas/<case>.{avsc,schema.json}.

Inactive REDEFINES views are not generated, they are decoded from the bytes of the
active view; those values are cross-checked by the independent Java decoder.
All data is synthetic. No real customer data, no client copybooks.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from decimal import Context, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "..", "python", "src"))

from kopybook import avro, codec, jsonschema_gen, parser  # noqa: E402
from kopybook.model import ALNUM, EDITED, FLOAT, NUMERIC  # noqa: E402
from kopybook.types import ltype  # noqa: E402

N_RECORDS = 25
DEFAULT_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,-/&'()*+:=?"
ALPHA_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz "

# case overrides; every copybook gets a case even when not listed here
CASES = {
    "23_codepage_cp037_specials": {"codepage": "cp037", "chars": "[]{}\\|!^~¢¬äöüÄÖÜéèàçñßø@#$% "},
    "24_codepage_cp1140_euro": {"codepage": "cp1140", "chars": "€£¥$¢ 0123456789.,ABCDEFabcdef"},
    "25_codepage_cp500": {"codepage": "cp500", "chars": "[]!|^ äöüéçABCDEFGHIJKabcdefghij"},
    "19_redefines_multi": {"selector": {"field": "REC-TYPE",
                                        "map": {"PAYMENT-DATA": "P", "REFUND-DATA": "R", "NOTE-DATA": "N"}}},
    "40_occurs_redefines_mix": {"selector": {"field": "MX-KIND",
                                             "map": {"MX-AREA": "A", "MX-TABLE": "T", "MX-PAIRS": "P"}}},
    "33_multiple_01_records": {"record": "FILE-DETAIL"},
    "33_multiple_01_records__header": {"copybook": "33_multiple_01_records", "record": "FILE-HEADER"},
    "29_fixed_format_columns": {"codepage": "cp1140"},
    "32_bank_transaction": {"codepage": "cp1140"},
}


class Gen:
    def __init__(self, root, rnd: random.Random, chars: str, selector=None):
        self.root, self.r, self.chars, self.sel = root, rnd, chars, selector
        self.odo = {}
        for n in root.walk():
            if n.depending_on:
                lo, hi = self.odo.get(n.depending_on, (0, 10 ** 9))
                self.odo[n.depending_on] = (max(lo, n.occurs_min), min(hi, n.occurs_max))
        self.mode = "random"
        self.vals = {}

    def record(self, mode: str, idx: int):
        self.mode, self.idx, self.vals = mode, idx, {}
        self.forced = {}
        return self.group(self.root)

    def group(self, node):
        out = {}
        kids = node.children
        i = 0
        while i < len(kids):
            c = kids[i]
            j = i + 1
            while j < len(kids) and kids[j].redefines:
                j += 1
            chain = kids[i:j]
            if len(chain) == 1:
                v = self.item(c)
                if not c.is_filler:
                    out[c.out_name] = v
            else:
                active = chain[self.idx % len(chain)]
                if self.sel and active.name in self.sel["map"]:
                    self._force(self.sel["field"], self.sel["map"][active.name], out)
                for alt in chain:
                    out[alt.out_name] = self.item(alt) if alt is active else None
            i = j
        return out

    def _force(self, field, value, out):
        # selector precedes the chain in our corpus copybooks, so patch the value already generated
        for n in self.root.walk():
            if n.name == field:
                if n.out_name in out:
                    out[n.out_name] = value
                    return
        raise RuntimeError(f"selector {field} not found before chain")

    def item(self, node):
        if not node.is_array:
            return self.single(node)
        n = self.vals[node.depending_on] if node.depending_on else node.occurs_max
        return [self.single(node) for _ in range(n)]

    def single(self, node):
        if node.children:
            return self.group(node)
        v = self.leaf(node)
        if node.name in self.odo:
            self.vals[node.name] = v
        return v

    def leaf(self, n):
        r, m = self.r, self.mode
        if n.kind == ALNUM:
            chars = ALPHA_CHARS if set(parser.expand_pic(n.pic.raw)) == {"A"} else self.chars
            if m == "max":
                s = (chars.replace(" ", "") * n.size)[: n.size]
            elif m == "min":
                s = ""
            elif m == "zero":
                s = chars.strip()[0]
            else:
                s = "".join(r.choice(chars) for _ in range(r.randint(0, n.size)))
            return s.rstrip(" ")
        if n.kind == EDITED:
            if m == "min":
                return ""
            num = r.randint(0, 10 ** 6)
            s = f"{num:,}"[: n.size]
            return s.rjust(r.randint(len(s), n.size))
        if n.kind == FLOAT:
            if m == "zero":
                return 0.0
            bits = 20 if n.size == 4 else 44
            k = r.randint(-(1 << bits), 1 << bits)
            if m == "max":
                k = (1 << bits) - 1
            elif m == "min":
                k = -((1 << bits) - 1)
            return float(k) * 2.0 ** r.choice([-12, -4, 0, 4, 16])
        t = ltype(n)
        lo, hi = t.minimum, t.maximum
        if n.name in self.odo:
            olo, ohi = self.odo[n.name]
            lo, hi = max(lo, olo), min(hi, ohi)
        if m == "max":
            u = hi
        elif m == "min":
            u = lo
        elif m == "zero":
            u = max(lo, min(0, hi))
        else:
            mag = r.choice([1, 2, 3, len(str(hi))])
            cap = min(hi, 10 ** mag)
            floor = max(lo, -cap)
            u = r.randint(floor, cap)
        if n.pic.scale:
            return Decimal(u).scaleb(-n.pic.scale, Context(prec=100))
        return u


def compare(gen, dec, path=""):
    if gen is None:
        return
    if isinstance(gen, dict):
        for k, v in gen.items():
            compare(v, dec[k], f"{path}/{k}")
        return
    if isinstance(gen, list):
        assert len(gen) == len(dec), f"{path}: {len(gen)} != {len(dec)}"
        for i, (a, b) in enumerate(zip(gen, dec)):
            compare(a, b, f"{path}[{i}]")
        return
    if isinstance(gen, (int, Decimal)) and isinstance(dec, (int, Decimal)):
        assert Decimal(gen) == Decimal(dec), f"{path}: generated {gen!r} decoded {dec!r}"
        return
    assert gen == dec, f"{path}: generated {gen!r} decoded {dec!r}"


def build_case(case: str, cfg: dict, out_dir: str):
    cb_name = cfg.get("copybook", case)
    cb_path = os.path.join(ROOT, "copybooks", cb_name + ".cpy")
    copy_dir = os.path.join(ROOT, "copybooks", "copylib")
    root = parser.parse_file(cb_path, copy_paths=[copy_dir]).record(cfg.get("record"))
    codepage = cfg.get("codepage", "cp037")
    seed = int(hashlib.sha256(case.encode()).hexdigest()[:8], 16)
    g = Gen(root, random.Random(seed), cfg.get("chars", DEFAULT_CHARS), cfg.get("selector"))
    opts = codec.Options(codepage=codepage)
    recs, expected = [], []
    modes = ["max", "min", "zero"] + ["random"] * (N_RECORDS - 3)
    for i, mode in enumerate(modes):
        v = g.record(mode, i)
        b = codec.encode(root, v, opts)
        d = codec.decode(root, b, opts)
        compare(v, d)
        recs.append(b)
        expected.append(codec.to_jsonable(d))
    framing = "rdw" if root.variable else "fixed"
    data = codec.write_rdw(recs) if framing == "rdw" else b"".join(recs)
    os.makedirs(os.path.join(out_dir, "data"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "expected"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "schemas"), exist_ok=True)
    with open(os.path.join(out_dir, "data", case + ".bin"), "wb") as f:
        f.write(data)
    with open(os.path.join(out_dir, "expected", case + ".jsonl"), "w", encoding="utf-8") as f:
        for e in expected:
            f.write(json.dumps(e, ensure_ascii=False, sort_keys=False) + "\n")
    with open(os.path.join(out_dir, "schemas", case + ".avsc"), "w", encoding="utf-8") as f:
        f.write(avro.dumps(avro.to_avro(root, namespace="kopybook.corpus")) + "\n")
    with open(os.path.join(out_dir, "schemas", case + ".schema.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(jsonschema_gen.to_json_schema(root), indent=2, ensure_ascii=False) + "\n")
    return {"case": case, "copybook": f"copybooks/{cb_name}.cpy", "copyPath": "copybooks/copylib",
            "record": root.name, "codepage": codepage,
            "framing": framing, "recordLength": root.size, "minRecordLength": root.min_size,
            "records": len(recs), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def main():
    names = sorted(f[:-4] for f in os.listdir(os.path.join(ROOT, "copybooks")) if f.endswith(".cpy"))
    cases = {n: CASES.get(n, {}) for n in names}
    for k, v in CASES.items():
        if k not in cases:
            cases[k] = v
    manifest = [build_case(c, cfg, ROOT) for c, cfg in sorted(cases.items())]
    with open(os.path.join(ROOT, "manifest.json"), "w") as f:
        json.dump({"generator": "kopybook-corpus/1", "recordsPerCase": N_RECORDS, "cases": manifest}, f, indent=2)
    print(f"{len(manifest)} cases, {sum(m['records'] for m in manifest)} records, "
          f"{sum(m['bytes'] for m in manifest)} bytes")


if __name__ == "__main__":
    main()
