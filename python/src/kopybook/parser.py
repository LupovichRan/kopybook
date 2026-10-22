"""COBOL copybook parser (data division entries only).

Supports fixed-format (cols 1-6 sequence, 7 indicator, 8-72 code) and free-format
source. Produces a tree of :class:`kopybook.model.Node` with resolved sizes and static
offsets. Only clauses covered by the regression corpus are accepted; anything that
would change the byte layout and is not implemented raises UnsupportedClause rather
than silently producing a wrong layout.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .model import (ALNUM, BINARY, COMP1, COMP2, DISPLAY, EDITED, FLOAT, GROUP, NATIVE,
                    NUMERIC, PACKED, Condition88, CopybookError, Node, Pic, Renames66,
                    UnsupportedClause)

USAGE_WORDS = {
    "DISPLAY": DISPLAY,
    "COMP": BINARY, "COMPUTATIONAL": BINARY, "COMP-4": BINARY, "COMPUTATIONAL-4": BINARY,
    "BINARY": BINARY,
    "COMP-5": NATIVE, "COMPUTATIONAL-5": NATIVE,
    "COMP-3": PACKED, "COMPUTATIONAL-3": PACKED, "PACKED-DECIMAL": PACKED,
    "COMP-1": COMP1, "COMPUTATIONAL-1": COMP1,
    "COMP-2": COMP2, "COMPUTATIONAL-2": COMP2,
}
UNSUPPORTED_USAGE = {"NATIONAL", "DISPLAY-1", "INDEX", "POINTER", "PROCEDURE-POINTER",
                     "FUNCTION-POINTER", "OBJECT", "COMP-6", "COMPUTATIONAL-6", "UTF-8"}
CLAUSE_WORDS = ({"PIC", "PICTURE", "USAGE", "REDEFINES", "OCCURS", "VALUE", "VALUES",
                 "SIGN", "LEADING", "TRAILING", "SYNC", "SYNCHRONIZED", "JUST", "JUSTIFIED",
                 "BLANK", "GLOBAL", "EXTERNAL", "RENAMES", "IS"}
                | set(USAGE_WORDS) | UNSUPPORTED_USAGE)
FIGURATIVE = {"ZERO": 0, "ZEROS": 0, "ZEROES": 0, "SPACE": " ", "SPACES": " ",
              "HIGH-VALUE": "\xff", "HIGH-VALUES": "\xff", "LOW-VALUE": "\x00",
              "LOW-VALUES": "\x00", "QUOTE": '"', "QUOTES": '"', "NULL": "\x00", "NULLS": "\x00"}


@dataclass
class Tok:
    text: str
    line: int
    literal: bool = False
    pseudo: Optional[List["Tok"]] = None   # ==pseudo-text== operand of COPY REPLACING


# ----------------------------------------------------------------------------- source

def _is_fixed(lines: List[str]) -> bool:
    for ln in lines:
        if not ln.strip():
            continue
        if len(ln) <= 6:
            continue
        if ln[6] not in " *-/Dd":
            return False
    return True


def preprocess(text: str, fmt: str = "auto") -> List[Tuple[int, str]]:
    """Return (line_number, code_text) pairs with comments and sequence areas removed."""
    lines = text.replace("\t", "    ").splitlines()
    fixed = _is_fixed(lines) if fmt == "auto" else fmt == "fixed"
    out: List[Tuple[int, str]] = []
    for i, ln in enumerate(lines, 1):
        if fixed:
            if len(ln) < 7:
                continue
            ind = ln[6]
            code = ln[7:72]
            if ind in "*/Dd":
                continue
            if ind == "-":
                cont = code.lstrip()
                if out and cont[:1] in "\"'":
                    pl, prev = out[-1]
                    prev = prev.ljust(65)  # literal runs to column 72
                    out[-1] = (pl, prev + cont[1:])
                    continue
                if out:
                    pl, prev = out[-1]
                    out[-1] = (pl, prev.rstrip() + cont)
                    continue
            out.append((i, code))
        else:
            s = ln
            if s.lstrip().startswith("*"):
                continue
            j = s.find("*>")
            if j >= 0:
                s = s[:j]
            out.append((i, s))
    return out


def tokenize(src: List[Tuple[int, str]]) -> List[Tok]:
    toks: List[Tok] = []
    # Join with newlines but keep line numbers.
    for line_no, code in src:
        i, n = 0, len(code)
        while i < n:
            c = code[i]
            if c.isspace():
                i += 1
                continue
            if c in ",;" and (i + 1 >= n or code[i + 1].isspace()):
                i += 1
                continue
            if c == ".":
                if i + 1 >= n or code[i + 1].isspace():
                    toks.append(Tok(".", line_no))
                    i += 1
                    continue
            if code.startswith("==", i):
                j = code.find("==", i + 2)
                if j < 0:
                    raise CopybookError("unterminated ==pseudo-text== (it must close on the same line)", line_no)
                inner = tokenize([(line_no, code[i + 2:j])])
                toks.append(Tok("==", line_no, pseudo=inner))
                i = j + 2
                continue
            hexlit = c in "xXzZ" and i + 1 < n and code[i + 1] in "\"'"
            if c in "\"'" or hexlit:
                start = i
                if hexlit:
                    i += 1
                q = code[i]
                i += 1
                buf = []
                while i < n:
                    if code[i] == q:
                        if i + 1 < n and code[i + 1] == q:
                            buf.append(q)
                            i += 2
                            continue
                        i += 1
                        break
                    buf.append(code[i])
                    i += 1
                else:
                    raise CopybookError("unterminated literal", line_no)
                s = "".join(buf)
                if hexlit and code[start] in "xX":
                    try:
                        s = bytes.fromhex(s).decode("latin-1")
                    except ValueError:
                        raise CopybookError(f"bad hex literal {s!r}", line_no)
                toks.append(Tok(s, line_no, literal=True))
                continue
            j = i
            while j < n and not code[j].isspace():
                if code[j] == "." and (j + 1 >= n or code[j + 1].isspace()):
                    break
                if code[j] in ",;" and (j + 1 >= n or code[j + 1].isspace()):
                    break
                j += 1
            toks.append(Tok(code[i:j].upper(), line_no))
            i = j
    return toks


# ----------------------------------------------------------------------------- COPY / REPLACING

COPY_EXTS = ("", ".cpy", ".CPY", ".cbl", ".CBL", ".cob", ".COB", ".copy", ".txt")
MAX_COPY_DEPTH = 16


def _check_member_name(name: str, what: str, line: int) -> None:
    """COPY names are library member names, never paths: reject separators, '..', NUL and absolute paths."""
    if (not name or "/" in name or "\\" in name or ".." in name or "\0" in name
            or os.path.isabs(name) or (len(name) > 1 and name[1] == ":")):
        raise CopybookError(f"COPY {what} name {name[:64]!r} is not a plain member name "
                            "(path separators and '..' are not allowed)", line)


def _within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def _find_member(name: str, lib: Optional[str], paths: List[str], line: int) -> str:
    """Return the real path of a COPY member, guaranteed to lie inside one of the copy directories.

    Error messages never contain member file contents."""
    _check_member_name(name, "member", line)
    if lib is not None:
        _check_member_name(lib, "library", line)
    cands = list(dict.fromkeys([name, name.lower(), name.upper()]))
    for d in paths:
        root = os.path.realpath(d)
        if not os.path.isdir(root):
            continue
        dirs = [root] + ([os.path.join(root, lib), os.path.join(root, lib.lower())] if lib else [])
        for dd in dirs:
            for c in cands:
                for e in COPY_EXTS:
                    p = os.path.join(dd, c + e)
                    if os.path.isfile(p):
                        real = os.path.realpath(p)
                        if not _within(real, root):
                            raise CopybookError(f"COPY member {name} resolves outside the copy library "
                                                "(symlink escape rejected)", line)
                        return real
    raise CopybookError(f"COPY member {name} not found in {paths}", line)


def _operand(t: Tok) -> List[Tok]:
    return list(t.pseudo) if t.pseudo is not None else [t]


def _same(a: Tok, b: Tok) -> bool:
    return a.text == b.text and a.literal == b.literal and a.pseudo is None and b.pseudo is None


def _apply_replacing(toks: List[Tok], reps) -> List[Tok]:
    out: List[Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        done = False
        for mode, pat, rep in reps:
            if not pat:
                continue
            if mode is None and all(i + k < len(toks) and _same(toks[i + k], p) for k, p in enumerate(pat)):
                out.extend(Tok(r.text, t.line, r.literal) for r in rep)
                i += len(pat)
                done = True
                break
            if len(pat) != 1 or t.literal or pat[0].literal:
                continue
            p, r = pat[0].text, "".join(x.text for x in rep)
            if mode == "LEADING" and t.text.startswith(p) and t.text != p:
                out.append(Tok(r + t.text[len(p):], t.line))
            elif mode == "TRAILING" and t.text.endswith(p) and t.text != p:
                out.append(Tok(t.text[:-len(p)] + r, t.line))
            elif mode is None and ":" in p and p in t.text:
                # IBM partial-word replacement of a :TAG: inside a word
                out.append(Tok(t.text.replace(p, r), t.line))
            else:
                continue
            i += 1
            done = True
            break
        if not done:
            out.append(t)
            i += 1
    return out


def _expand_copy(toks: List[Tok], paths: List[str], stack: List[str]) -> List[Tok]:
    out: List[Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.literal or t.pseudo is not None or t.text != "COPY":
            out.append(t)
            i += 1
            continue
        line = t.line
        try:
            name = toks[i + 1].text
            i += 2
            lib = None
            if toks[i].text in ("OF", "IN"):
                lib = toks[i + 1].text
                i += 2
            if toks[i].text == "SUPPRESS":
                i += 1
            reps = []
            if toks[i].text == "REPLACING":
                i += 1
                while toks[i].text != "." or toks[i].pseudo is not None:
                    mode = None
                    if toks[i].pseudo is None and toks[i].text in ("LEADING", "TRAILING"):
                        mode = toks[i].text
                        i += 1
                    a = _operand(toks[i])
                    if toks[i + 1].text != "BY":
                        raise CopybookError("COPY REPLACING: expected BY", toks[i + 1].line)
                    b = _operand(toks[i + 2])
                    reps.append((mode, a, b))
                    i += 3
            if toks[i].text != ".":
                raise CopybookError("COPY statement must end with a period", toks[i].line)
            i += 1
        except IndexError:
            raise CopybookError("incomplete COPY statement", line) from None
        if not paths:
            raise CopybookError(f"COPY {name}: no copy library path given", line)
        path = _find_member(name, lib, paths, line)
        if path in stack:
            raise CopybookError(f"recursive COPY of {name}", line)
        if len(stack) >= MAX_COPY_DEPTH:
            raise CopybookError("COPY nesting too deep", line)
        with open(path, encoding="utf-8") as f:
            member = tokenize(preprocess(f.read(), "auto"))
        member = _expand_copy(member, paths, stack + [path])
        out.extend(_apply_replacing(member, reps))
    return out


# ----------------------------------------------------------------------------- PIC

_REPEAT = re.compile(r"(.)\((\d+)\)")

#: Upper bound (bytes) for any single field and for a whole record. Real z/OS records top out
#: around 32 KB (QSAM/VSAM) and spanned records far below this; the cap exists so a hostile or
#: corrupt copybook such as ``PIC X(999999999)`` cannot exhaust memory in the parser or connector.
MAX_RECORD_LENGTH = 1_000_000


def expand_pic(raw: str, line: int = 0) -> str:
    total = 0
    for m in _REPEAT.finditer(raw):
        total += int(m.group(2)) if len(m.group(2)) <= 9 else MAX_RECORD_LENGTH + 1
        if total > MAX_RECORD_LENGTH:
            raise CopybookError(f"PIC {raw[:64]}: length exceeds the maximum of {MAX_RECORD_LENGTH} bytes", line)
    return _REPEAT.sub(lambda m: m.group(1) * int(m.group(2)), raw.upper())


def parse_pic(raw: str, line: int) -> Pic:
    s = expand_pic(raw, line)
    if "N" in s or "G" in s:
        raise UnsupportedClause(f"PIC {raw}: national/DBCS (N/G) is not supported", line)
    if "P" in s:
        raise UnsupportedClause(f"PIC {raw}: scaling position P is not supported", line)
    if "E" in s:
        raise UnsupportedClause(f"PIC {raw}: external floating point is not supported", line)
    if set(s) <= set("XA9") and ("X" in s or "A" in s):
        return Pic(raw, ALNUM, length=len(s))
    if set(s) <= set("S9V") and "9" in s:
        if s.count("S") > 1 or (s.count("S") == 1 and not s.startswith("S")) or s.count("V") > 1:
            raise CopybookError(f"invalid numeric PIC {raw}", line)
        body = s.lstrip("S")
        int_part, _, frac = body.partition("V")
        digits = int_part.count("9") + frac.count("9")
        if digits > 38:
            raise UnsupportedClause(f"PIC {raw}: more than 38 digits", line)
        return Pic(raw, NUMERIC, length=digits, digits=digits, scale=frac.count("9"),
                   signed=s.startswith("S"))
    if set(s) <= set("9Z*.,+-$B0/CRDBV") and any(ch in s for ch in "9Z*"):
        shown = s.replace("V", "")
        return Pic(raw, EDITED, length=len(shown))
    raise CopybookError(f"unrecognised PIC {raw}", line)


# ----------------------------------------------------------------------------- entries

def _split_entries(toks: List[Tok]) -> List[List[Tok]]:
    entries, cur = [], []
    for t in toks:
        if t.text == "." and not t.literal:
            if cur:
                entries.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        entries.append(cur)
    return entries


def _literal_value(t: Tok):
    if t.literal:
        return t.text
    if t.text in FIGURATIVE:
        return FIGURATIVE[t.text]
    if t.text.startswith("ALL"):
        return t.text
    try:
        if re.fullmatch(r"[+-]?\d+", t.text):
            return int(t.text)
        if re.fullmatch(r"[+-]?\d*\.\d+", t.text):
            return t.text
    except ValueError:
        pass
    return t.text


def _parse_entry(ent: List[Tok]):
    first = ent[0]
    if not re.fullmatch(r"\d{1,2}", first.text):
        raise CopybookError(f"expected level number, got {first.text!r}", first.line)
    level = int(first.text)
    if not (1 <= level <= 49 or level in (66, 77, 88)):
        raise CopybookError(f"invalid level number {level}", first.line)
    i = 1
    name = "FILLER"
    if i < len(ent) and not ent[i].literal and ent[i].text not in CLAUSE_WORDS:
        name = ent[i].text
        i += 1
    line = first.line

    if level == 88:
        j = i
        if j < len(ent) and ent[j].text in ("VALUE", "VALUES"):
            j += 1
        if j < len(ent) and ent[j].text in ("IS", "ARE"):
            j += 1
        vals: list = []
        while j < len(ent):
            v = _literal_value(ent[j])
            if j + 2 < len(ent) and ent[j + 1].text in ("THRU", "THROUGH") and not ent[j + 1].literal:
                vals.append(["THRU", v, _literal_value(ent[j + 2])])
                j += 3
            else:
                vals.append(v)
                j += 1
        if not vals:
            raise CopybookError(f"88 {name} has no VALUE", line)
        return ("88", Condition88(name, vals, line))

    if level == 66:
        if i >= len(ent) or ent[i].text != "RENAMES":
            raise CopybookError("66 level requires RENAMES", line)
        start = ent[i + 1].text
        end = None
        if i + 3 < len(ent) and ent[i + 2].text in ("THRU", "THROUGH"):
            end = ent[i + 3].text
        return ("66", Renames66(name, start, end, line))

    node = Node(level=level, name=name, line=line)
    while i < len(ent):
        t = ent[i].text
        if ent[i].literal:
            raise CopybookError(f"unexpected literal {ent[i].text!r}", ent[i].line)
        if t in ("PIC", "PICTURE"):
            i += 1
            if i < len(ent) and ent[i].text == "IS":
                i += 1
            node.pic = parse_pic(ent[i].text, ent[i].line)
            i += 1
        elif t == "USAGE":
            i += 1
            if i < len(ent) and ent[i].text == "IS":
                i += 1
            u = ent[i].text
            if u in UNSUPPORTED_USAGE:
                raise UnsupportedClause(f"USAGE {u} is not supported", line)
            if u not in USAGE_WORDS:
                raise CopybookError(f"unknown USAGE {u}", line)
            node.usage = USAGE_WORDS[u]
            i += 1
        elif t in USAGE_WORDS:
            node.usage = USAGE_WORDS[t]
            i += 1
        elif t in UNSUPPORTED_USAGE:
            raise UnsupportedClause(f"USAGE {t} is not supported", line)
        elif t == "REDEFINES":
            node.redefines = ent[i + 1].text
            i += 2
        elif t == "OCCURS":
            i += 1
            lo = int(ent[i].text)
            i += 1
            hi = lo
            if i < len(ent) and ent[i].text == "TO":
                hi = int(ent[i + 1].text)
                i += 2
            if i < len(ent) and ent[i].text == "TIMES":
                i += 1
            if i < len(ent) and ent[i].text == "DEPENDING":
                i += 1
                if ent[i].text == "ON":
                    i += 1
                node.depending_on = ent[i].text
                i += 1
            elif hi != lo:
                raise CopybookError("OCCURS m TO n requires DEPENDING ON", line)
            # KEY / INDEXED BY phrases do not change layout
            while i < len(ent) and ent[i].text in ("ASCENDING", "DESCENDING", "INDEXED"):
                if ent[i].text == "INDEXED":
                    i += 1
                    if i < len(ent) and ent[i].text == "BY":
                        i += 1
                    while i < len(ent) and ent[i].text not in CLAUSE_WORDS | {"ASCENDING", "DESCENDING"}:
                        i += 1
                else:
                    i += 1
                    while i < len(ent) and ent[i].text in ("KEY", "IS"):
                        i += 1
                    while i < len(ent) and ent[i].text not in CLAUSE_WORDS | {"ASCENDING", "DESCENDING", "INDEXED"}:
                        i += 1
            node.occurs_min, node.occurs_max = lo, hi
        elif t == "SIGN":
            i += 1
            if i < len(ent) and ent[i].text == "IS":
                i += 1
            continue
        elif t in ("LEADING", "TRAILING"):
            node.sign_leading = t == "LEADING"
            node.sign_separate = False
            i += 1
            if i < len(ent) and ent[i].text == "SEPARATE":
                node.sign_separate = True
                i += 1
                if i < len(ent) and ent[i].text == "CHARACTER":
                    i += 1
        elif t in ("VALUE", "VALUES"):
            i += 1
            if i < len(ent) and ent[i].text in ("IS", "ARE"):
                i += 1
            node.value = _literal_value(ent[i])
            i += 1
        elif t in ("SYNC", "SYNCHRONIZED"):
            raise UnsupportedClause("SYNCHRONIZED changes alignment and is not supported", line)
        elif t in ("JUST", "JUSTIFIED"):
            i += 1
            if i < len(ent) and ent[i].text == "RIGHT":
                i += 1
        elif t == "BLANK":
            i += 1
            while i < len(ent) and ent[i].text in ("WHEN", "ZERO", "ZEROS", "ZEROES"):
                i += 1
        elif t in ("GLOBAL", "EXTERNAL", "IS"):
            i += 1
        else:
            raise CopybookError(f"unexpected token {t!r}", ent[i].line)
    return ("node", node)


# ----------------------------------------------------------------------------- tree

def _build_tree(entries) -> List[Node]:
    roots: List[Node] = []
    stack: List[Node] = []
    last: Optional[Node] = None
    for kind, obj in entries:
        if kind == "88":
            if last is None:
                raise CopybookError("88 level without a preceding item", obj.line)
            last.conditions.append(obj)
            continue
        if kind == "66":
            if not roots:
                raise CopybookError("66 level without a record", obj.line)
            roots[-1].renames.append(obj)
            continue
        node: Node = obj
        if node.level in (1, 77):
            stack = [node]
            roots.append(node)
        else:
            while stack and stack[-1].level >= node.level:
                stack.pop()
            if not stack:
                # copybook fragment without an 01: synthesise a root
                root = Node(level=0, name="RECORD", line=node.line)
                roots.append(root)
                stack = [root]
            parent = stack[-1]
            if parent.pic is not None:
                raise CopybookError(f"{parent.name} has a PIC and cannot have subordinate items", node.line)
            node.parent = parent
            parent.children.append(node)
            stack.append(node)
        last = node
    return roots


def _inherit(node: Node, usage: str, sign_leading, sign_separate):
    u = node.usage or usage
    sl = node.sign_leading if node.sign_leading is not None else sign_leading
    ss = node.sign_separate if node.sign_separate is not None else sign_separate
    node.eff_usage = u
    node.sign_leading, node.sign_separate = sl, ss
    for c in node.children:
        _inherit(c, u, sl, ss)


def _binary_size(digits: int, line: int) -> int:
    if digits <= 4:
        return 2
    if digits <= 9:
        return 4
    if digits <= 18:
        return 8
    raise UnsupportedClause(f"binary field with {digits} digits (max 18)", line)


def _resolve(node: Node):
    if node.children:
        if node.pic is not None:
            raise CopybookError(f"group {node.name} has a PIC", node.line)
        node.kind = GROUP
        for c in node.children:
            _resolve(c)
        names = {c.name: c for c in node.children}
        size = min_size = 0
        i = 0
        kids = node.children
        while i < len(kids):
            c = kids[i]
            if c.redefines:
                raise CopybookError(f"{c.name} REDEFINES {c.redefines}, which does not immediately precede it", c.line)
            area_max = c.size * (c.occurs_max or 1)
            area_min = c.min_size * (c.occurs_min if c.occurs_max is not None else 1)
            j = i + 1
            while j < len(kids) and kids[j].redefines:
                r = kids[j]
                if r.redefines != c.name:
                    if r.redefines not in names:
                        raise CopybookError(f"REDEFINES target {r.redefines} not found", r.line)
                    # redefines another redefiner of the same area is allowed
                    tgt = names[r.redefines]
                    if not (tgt is c or tgt in kids[i + 1:j]):
                        raise CopybookError(f"{r.name} REDEFINES {r.redefines}, which does not immediately precede it", r.line)
                if r.depending_on or c.depending_on or r.variable or c.variable:
                    raise UnsupportedClause(f"REDEFINES involving variable-length data ({r.name})", r.line)
                c.is_redefined = True
                area_max = max(area_max, r.size * (r.occurs_max or 1))
                j += 1
            size += area_max
            min_size += area_max if j > i + 1 else area_min
            i = j
        if size > MAX_RECORD_LENGTH:
            what = "record" if node.level in (0, 1, 77) else "group"
            raise CopybookError(f"{what} {node.name} is {size} bytes, exceeding the maximum record length "
                                f"of {MAX_RECORD_LENGTH} bytes", node.line)
        node.size, node.min_size = size, min_size
        return
    if node.level == 0:
        raise CopybookError("empty record")
    u = node.eff_usage
    if u in (COMP1, COMP2):
        if node.pic is not None:
            raise CopybookError(f"{u} item {node.name} must not have a PIC", node.line)
        node.kind = FLOAT
        node.size = 4 if u == COMP1 else 8
    else:
        if node.pic is None:
            raise CopybookError(f"elementary item {node.name} has no PIC", node.line)
        p = node.pic
        node.kind = p.kind
        if p.kind in (ALNUM, EDITED):
            if u != DISPLAY:
                raise CopybookError(f"{node.name}: USAGE {u} needs a numeric PIC", node.line)
            node.size = p.length
        elif u == DISPLAY:
            node.size = p.digits + (1 if (p.signed and node.sign_separate) else 0)
        elif u in (BINARY, NATIVE):
            node.size = _binary_size(p.digits, node.line)
        elif u == PACKED:
            node.size = p.digits // 2 + 1
    if node.size * (node.occurs_max or 1) > MAX_RECORD_LENGTH:
        raise CopybookError(f"{node.name} is {node.size * (node.occurs_max or 1)} bytes, exceeding the maximum "
                            f"record length of {MAX_RECORD_LENGTH} bytes", node.line)
    node.min_size = node.size


def _odo_check(root: Node):
    by_name = {}
    for n in root.walk():
        by_name.setdefault(n.name, n)
    for n in root.walk():
        if n.depending_on:
            obj = by_name.get(n.depending_on)
            if obj is None:
                raise CopybookError(f"DEPENDING ON object {n.depending_on} not found", n.line)
            if obj.kind != NUMERIC:
                raise CopybookError(f"DEPENDING ON object {n.depending_on} is not numeric", n.line)
            if obj.pic.scale:
                raise CopybookError(f"DEPENDING ON object {n.depending_on} must be an integer", n.line)


def _offsets(node: Node, base: int):
    node.offset = base
    if not node.children:
        return
    cur = base
    area_start = base
    for c in node.children:
        if c.redefines:
            _offsets(c, area_start)
            continue
        area_start = cur
        _offsets(c, cur)
        # the area occupied may be widened by following redefiners
        width = c.size * (c.occurs_max or 1)
        idx = node.children.index(c)
        for r in node.children[idx + 1:]:
            if not r.redefines:
                break
            width = max(width, r.size * (r.occurs_max or 1))
        cur += width


def _norm_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", name.lower())
    if s[:1].isdigit():
        s = "f_" + s
    return s


def _assign_out_names(node: Node):
    seen = {}
    for c in node.children:
        if c.is_filler:
            c.out_name = ""
        else:
            base = _norm_name(c.name)
            k = seen.get(base, 0)
            seen[base] = k + 1
            c.out_name = base if k == 0 else f"{base}_{k + 1}"
        _assign_out_names(c)


@dataclass
class Copybook:
    records: List[Node]

    def record(self, name: Optional[str] = None) -> Node:
        if name is None:
            for r in self.records:
                if r.level != 77:
                    return r
            raise CopybookError("no record found")
        for r in self.records:
            if r.name == name.upper() or r.out_name == name:
                return r
        raise CopybookError(f"record {name} not found (have {[r.name for r in self.records]})")


def parse(text: str, fmt: str = "auto", copy_paths: Optional[List[str]] = None) -> Copybook:
    """copy_paths: directories searched for COPY members (parse_file adds the copybook's own dir)."""
    toks = _expand_copy(tokenize(preprocess(text, fmt)), list(copy_paths or []), [])
    if not toks:
        raise CopybookError("copybook is empty")
    entries = [_parse_entry(e) for e in _split_entries(toks)]
    roots = _build_tree(entries)
    for r in roots:
        _inherit(r, DISPLAY, False, False)
        _resolve(r)
        _odo_check(r)
        _offsets(r, 0)
        r.out_name = _norm_name(r.name)
        _assign_out_names(r)
        for rn in r.renames:
            names = {n.name for n in r.walk()}
            for ref in (rn.start, rn.end):
                if ref and ref not in names:
                    raise CopybookError(f"RENAMES target {ref} not found", rn.line)
    return Copybook(roots)


def parse_file(path: str, fmt: str = "auto", copy_paths: Optional[List[str]] = None) -> Copybook:
    with open(path, encoding="utf-8") as f:
        return parse(f.read(), fmt, list(copy_paths or []) + [os.path.dirname(os.path.abspath(path))])
