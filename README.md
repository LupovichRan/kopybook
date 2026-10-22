# Kopybook: COBOL copybooks → Kafka

> **Status: pre-release (0.1.1).** [Changelog](CHANGELOG.md) · Docs: [docs/](docs/index.md) · Issues: https://github.com/LupovichRan/kopybook/issues

[![CI](https://github.com/LupovichRan/kopybook/actions/workflows/ci.yml/badge.svg)](https://github.com/LupovichRan/kopybook/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Java](https://img.shields.io/badge/java-17%2B-orange)

Mainframe records reach Kafka as opaque EBCDIC bytes. Kopybook uses the COBOL copybook to turn
them into typed, schema-registered data:

- **Copybook → Avro / JSON Schema.** Decimal logical types with exact precision and scale.
  OCCURS becomes arrays. REDEFINES becomes optional views. 88-levels and 66-levels are kept as
  metadata.
- **A Kafka Connect plugin with no runtime dependencies.** It ships as a Converter and an SMT.
  It decodes COMP-3, COMP/COMP-4/COMP-5, zoned decimal in every sign form, COMP-1/COMP-2 (IBM
  hex float), OCCURS DEPENDING ON, REDEFINES, COPY/REPLACING and RDW framing. Supported code
  pages are cp037, cp1140, cp500 and others. The output is a Connect Struct, so Confluent's
  AvroConverter and Schema Registry take it from there.
- **A CLI** that does the same on files: `schema`, `layout`, `decode`, `encode`, `register`.
- **A golden corpus**: 42 synthetic copybooks, 43 cases and 1,075 EBCDIC records. Two
  independent implementations (Python and Java) decode every record byte-for-byte to the same
  JSON.

![demo](docs/assets/demo.gif)

## Quickstart

```bash
git clone https://github.com/LupovichRan/kopybook && cd kopybook
pip install ./python                       # the kopybook CLI (Python 3.10+)

kopybook layout   corpus/copybooks/30_customer_master.cpy          # offsets and sizes
kopybook schema   corpus/copybooks/31_insurance_claim.cpy -f avro --namespace acme.claims
kopybook decode   corpus/copybooks/31_insurance_claim.cpy corpus/data/31_insurance_claim.bin --rdw
kopybook register corpus/copybooks/30_customer_master.cpy --registry http://localhost:8081 --subject cust-value
```

Docker (no Python needed):

```bash
docker build -t kopybook .
docker run --rm -v "$PWD/corpus:/data" kopybook layout /data/copybooks/30_customer_master.cpy
```

### Kafka Connect

Build the plugin with `make package` and unzip `java/target/kopybook-connect-*.zip` into your
`plugin.path`. Then decode on any source that delivers bytes, such as MirrorSource, MQ, S3 or
SFTP:

```properties
transforms=cobol
transforms.cobol.type=dev.kopybook.connect.CopybookDecode$Value
transforms.cobol.copybook.path=/etc/kopybook/customer.cpy
transforms.cobol.copybook.include.path=/etc/kopybook/copylib
transforms.cobol.codepage=cp037
transforms.cobol.redefines.when=PAYMENT-DATA=IS-PAYMENT,REFUND-DATA=IS-REFUND
value.converter=io.confluent.connect.avro.AvroConverter
value.converter.schema.registry.url=http://schema-registry:8081
```

You can also use the plugin as a converter: `value.converter=dev.kopybook.connect.CopybookConverter`.
The converter also encodes Struct → EBCDIC for sinks. All options are listed in
[docs/connect.md](docs/connect.md).

## Why not just …

| | Kopybook |
|---|---|
| Hand-written decoding UDFs | Driven by the copybook, and tested against 1,075 golden records |
| Generic EBCDIC converters | Real COBOL semantics: ODO, REDEFINES view selection, TRUNC(STD), sign nibbles, HFP |
| Spark-only libraries | Runs inside Kafka Connect and on the command line. No cluster needed |

## Kopybook Pro: schema-evolution checker

`kopybook compat` (commercial add-on **Kopybook Pro**, package `kopybook-pro`) compares copybook versions. It reports the
Schema Registry verdict (BACKWARD/FORWARD/FULL, including transitive) **and** the wire-layout
verdict. A change that Schema Registry accepts can still shift every byte:

```
$ kopybook compat v1.cpy v2.cpy --level BACKWARD    # exit code 1
Schema Registry BACKWARD: COMPATIBLE
Wire layout: BREAKING (record length 24 -> 26)
  - CHANGED /acct_branch: size 4->6, PIC 9(4)->9(6)
  - CHANGED /acct_name: offset 4->6
```

Without a Pro license, every other feature stays free under Apache-2.0. See
[LICENSING.md](LICENSING.md).

## Development

```bash
make venv     # .venv with kopybook (editable) and test tools
make test     # Python + Java suites
make package  # Connect plugin zip (Confluent Hub layout)
make it       # docker compose Kafka + Schema Registry + Connect, end-to-end round trip
make docs     # mkdocs site -> site/
make demo     # re-record docs/assets/demo.gif
make bench    # Java decode throughput
```

```
python/        kopybook CLI and library (parser, codec, Avro / JSON Schema)
java/          kopybook-connect: Converter, SMT, parser, decoder/encoder, benchmarks
corpus/        copybooks/ (+ copylib/), data/*.bin, expected/*.jsonl, schemas/, generator/
integration/   docker-compose.yml + roundtrip.py
docs/          documentation site (mkdocs)
```

All copybooks and data in this repository are synthetic. They were written for this project
from public COBOL language rules.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
