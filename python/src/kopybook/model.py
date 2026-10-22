"""Data model for a parsed COBOL copybook."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


class CopybookError(Exception):
    """Raised for syntax errors or unsupported clauses, with a line number when known."""

    def __init__(self, message: str, line: Optional[int] = None):
        self.line = line
        super().__init__(f"line {line}: {message}" if line else message)


class UnsupportedClause(CopybookError):
    pass


class DecodeError(Exception):
    def __init__(self, path: str, offset: int, message: str):
        self.path, self.offset = path, offset
        super().__init__(f"{path} @ offset {offset}: {message}")


# Field kinds
ALNUM = "alnum"        # PIC X / A
NUMERIC = "numeric"    # PIC 9 / S9 / V
EDITED = "edited"      # numeric-edited, decoded as text
FLOAT = "float"        # COMP-1 / COMP-2 (IBM hexadecimal floating point)
GROUP = "group"

# Usages
DISPLAY = "DISPLAY"
BINARY = "BINARY"      # COMP, COMP-4, BINARY  (value limited to PIC digits, TRUNC(STD))
NATIVE = "COMP-5"      # COMP-5 (value limited by storage size)
PACKED = "COMP-3"      # COMP-3, PACKED-DECIMAL
COMP1 = "COMP-1"
COMP2 = "COMP-2"


@dataclass
class Pic:
    raw: str
    kind: str               # ALNUM / NUMERIC / EDITED
    length: int = 0         # display characters (ALNUM/EDITED) or digit count (NUMERIC)
    digits: int = 0         # total digits for NUMERIC
    scale: int = 0          # digits after V
    signed: bool = False


@dataclass
class Condition88:
    name: str
    values: List[object]    # literal values or ("THRU", lo, hi) tuples
    line: int = 0


@dataclass
class Renames66:
    name: str
    start: str
    end: Optional[str]
    line: int = 0


@dataclass
class Node:
    level: int
    name: str                       # COBOL name, upper-case; FILLER for unnamed
    line: int = 0
    pic: Optional[Pic] = None
    usage: Optional[str] = None     # explicit usage on this item
    sign_leading: Optional[bool] = None
    sign_separate: Optional[bool] = None
    occurs_min: Optional[int] = None
    occurs_max: Optional[int] = None
    depending_on: Optional[str] = None
    redefines: Optional[str] = None
    value: Optional[object] = None
    children: List["Node"] = field(default_factory=list)
    conditions: List[Condition88] = field(default_factory=list)
    renames: List[Renames66] = field(default_factory=list)   # only on 01
    parent: Optional["Node"] = field(default=None, repr=False)
    # resolved after parse
    eff_usage: str = DISPLAY
    kind: str = GROUP
    size: int = 0                   # bytes of ONE occurrence (max size when variable)
    min_size: int = 0
    offset: int = 0                 # static offset of first occurrence (max-layout)
    out_name: str = ""              # normalised output name
    is_redefined: bool = False      # some sibling REDEFINES this item

    @property
    def is_filler(self) -> bool:
        return self.name == "FILLER"

    @property
    def is_group(self) -> bool:
        return self.kind == GROUP

    @property
    def is_array(self) -> bool:
        return self.occurs_max is not None

    @property
    def variable(self) -> bool:
        return self.min_size != self.size

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def path(self) -> str:
        parts, n = [], self
        while n is not None:
            parts.append(n.name)
            n = n.parent
        return ".".join(reversed(parts))
