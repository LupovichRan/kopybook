# CLI reference

```
kopybook layout   COPYBOOK                      byte layout table
kopybook schema   COPYBOOK -f avro|json         schema to stdout
kopybook decode   COPYBOOK DATA [-o out.jsonl]  EBCDIC records -> JSON lines
kopybook encode   COPYBOOK IN.jsonl -o DATA     JSON lines -> EBCDIC (test data)
kopybook register COPYBOOK --registry URL --subject S
kopybook compat   V1 V2 [...]                   [Pro] evolution verdict
kopybook license                                [Pro] show the installed license
```

## Common options

| Option | Default | Meaning |
|---|---|---|
| `--record NAME` | first 01 | which 01-level record to use |
| `--source-format` | `auto` | `fixed` (columns 7–72), `free` or `auto` |
| `-I DIR`, `--copy-path DIR` | — | COPY member directory (repeatable). The copybook's own directory is always searched last |
| `--codepage` | `cp037` | any Python codec: `cp1140`, `cp500`, `cp273`, … |
| `--trim` | `right` | `right`, `both` or `none` for PIC X |
| `--redefines` | `all` | `all` = every view, nullable; `first` = original item only |
| `--redefines-when VIEW=COND` | — | decode a view only when COND holds (an 88-level name or `FIELD:V1\|V2`) |
| `--keep-filler` | off | emit FILLER as `filler_<offset>` |
| `--trunc` | `std` | `std`: COMP values limited to the PIC digits; `bin`: full storage |

## decode

| Option | Meaning |
|---|---|
| `--rdw` | 4-byte RDW before every record |
| `--record-length N` | override the copybook length, e.g. LRECL with trailing padding (use with `--allow-trailing`) |
| `--keep-going` | report bad records on stderr and continue |
| `-o FILE` | write to a file instead of stdout |

## register

Posts the Avro schema to `--registry`/subjects/`--subject`/versions. Do not put credentials in the
URL; it is refused. For HTTP Basic auth, set `KOPYBOOK_REGISTRY_USER` and
`KOPYBOOK_REGISTRY_PASSWORD`; credentials are sent only to an `https://` registry, and redirects
are not followed.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | `compat`: incompatible verdict |
| 2 | `decode`: at least one record could not be decoded |
| 3 | Pro command without `kopybook-pro` installed |
| 4 | Pro license missing, expired or invalid |
| 64 | bad option value |
| 65 | copybook syntax error or unsupported clause |
| 69 | `register`: Schema Registry unreachable or returned an error |
