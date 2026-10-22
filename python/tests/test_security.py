"""Hardening tests: COPY path traversal / symlink escape and the record-length cap."""
import os

import pytest

from kopybook import parser
from kopybook.model import CopybookError

SECRET = "TOP-SECRET-CONTENT-4f2a"


@pytest.fixture
def layout(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.cpy").write_text(SECRET + "\n")
    (outside / "secret").write_text(SECRET + "\n")
    (lib / "GOOD.cpy").write_text("           05  A PIC X(3).\n")
    return lib, outside


def _copy(stmt, lib):
    return parser.parse(f"       01  R.\n           {stmt}\n", copy_paths=[str(lib)])


@pytest.mark.parametrize("stmt", [
    "COPY '../outside/secret'.",
    "COPY '../../etc/hostname'.",
    "COPY '..'.",
    "COPY 'a/b'.",
    "COPY '..\\\\outside\\\\secret'.",
    "COPY 'sub\\\\x'.",
    "COPY GOOD OF '../outside'.",
])
def test_traversal_names_rejected(layout, stmt):
    lib, _ = layout
    with pytest.raises(CopybookError, match="not a plain member name") as ei:
        _copy(stmt, lib)
    assert SECRET not in str(ei.value)


def test_absolute_path_rejected(layout):
    lib, outside = layout
    # long absolute paths do not fit a fixed-format line, so exercise the resolver directly too
    with pytest.raises(CopybookError, match="not a plain member name") as ei:
        parser._find_member(str(outside / "secret"), None, [str(lib)], 1)
    assert SECRET not in str(ei.value)
    with pytest.raises(CopybookError, match="not a plain member name"):
        _copy("COPY '/etc/hostname'.", lib)


def test_symlink_escape_rejected(layout):
    lib, outside = layout
    os.symlink(outside / "secret.cpy", lib / "LEAK.cpy")
    with pytest.raises(CopybookError, match="outside the copy library") as ei:
        _copy("COPY LEAK.", lib)
    assert SECRET not in str(ei.value)


def test_symlinked_library_dir_escape_rejected(layout):
    lib, outside = layout
    os.symlink(outside, lib / "evil")
    with pytest.raises(CopybookError, match="outside the copy library"):
        _copy("COPY SECRET OF EVIL.", lib)


def test_symlink_inside_library_allowed(layout):
    lib, _ = layout
    os.symlink(lib / "GOOD.cpy", lib / "ALIAS.cpy")
    assert _copy("COPY ALIAS.", lib).record().size == 3


def test_extensionless_file_not_matched(layout):
    lib, _ = layout
    (lib / "BARE").write_text("           05  B PIC X.\n")
    with pytest.raises(CopybookError, match="not found"):
        _copy("COPY BARE.", lib)


def test_error_message_does_not_leak_content(tmp_path):
    # the original exploit: a non-copybook file reached via traversal used to surface in a parse error
    lib = tmp_path / "a" / "b"
    lib.mkdir(parents=True)
    (tmp_path / "hostname").write_text(SECRET + "\n")
    with pytest.raises(CopybookError) as ei:
        _copy("COPY '../../hostname'.", lib)
    assert SECRET not in str(ei.value)


def test_normal_copy_still_works(layout):
    lib, _ = layout
    r = _copy("COPY GOOD.", lib).record()
    assert [(c.name, c.size) for c in r.children] == [("A", 3)]
    assert _copy("COPY good.", lib).record().size == 3


def test_copy_of_library_still_works(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "M.cpy").write_text("           05  A PIC X(2).\n")
    assert _copy("COPY M OF SUB.", tmp_path).record().size == 2


# ----------------------------------------------------------------------------- record cap

def test_max_record_length_constant():
    assert parser.MAX_RECORD_LENGTH == 1_000_000


def test_pic_at_cap_ok():
    r = parser.parse(f"       01  R.\n           05  A PIC X({parser.MAX_RECORD_LENGTH}).\n").record()
    assert r.size == parser.MAX_RECORD_LENGTH


@pytest.mark.parametrize("n", [parser.MAX_RECORD_LENGTH + 1, 999999999, 10 ** 30])
def test_huge_pic_x_rejected(n):
    with pytest.raises(CopybookError, match="maximum"):
        parser.parse(f"       01  R.\n           05  A PIC X({n}).\n")


def test_record_total_over_cap_rejected():
    with pytest.raises(CopybookError, match="maximum record length"):
        parser.parse("       01  R.\n           05  A PIC X(600000).\n           05  B PIC X(600000).\n")


def test_occurs_over_cap_rejected():
    with pytest.raises(CopybookError, match="maximum record length"):
        parser.parse("       01  R.\n           05  A PIC X(1000) OCCURS 2000 TIMES.\n")
