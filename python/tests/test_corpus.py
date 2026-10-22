"""Regression corpus: every golden record must decode byte-for-byte to its expected JSON."""
import hashlib
import io
import json
import os

import fastavro
import jsonschema
import pytest
from kopybook.codec import DecodeError

from kopybook import avro, codec, jsonschema_gen, parser
from conftest import CORPUS

MANIFEST = json.load(open(os.path.join(CORPUS, "manifest.json")))
CASES = {c["case"]: c for c in MANIFEST["cases"]}


def load(case):
    c = CASES[case]
    root = parser.parse_file(os.path.join(CORPUS, c["copybook"]),
                             copy_paths=[os.path.join(CORPUS, c["copyPath"])]).record(c["record"])
    data = open(os.path.join(CORPUS, "data", case + ".bin"), "rb").read()
    recs = list(codec.iter_rdw(data) if c["framing"] == "rdw" else codec.iter_fixed(data, c["recordLength"]))
    exp = [json.loads(l) for l in open(os.path.join(CORPUS, "expected", case + ".jsonl"), encoding="utf-8")]
    return c, root, data, recs, exp


def test_corpus_size():
    assert len(CASES) >= 40
    assert sum(c["records"] for c in CASES.values()) >= 750


@pytest.mark.parametrize("case", sorted(CASES))
def test_decode_matches_golden(case):
    c, root, data, recs, exp = load(case)
    assert hashlib.sha256(data).hexdigest() == c["sha256"], "corpus bytes changed"
    assert len(recs) == len(exp) == c["records"]
    o = codec.Options(codepage=c["codepage"])
    for i, (r, e) in enumerate(zip(recs, exp)):
        assert codec.to_jsonable(codec.decode(root, r, o)) == e, f"record {i}"


def _has_redefines(root):
    return any(n.redefines for n in root.walk())


@pytest.mark.parametrize("case", sorted(CASES))
def test_reencode_is_byte_identical(case):
    c, root, data, recs, exp = load(case)
    if _has_redefines(root):
        pytest.skip("inactive REDEFINES views are lossy by design")
    o = codec.Options(codepage=c["codepage"])
    for r in recs:
        if any(n.is_filler for n in root.walk()):
            # FILLER bytes are not carried; compare after re-decoding instead
            assert codec.decode(root, codec.encode(root, codec.decode(root, r, o), o), o) == codec.decode(root, r, o)
        else:
            assert codec.encode(root, codec.decode(root, r, o), o) == r


@pytest.mark.parametrize("case", sorted(CASES))
def test_golden_validates_against_json_schema(case):
    c, root, data, recs, exp = load(case)
    schema = jsonschema_gen.to_json_schema(root)
    jsonschema.Draft202012Validator.check_schema(schema)
    v = jsonschema.Draft202012Validator(schema)
    for e in exp:
        errs = list(v.iter_errors(e))
        assert not errs, errs[0].message


@pytest.mark.parametrize("case", sorted(CASES))
def test_avro_roundtrip(case):
    c, root, data, recs, exp = load(case)
    parsed = fastavro.parse_schema(avro.to_avro(root, namespace="kopybook.test"))
    o = codec.Options(codepage=c["codepage"])
    for r in recs:
        d = codec.decode(root, r, o)
        buf = io.BytesIO()
        fastavro.schemaless_writer(buf, parsed, d)
        buf.seek(0)
        assert fastavro.schemaless_reader(buf, parsed) == d


@pytest.mark.parametrize("case", sorted(CASES))
def test_schema_snapshots_up_to_date(case):
    c, root, *_ = load(case)
    with open(os.path.join(CORPUS, "schemas", case + ".avsc"), encoding="utf-8") as f:
        assert json.load(f) == json.loads(avro.dumps(avro.to_avro(root, namespace="kopybook.corpus")))
    with open(os.path.join(CORPUS, "schemas", case + ".schema.json"), encoding="utf-8") as f:
        assert json.load(f) == json.loads(json.dumps(jsonschema_gen.to_json_schema(root)))


def test_truncated_record_reports_offset():
    c, root, data, recs, exp = load("30_customer_master")
    with pytest.raises(Exception) as e:
        codec.decode(root, recs[0][:-20])
    assert "offset" in str(e.value)


def test_trailing_bytes_rejected_unless_allowed():
    c, root, data, recs, exp = load("02_zoned_unsigned")
    with pytest.raises(Exception):
        codec.decode(root, recs[3] + b"\x40")
    assert codec.decode(root, recs[3] + b"\x40", codec.Options(allow_trailing=True))


def test_odo_out_of_range():
    c, root, data, recs, exp = load("14_odo_simple")
    bad = recs[0][:8] + (99).to_bytes(2, "big") + recs[0][10:]
    with pytest.raises(Exception) as e:
        codec.decode(root, bad)
    assert "outside 0..20" in str(e.value)


def test_redefines_first_strategy():
    c, root, data, recs, exp = load("19_redefines_multi")
    d = codec.decode(root, recs[0], codec.Options(redefines="first", codepage=c["codepage"]))
    assert set(d) == {"rec_type", "payment_data", "seq_no"}


def test_keep_filler():
    c, root, data, recs, exp = load("22_filler")
    d = codec.decode(root, recs[0], codec.Options(keep_filler=True))
    assert {"filler_0", "filler_7", "filler_12", "filler_19"} <= set(d)
    assert d["filler_12"]["filler_15"] == 0 and d["filler_19"] == 0


def test_codepage_matters():
    c, root, data, recs, exp = load("23_codepage_cp037_specials")
    a = codec.decode(root, recs[0], codec.Options(codepage="cp037"))
    b = codec.decode(root, recs[0], codec.Options(codepage="cp500"))
    assert a["brackets"].startswith("[]{}") and a != b


# ----------------------------------------------------------------------------- REDEFINES view selection
WHEN_19 = {"PAYMENT-DATA": "IS-PAYMENT", "REFUND-DATA": "IS-REFUND", "NOTE-DATA": "REC-TYPE:N"}


def test_redefines_when_selects_one_view():
    c, root, data, recs, exp = load("19_redefines_multi")
    o = codec.Options(codepage=c["codepage"], redefines_when=WHEN_19)
    views = {"P": "payment_data", "R": "refund_data", "N": "note_data"}
    for r, e in zip(recs, exp):
        d = codec.to_jsonable(codec.decode(root, r, o))
        want = views[e["rec_type"]]
        assert d[want] == e[want]
        assert all(d[v] is None for v in views.values() if v != want)


def test_redefines_when_otherwise_view_and_errors():
    c, root, data, recs, exp = load("40_occurs_redefines_mix")
    # MX-AREA has no rule: it is the "otherwise" view
    o = codec.Options(redefines_when=codec.parse_when("MX-TABLE=MX-KIND:T,MX-PAIRS=MX-KIND:P"))
    for r, e in zip(recs, exp):
        d = codec.to_jsonable(codec.decode(root, r, o))
        k = e["mx_kind"]
        assert (d["mx_table"] is not None) == (k == "T") and (d["mx_pairs"] is not None) == (k == "P")
        assert (d["mx_area"] is not None) == (k == "A")
    with pytest.raises(ValueError, match="not part of a REDEFINES"):
        codec.decode(root, recs[0], codec.Options(redefines_when={"MX-KIND": "MX-KIND:T"}))
    with pytest.raises(ValueError, match="no 88-level"):
        codec.decode(root, recs[0], codec.Options(redefines_when={"MX-TABLE": "NOPE"}))
    with pytest.raises(ValueError, match="expected VIEW"):
        codec.parse_when("MX-TABLE")


def test_redefines_when_selected_view_is_strict():
    root = parser.parse("       01  R.\n           05  K PIC X.\n           05  A PIC X(2).\n"
                        "           05  B REDEFINES A PIC 99.\n").record()
    o = codec.Options(codepage="cp037", redefines_when={"B": "K:N"})
    good = codec.decode(root, "N12".encode("cp037"), o)
    assert good["b"] == 12 and good["a"] is None
    assert codec.decode(root, "XAB".encode("cp037"), o)["b"] is None
    with pytest.raises(Exception):          # selected view is decoded strictly: bad data is an error, not null
        codec.decode(root, "NAB".encode("cp037"), o)
    with pytest.raises(DecodeError, match="not decoded before"):
        codec.decode(root, b"NAB", codec.Options(redefines_when={"B": "A:12"}))


def test_cli_redefines_when(tmp_path, capsys):
    from kopybook.cli import main
    assert main(["decode", os.path.join(CORPUS, "copybooks", "19_redefines_multi.cpy"),
                 os.path.join(CORPUS, "data", "19_redefines_multi.bin"),
                 "--redefines-when", "PAYMENT-DATA=IS-PAYMENT", "--redefines-when", "REFUND-DATA=IS-REFUND",
                 "--redefines-when", "NOTE-DATA=IS-NOTE"]) == 0
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    assert len(lines) == 25 and all(sum(l[v] is not None for v in ("payment_data", "refund_data", "note_data")) == 1 for l in lines)
