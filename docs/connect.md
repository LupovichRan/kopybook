# Kafka Connect

The plugin `kopybook-connect` has no dependencies beyond the Kafka Connect API that the worker
supplies. Unzip `kopybook-connect-<version>.zip` into a directory on `plugin.path` and restart the
worker.

## As an SMT (recommended)

Use the SMT with any source connector that delivers the raw record as `byte[]`, such as
MirrorSource, IBM MQ, S3 or SFTP. Then let Confluent's AvroConverter register the schema:

```properties
key.converter=org.apache.kafka.connect.converters.ByteArrayConverter
value.converter=io.confluent.connect.avro.AvroConverter
value.converter.schema.registry.url=http://schema-registry:8081
transforms=cobol
transforms.cobol.type=dev.kopybook.connect.CopybookDecode$Value
transforms.cobol.copybook.path=/etc/kopybook/customer.cpy
transforms.cobol.codepage=cp037
```

`dev.kopybook.connect.CopybookDecode$Key` decodes the record key instead.

## As a converter

```properties
value.converter=dev.kopybook.connect.CopybookConverter
value.converter.copybook.path=/etc/kopybook/customer.cpy
```

The converter also encodes Struct → EBCDIC, so a sink connector can write mainframe-format
files. Use `errors.tolerance=all` and a DLQ to route records that cannot be decoded.

## Options

| Key | Default | Description |
|---|---|---|
| `copybook.path` | — | Copybook file, present on every worker. Exactly one of `copybook.path` / `copybook.text` |
| `copybook.text` | — | Copybook source inline |
| `copybook.include.path` | — | Comma-separated COPY member directories. The directory of `copybook.path` is searched last |
| `copybook.record` | first | 01-level record name |
| `copybook.source.format` | `auto` | `auto`, `fixed`, `free` |
| `codepage` | `cp037` | cp037, cp1140, cp500, cp273, cp1047 or any Java charset name |
| `string.trim` | `right` | `right`, `both`, `none` |
| `redefines.strategy` | `all` | `all`: every view optional, null when unreadable; `first`: original only |
| `redefines.when` | — | view selection, e.g. `PAYMENT-DATA=IS-PAYMENT,NOTE-DATA=REC-TYPE:N\|X` ([rules](SPEC.md#redefines-view-selection)) |
| `filler.keep` | `false` | emit FILLER as `filler_<offset>` |
| `binary.trunc` | `std` | `std` or `bin` (COMP/COMP-4 range) |
| `framing` | `none` | `rdw`: each message starts with a 4-byte RDW |
| `schema.namespace` | — | namespace for struct names |
| `schema.nullable.all` | `false` | every field optional, so added fields stay BACKWARD compatible |
| `allow.trailing.bytes` | `false` | accept padding after the record |
| `on.error` | `fail` | SMT only: `fail` the task or `skip` the record |

## Types

| COBOL | Connect | Avro (via AvroConverter) |
|---|---|---|
| PIC X / A / edited | STRING | string |
| PIC 9 (scale 0, ≤ 9 digits) | INT32 | int |
| PIC 9 (scale 0, ≤ 18 digits) | INT64 | long |
| PIC 9 with V, or > 18 digits | Decimal (`connect.decimal.precision` set) | bytes + decimal logical type |
| COMP-1 / COMP-2 | FLOAT64 | double |
| group | STRUCT | record |
| OCCURS | ARRAY | array |
| REDEFINES view | optional | `["null", T]` |

## Verified end to end

`make it` starts Kafka, Schema Registry and Connect 7.8.0 (Confluent images) with docker
compose. It writes every corpus file to a topic, decodes it through MirrorSource → SMT →
AvroConverter, and compares all 1,075 records with the golden JSON.
