# Golden corpus

`corpus/` is a synthetic test suite for anyone who decodes copybooks, whatever tool they use.

| | |
|---|---|
| `copybooks/*.cpy` | 42 copybooks; `copybooks/copylib/` holds 4 COPY members |
| `data/*.bin` | EBCDIC data, fixed or RDW-framed |
| `expected/*.jsonl` | the decoded value of every record (decimals as strings) |
| `schemas/` | the Avro and JSON Schema generated for every case |
| `manifest.json` | case → copybook, record, codepage, framing, record length, count |
| `generator/` | seeded generator; `make corpus` rebuilds everything byte-identically |

Every case targets one rule: overpunch signs on every digit, all packed sign nibbles, COMP
boundary values for 2/4/8 bytes, HFP special values, ODO at min/max, items after an ODO
table, multi-view REDEFINES, cp1140's euro sign, continuation literals, COPY REPLACING and
more. The Python and Java decoders are both tested against it.

All data is made up. No production copybook or record was used.
