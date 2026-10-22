import json
import os

from kopybook.cli import main
from conftest import CORPUS

CB = os.path.join(CORPUS, "copybooks")


def test_schema_avro_and_json(tmp_path, capsys):
    out = tmp_path / "s.avsc"
    assert main(["schema", os.path.join(CB, "30_customer_master.cpy"), "-o", str(out), "--namespace", "acme"]) == 0
    s = json.loads(out.read_text())
    assert s["name"] == "CustomerMaster" and s["namespace"] == "acme"
    assert main(["schema", "-f", "json", "--no-meta", os.path.join(CB, "14_odo_simple.cpy")]) == 0
    js = json.loads(capsys.readouterr().out)
    assert js["properties"]["txn_amount"]["maxItems"] == 20 and "x-cobol" not in js["properties"]["acct"]


def test_decode_encode_roundtrip(tmp_path):
    data = os.path.join(CORPUS, "data", "15_odo_group.bin")
    jl = tmp_path / "out.jsonl"
    assert main(["decode", os.path.join(CB, "15_odo_group.cpy"), data, "--rdw", "-o", str(jl)]) == 0
    assert jl.read_text() == open(os.path.join(CORPUS, "expected", "15_odo_group.jsonl"), encoding="utf-8").read()
    back = tmp_path / "back.bin"
    assert main(["encode", os.path.join(CB, "15_odo_group.cpy"), str(jl), "--rdw", "-o", str(back)]) == 0
    assert back.read_bytes() == open(data, "rb").read()


def test_decode_wrong_copybook_fails(tmp_path, capsys):
    data = os.path.join(CORPUS, "data", "02_zoned_unsigned.bin")
    assert main(["decode", os.path.join(CB, "09_comp3_packed.cpy"), data, "--record-length", "54"]) == 2


def test_compat_requires_pro(capsys, monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("kopybook_pro"):
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    d = os.path.join(CB)
    assert main(["compat", f"{d}/01_alnum_basic.cpy", f"{d}/01_alnum_basic.cpy"]) == 3
    assert "Kopybook Pro" in capsys.readouterr().err


def test_layout_and_bad_copybook(tmp_path, capsys):
    assert main(["layout", os.path.join(CB, "19_redefines_multi.cpy")]) == 0
    assert "record length: 25 bytes" in capsys.readouterr().out
    bad = tmp_path / "bad.cpy"
    bad.write_text("       01  R.\n           05  A PIC X SYNC.\n")
    assert main(["layout", str(bad)]) == 65
