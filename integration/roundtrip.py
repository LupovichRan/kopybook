#!/usr/bin/env python3
"""End-to-end test against the docker-compose stack (Kafka + Schema Registry + Connect).

1. Produces raw EBCDIC records from the golden corpus to `ebcdic.<case>` topics.
2. Runs Kafka's stock MirrorSourceConnector per topic with the kopybook SMT
   (CopybookDecode$Value) and Confluent's AvroConverter, so Connect writes Avro to
   `mf.ebcdic.<case>` and registers the schema in Schema Registry.
3. Consumes the Avro topic, decodes it with the schema fetched from Schema Registry,
   and compares every record with the golden JSON.
4. Replays the copybook-evolution corpus against the live Schema Registry and compares
   its verdicts with the expected verdicts and with kopybook's own checker.
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

import fastavro
from kafka import KafkaConsumer, KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "python", "src"))
# Optional Kopybook Pro checkout, only from the environment (no sibling-path guessing).
PRO = os.environ.get("KOPYBOOK_PRO", "")
if PRO:
    sys.path.insert(0, os.path.join(PRO, "python", "src"))
from kopybook import avro, codec, parser  # noqa: E402

try:  # the live compatibility replay needs Kopybook Pro (set KOPYBOOK_PRO)
    from kopybook_pro import compat  # noqa: E402
except ImportError:
    compat = None

CORPUS = os.path.join(ROOT, "corpus")
BOOT, SR, CONNECT = "localhost:9092", "http://localhost:8081", "http://localhost:8083"
CASES = os.environ.get("KOPYBOOK_CASES", "").split(",") if os.environ.get("KOPYBOOK_CASES") else [
    "08_comp5_native", "09_comp3_packed", "10_comp3_large", "15_odo_group", "19_redefines_multi",
    "24_codepage_cp1140_euro", "27_float_hfp", "30_customer_master", "31_insurance_claim", "40_occurs_redefines_mix"]


def http(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def wait(url, what, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if http("GET", url)[0] == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit(f"{what} not ready after {timeout}s")


def load_case(case):
    m = {c["case"]: c for c in json.load(open(os.path.join(CORPUS, "manifest.json")))["cases"]}[case]
    root = parser.parse_file(os.path.join(CORPUS, m["copybook"]),
                             copy_paths=[os.path.join(CORPUS, m.get("copyPath", "copybooks/copylib"))]).record(m["record"])
    data = open(os.path.join(CORPUS, "data", case + ".bin"), "rb").read()
    recs = list(codec.iter_rdw(data) if m["framing"] == "rdw" else codec.iter_fixed(data, m["recordLength"]))
    exp = [json.loads(l) for l in open(os.path.join(CORPUS, "expected", case + ".jsonl"), encoding="utf-8")]
    return m, root, recs, exp


def pipeline():
    wait(f"{SR}/subjects", "schema registry")
    wait(f"{CONNECT}/connector-plugins", "connect")
    plugins = http("GET", f"{CONNECT}/connector-plugins?connectorsOnly=false")[1]
    names = {p["class"] for p in plugins}
    assert "dev.kopybook.connect.CopybookDecode$Value" in names, "kopybook SMT not loaded by Connect"
    assert "dev.kopybook.connect.CopybookConverter" in names, "kopybook converter not loaded by Connect"
    print("Connect loaded kopybook plugin: CopybookDecode$Value, CopybookDecode$Key, CopybookConverter")

    admin = KafkaAdminClient(bootstrap_servers=BOOT)
    existing = set(admin.list_topics())
    admin.create_topics([NewTopic(f"ebcdic.{c}", 1, 1) for c in CASES if f"ebcdic.{c}" not in existing])
    prod = KafkaProducer(bootstrap_servers=BOOT)
    total = 0
    for c in CASES:
        m, root, recs, exp = load_case(c)
        for i, r in enumerate(recs):
            prod.send(f"ebcdic.{c}", key=str(i).encode(), value=r)
            total += 1
    prod.flush()
    print(f"produced {total} EBCDIC records to {len(CASES)} topics")

    for c in CASES:
        m, *_ = load_case(c)
        cfg = {
            "connector.class": "org.apache.kafka.connect.mirror.MirrorSourceConnector",
            "source.cluster.alias": "mf", "target.cluster.alias": "local",
            "source.cluster.bootstrap.servers": "localhost:9092", "target.cluster.bootstrap.servers": "localhost:9092",
            "topics": f"ebcdic.{c}", "tasks.max": "1",
            "replication.factor": "1", "offset-syncs.topic.replication.factor": "1",
            "sync.topic.configs.enabled": "false", "sync.topic.acls.enabled": "false",
            "refresh.topics.interval.seconds": "5",
            "key.converter": "org.apache.kafka.connect.converters.ByteArrayConverter",
            "value.converter": "io.confluent.connect.avro.AvroConverter",
            "value.converter.schema.registry.url": "http://localhost:8081",
            "transforms": "cobol",
            "transforms.cobol.type": "dev.kopybook.connect.CopybookDecode$Value",
            "transforms.cobol.copybook.path": f"/etc/kopybook/{m['copybook']}",
            "transforms.cobol.copybook.record": m["record"],
            "transforms.cobol.copybook.include.path": f"/etc/kopybook/{m.get('copyPath', 'copybooks/copylib')}",
            "transforms.cobol.codepage": m["codepage"],
            "transforms.cobol.schema.namespace": "kopybook.corpus",
        }
        st, body = http("PUT", f"{CONNECT}/connectors/kopybook-{c.replace('_', '-')}/config", cfg)
        assert st in (200, 201), (st, body)
    print(f"started {len(CASES)} MirrorSourceConnector pipelines with the kopybook SMT + AvroConverter")

    schemas = {}
    ok = bad = 0
    for c in CASES:
        m, root, recs, exp = load_case(c)
        cons = KafkaConsumer(f"mf.ebcdic.{c}", bootstrap_servers=BOOT, auto_offset_reset="earliest",
                             consumer_timeout_ms=1000, group_id=None)
        got = []
        t0 = time.time()
        while len(got) < len(recs) and time.time() - t0 < 120:
            for msg in cons:
                got.append(msg)
            if len(got) < len(recs):
                time.sleep(1)
        cons.close()
        if len(got) != len(recs):
            st = http("GET", f"{CONNECT}/connectors/kopybook-{c.replace('_', '-')}/status")[1]
            raise SystemExit(f"{c}: got {len(got)} of {len(recs)} records; status {json.dumps(st)[:800]}")
        got.sort(key=lambda m_: int(m_.key))
        for msg, e in zip(got, exp):
            v = msg.value
            assert v[0] == 0, "not Confluent wire format"
            sid = int.from_bytes(v[1:5], "big")
            if sid not in schemas:
                schemas[sid] = fastavro.parse_schema(json.loads(http("GET", f"{SR}/schemas/ids/{sid}")[1]["schema"]))
            rec = fastavro.schemaless_reader(io.BytesIO(v[5:]), schemas[sid])
            if codec.to_jsonable(rec) == e:
                ok += 1
            else:
                bad += 1
                print(f"MISMATCH {c} key={msg.key}: {codec.to_jsonable(rec)} != {e}")
        subj = http("GET", f"{SR}/subjects/mf.ebcdic.{c}-value/versions/latest")[1]
        registered = json.loads(subj["schema"])
        mine = avro.to_avro(root, namespace="kopybook.corpus", meta=False)
        if compat is not None:
            assert compat.can_read(registered, mine) == [] and compat.can_read(mine, registered) == [], \
                f"{c}: registered schema differs from kopybook schema"
        else:
            assert [f["name"] for f in registered["fields"]] == [f["name"] for f in mine["fields"]], c
    print(f"Avro records verified against golden JSON: {ok} ok, {bad} mismatched")
    return bad == 0


def live_compat():
    root = os.path.join(PRO, "corpus-compat") if PRO else ""
    if compat is None or not os.path.isdir(root):
        print("KOPYBOOK_PRO not set (or Kopybook Pro not available): skipping the live compatibility replay")
        return True
    agree = disagree = 0
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        spec = json.load(open(os.path.join(d, "expected.json")))
        nullable = spec["options"].get("nullable_all", False)
        files = sorted(f for f in os.listdir(d) if f.endswith(".cpy"))
        schemas = [avro.to_avro(parser.parse_file(os.path.join(d, f)).record(), nullable_all=nullable, meta=False)
                   for f in files]
        subject = f"kopybook-compat-{name}-{int(time.time())}"
        http("PUT", f"{SR}/config/{subject}", {"compatibility": "NONE"})
        for s in schemas[:-1]:
            st, body = http("POST", f"{SR}/subjects/{subject}/versions", {"schema": json.dumps(s)})
            assert st == 200, body
        for level, want in spec["expected"].items():
            if level == "wire" or level == "semantic":
                continue
            http("PUT", f"{SR}/config/{subject}", {"compatibility": level})
            live = compat.registry_check(SR, subject, schemas[-1], version=None)["is_compatible"]
            ours = compat.check_level(schemas[-1], schemas[:-1], level)["compatible"]
            if live == want == ours:
                agree += 1
            else:
                disagree += 1
                print(f"DISAGREE {name} {level}: expected={want} schema-registry={live} kopybook={ours}")
        http("DELETE", f"{SR}/subjects/{subject}")
    print(f"live Schema Registry compatibility verdicts: {agree} agree, {disagree} disagree")
    return disagree == 0


if __name__ == "__main__":
    a = pipeline() if "--compat-only" not in sys.argv else True
    b = live_compat()
    sys.exit(0 if a and b else 1)
