import os

import pytest

from kopybook import parser
from kopybook.model import CopybookError, UnsupportedClause
from conftest import CORPUS


def cb(name):
    return parser.parse_file(os.path.join(CORPUS, "copybooks", name + ".cpy"))


def leaf(root, name):
    return next(n for n in root.walk() if n.name == name)


EXPECTED_LENGTHS = {
    "01_alnum_basic": 51, "02_zoned_unsigned": 54, "03_zoned_signed_trailing": 37,
    "06_comp_binary": 34, "08_comp5_native": 32, "09_comp3_packed": 26, "10_comp3_large": 83,
    "11_occurs_fixed": 89, "12_occurs_group": 72, "13_occurs_nested": 118, "17_redefines_simple": 12,
    "19_redefines_multi": 25, "22_filler": 23, "27_float_hfp": 32, "28_numeric_edited": 46,
    "29_fixed_format_columns": 78, "30_customer_master": 173, "36_free_format_lowercase": 20,
}


@pytest.mark.parametrize("name,length", sorted(EXPECTED_LENGTHS.items()))
def test_record_lengths(name, length):
    # lengths computed by hand from the PIC/USAGE size rules
    assert cb(name).record().size == length


def test_offsets_and_sizes():
    r = cb("09_comp3_packed").record()
    assert [(c.name, c.offset, c.size) for c in r.children] == [
        ("P-ODD-S", 0, 5), ("P-EVEN-S", 5, 4), ("P-UNSIGNED", 9, 3), ("P-ONE", 12, 1),
        ("P-PACKED-DEC", 13, 7), ("P-COMPUTATIONAL-3", 20, 3), ("P-FRACTION", 23, 3)]


def test_binary_sizes():
    r = cb("06_comp_binary").record()
    assert [c.size for c in r.children] == [2, 2, 4, 4, 8, 8, 2, 4]


def test_sign_clauses():
    r = cb("05_zoned_sign_separate").record()
    a, b, c = r.children
    assert (a.size, a.sign_leading, a.sign_separate) == (8, False, True)
    assert (b.size, b.sign_leading, b.sign_separate) == (8, True, True)
    assert (c.size, c.sign_leading) == (4, True)


def test_redefines_area():
    r = cb("19_redefines_multi").record()
    pay = leaf(r, "PAYMENT-DATA")
    assert pay.is_redefined and pay.size == 18
    assert leaf(r, "REFUND-DATA").offset == 1 and leaf(r, "NOTE-DATA").offset == 1
    assert leaf(r, "SEQ-NO").offset == 19


def test_odo():
    r = cb("15_odo_group").record()
    t = leaf(r, "CLAIM-LINE")
    assert (t.occurs_min, t.occurs_max, t.depending_on, t.size) == (1, 15, "LINE-COUNT", 16)
    assert r.size == 14 + 15 * 16 and r.min_size == 14 + 16 and r.variable


def test_variable_location_after_odo():
    r = cb("16_odo_trailing_fields").record()
    assert r.min_size == 5 + 4 + 3 and r.size == 5 + 50 + 7


def test_level88_and_66():
    r = cb("20_level88_conditions").record()
    st = leaf(r, "ACCT-STATUS")
    assert [c.name for c in st.conditions] == ["ST-ACTIVE", "ST-CLOSED", "ST-ANY-OPEN"]
    assert st.conditions[1].values == ["C", "X"]
    assert st.conditions[2].values == [["THRU", "A", "B"]]
    assert leaf(r, "RISK-SCORE").conditions[1].values == [["THRU", 300, 699]]
    assert leaf(r, "VIP-FLAG").conditions[1].values == ["N", " "]
    r = cb("21_level66_renames").record()
    assert [(x.name, x.start, x.end) for x in r.renames] == [
        ("FULL-NAME", "FIRST-NAME", "LAST-NAME"), ("PHONE", "PHONE-AREA", "PHONE-NUM"), ("SURNAME", "LAST-NAME", None)]
    assert r.size == 35


def test_fillers_and_unnamed():
    r = cb("22_filler").record()
    assert [c.name for c in r.children] == ["FILLER", "KEEP-1", "FILLER", "KEEP-2", "FILLER", "FILLER", "KEEP-3"]


def test_group_usage_inherited():
    r = cb("26_group_usage_inherit").record()
    assert leaf(r, "T-GROSS").eff_usage == "COMP-3" and leaf(r, "T-GROSS").size == 6
    assert leaf(r, "C-LINES").eff_usage == "BINARY" and leaf(r, "C-LINES").size == 4


def test_fixed_format_and_continuation():
    r = cb("29_fixed_format_columns").record()
    assert leaf(r, "F-DESC").value == "A LONG LITERAL THAT CONTINUES"
    assert [c.name for c in r.children] == ["F-ID", "F-NAME", "F-AMOUNT", "F-DESC", "F-CODE"]


def test_value_literals():
    r = cb("37_value_clauses").record()
    assert leaf(r, "V-QUOTE").value == "IT'S"
    assert leaf(r, "V-HEX").value == "\xc1\xc2"
    assert leaf(r, "V-PACK").value == -1


def test_multiple_01_and_fragment():
    c = cb("33_multiple_01_records")
    assert [r.name for r in c.records] == ["FILE-HEADER", "FILE-DETAIL"]
    assert c.record("FILE-DETAIL").size == 41 and c.record("FILE-HEADER").size == 40 and c.record().name == "FILE-HEADER"
    f = cb("35_no_01_fragment").record()
    assert f.name == "RECORD" and f.size == 14


def test_duplicate_names_get_qualified_paths():
    r = cb("38_duplicate_names_qualified").record()
    names = [n.path() for n in r.walk() if n.name == "ZIP"]
    assert names == ["SHIPMENT-REC.BILL-TO.ADDR.ZIP", "SHIPMENT-REC.SHIP-TO.ADDR.ZIP"]


SRC = "       01  R.\n{}\n"


@pytest.mark.parametrize("body,exc,msg", [
    ("           05  A PIC S9(4) COMP SYNC.", UnsupportedClause, "SYNCHRONIZED"),
    ("           05  A PIC 9(3)PP.", UnsupportedClause, "scaling"),
    ("           05  A PIC N(10).", UnsupportedClause, "national"),
    ("           05  A PIC X(4) USAGE NATIONAL.", UnsupportedClause, "NATIONAL"),
    ("           05  A PIC S9(19) COMP.", UnsupportedClause, "binary"),
    ("           05  A PIC X OCCURS 1 TO 5 DEPENDING ON NOPE.", CopybookError, "not found"),
    ("           05  A PIC X OCCURS 1 TO 5.", CopybookError, "DEPENDING"),
    ("           05  A PIC X.\n           05  B PIC X.\n           05  C REDEFINES A PIC X.", CopybookError, "immediately"),
    ("           05  A PIC X(3).\n               10  B PIC X.", CopybookError, "PIC"),
    ("           05  A.", CopybookError, "has no PIC"),
    ("", CopybookError, "empty"),
    ("           05  A PIC X(3) FOO.", CopybookError, "unexpected token"),
    ("           05  A PIC X VALUE 'OPEN.", CopybookError, "unterminated"),
])
def test_rejects(body, exc, msg):
    with pytest.raises(exc) as e:
        parser.parse(SRC.format(body) if body else "      * nothing here\n")
    assert msg.lower() in str(e.value).lower()


def test_error_has_line_number():
    with pytest.raises(UnsupportedClause) as e:
        parser.parse("       01  R.\n           05  A PIC X.\n           05  B PIC S9(4) COMP SYNC.\n")
    assert e.value.line == 3


def test_odo_in_redefines_rejected():
    src = """       01  R.
           05  N PIC 9.
           05  A.
               10  T PIC X OCCURS 0 TO 3 DEPENDING ON N.
           05  B REDEFINES A PIC X(3).
"""
    with pytest.raises(UnsupportedClause):
        parser.parse(src)


# ----------------------------------------------------------------------------- COPY / REPLACING
COPYLIB = os.path.join(CORPUS, "copybooks", "copylib")


def test_copy_replacing_layout():
    r = parser.parse_file(os.path.join(CORPUS, "copybooks", "41_copy_replacing.cpy"), copy_paths=[COPYLIB]).record()
    names = [n.name for n in r.walk()]
    assert "BILL-STREET" in names and "SHIP-ZIP" in names and ":PFX:-CITY" not in names
    assert leaf(r, "PTY-GROSS").size == 6 and leaf(r, "PTY-GROSS").pic.raw == "S9(9)V99"
    assert leaf(r, "TRL-STAMP").offset == 119 and r.size == 145


def test_copy_word_replacing_and_level_number():
    r = parser.parse_file(os.path.join(CORPUS, "copybooks", "42_copy_word_replacing.cpy"), copy_paths=[COPYLIB]).record()
    assert [(c.level, c.name) for c in r.children] == [(5, "LG-KEY"), (5, "LG-DEBIT"), (5, "LG-CREDIT"), (5, "AMT-CCY")]


def test_copy_errors(tmp_path):
    (tmp_path / "SELF.cpy").write_text("           COPY SELF.\n")
    with pytest.raises(CopybookError, match="recursive"):
        parser.parse("       01  R.\n           COPY SELF.\n", copy_paths=[str(tmp_path)])
    with pytest.raises(CopybookError, match="not found"):
        parser.parse("       01  R.\n           COPY NOPE.\n", copy_paths=[str(tmp_path)])
    with pytest.raises(CopybookError, match="no copy library"):
        parser.parse("       01  R.\n           COPY NOPE.\n")
    with pytest.raises(CopybookError, match="pseudo-text"):
        parser.parse("       01  R.\n           COPY X REPLACING ==A BY B.\n", copy_paths=[str(tmp_path)])
    (tmp_path / "m.cpy").write_text("           05  A PIC X.\n")
    with pytest.raises(CopybookError, match="BY"):
        parser.parse("       01  R.\n           COPY M REPLACING ==A== WITH ==B==.\n", copy_paths=[str(tmp_path)])


def test_copy_trailing_replacing_and_delete(tmp_path):
    (tmp_path / "M.cpy").write_text("           05  ID-IN PIC X(3).\n           05  JUNK PIC X.\n")
    r = parser.parse("       01  R.\n           COPY M REPLACING TRAILING ==-IN== BY ==-OUT==\n"
                     "                            ==05  JUNK PIC X.== BY ====.\n", copy_paths=[str(tmp_path)]).record()
    assert [c.name for c in r.children] == ["ID-OUT"]
