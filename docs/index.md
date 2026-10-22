# Kopybook

**COBOL copybooks → typed Kafka data.** Kopybook reads a copybook and turns mainframe EBCDIC
records into Avro, JSON Schema and Kafka Connect Structs. Field values come out exact: packed
decimals stay decimals, and tables keep their real ODO length.

![demo](assets/demo.gif)

<div class="grid" markdown>

- **[Quickstart](quickstart.md)**: decode your first file in two minutes.
- **[CLI](cli.md)**: `layout`, `schema`, `decode`, `encode`, `register`.
- **[Kafka Connect](connect.md)**: the Converter and SMT, with every option.
- **[Supported COBOL](SPEC.md)**: exactly what is decoded, and how.

</div>

## What it handles

| | |
|---|---|
| Numeric | zoned decimal (overpunch, LEADING/TRAILING, SEPARATE), COMP-3, COMP/COMP-4/BINARY with TRUNC(STD) or full binary range, COMP-5, COMP-1/COMP-2 IBM hex float |
| Structure | groups, OCCURS, OCCURS DEPENDING ON (items after the table move with it), REDEFINES with view selection, 66 RENAMES, 88 conditions, FILLER |
| Source | fixed and free format, continuation lines, `COPY … REPLACING` (pseudo-text, LEADING/TRAILING, `:TAG:`) |
| Data | cp037, cp1140, cp500, cp273, cp1047 …, fixed-length and RDW-framed files |
| Output | Avro (decimal logical types), JSON Schema 2020-12, Connect Struct (Decimal with `connect.decimal.precision`) |

Every feature is covered by the [golden corpus](corpus.md). Two independent decoders, one in
Python and one in Java, must agree on every byte of it.
