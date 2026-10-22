# Supported COBOL — what Kopybook decodes, and how

Everything below is covered by the regression corpus (`corpus/`) and decoded identically by the
Python toolkit and the Java Kafka Connect plugin. Anything not listed is either rejected with an
error that names the line (when it would change the byte layout) or ignored (when it does not).
Semantics follow IBM Enterprise COBOL for z/OS.

## Source format
| Item | Support |
|---|---|
| Fixed format: cols 1-6 sequence, col 7 indicator, cols 8-72 code, 73-80 ignored | yes (auto-detected) |
| Comment lines `*` and `/` in col 7, debug lines `D` (treated as comments) | yes |
| Continuation `-` in col 7, including split literals | yes |
| Free format, `*>` floating comments, lower case | yes |
| Several 01 records in one copybook | yes, choose with `--record` / `copybook.record` (default: first) |
| Fragment without an 01 (starts at 05) | yes, wrapped in a synthetic `RECORD` |
| `COPY name [OF\|IN lib] [SUPPRESS] [REPLACING ...]` | yes: members searched on the copy path (`-I` / `copybook.include.path`, then the copybook's own directory), names tried as-is/lower/upper with `.cpy .cbl .cob .copy .txt` or no extension, `lib` as a subdirectory; nested COPY (depth 16, recursion rejected) |
| `REPLACING` operands | `==pseudo-text==` (single line), words, literals; `LEADING` / `TRAILING` partial-word; IBM-style `:TAG:` partial-word replacement inside words; `BY ====` deletes |

## Data description clauses
| Clause | Support |
|---|---|
| Levels 01-49, 77 | yes |
| Level 88 condition names (VALUE, VALUES ARE, THRU/THROUGH, several values) | parsed, carried as schema metadata (`cobol.conditions88`) |
| Level 66 RENAMES ... THRU | parsed and validated, carried as record metadata (`cobol.renames66`) |
| FILLER and unnamed items | skipped by default, `filler_<offset>` with `--keep-filler` |
| `PIC X`, `PIC A`, repeat counts `X(n)`, mixed `X(5)X(5)` | string |
| `PIC 9`, `S9`, `V` (implied decimal), up to 38 digits | number (see type mapping) |
| Numeric-edited (`Z`, `*`, `$`, `,`, `.`, `+`, `-`, `CR`, `DB`, `B`, `0`, `/`) | carried as text |
| `USAGE DISPLAY` zoned decimal, sign overpunch trailing (default) | yes |
| `SIGN IS LEADING` / `TRAILING`, `SEPARATE CHARACTER` | yes |
| `COMP`, `COMP-4`, `BINARY`, `COMPUTATIONAL[-4]` (2/4/8 bytes by digits) | yes, value limited to PIC digits (TRUNC(STD)); `--trunc bin` for full range |
| `COMP-5` / `COMPUTATIONAL-5` native binary | yes, full storage range |
| `COMP-3` / `PACKED-DECIMAL` (sign C/F/A/E positive, D/B negative) | yes, up to 31+ digits |
| `COMP-1` / `COMP-2` (IBM hexadecimal floating point) | decode yes (double); Java encoder not yet |
| USAGE on a group (inherited by children) | yes |
| `OCCURS n TIMES` (also nested, also of groups), `INDEXED BY`, `ASCENDING KEY` | array |
| `OCCURS m TO n DEPENDING ON x` | variable-length array; items after the table (variable location) are supported |
| `REDEFINES` (elementary, group, multiple alternatives, OCCURS inside an alternative) | every view as an optional field (`all`, default), or only the original (`first`); with view selection (below) only the view that applies |
| `VALUE`, `JUSTIFIED`, `BLANK WHEN ZERO`, `GLOBAL`, `EXTERNAL` | accepted, no effect on decoding |
| `SYNCHRONIZED` | **rejected** (would add slack bytes) |
| `PIC P` scaling, `PIC N`/`G`, `NATIONAL`, `DISPLAY-1`, `INDEX`, `POINTER`, `PIC E` | **rejected** |
| REDEFINES of variable-length data | **rejected** |

## Code pages
Any Python codec / Java charset. Tested: **cp037** (default), **cp1140** (cp037 + euro at 0x9F),
**cp500**. Aliases in Java: cp037→IBM037, cp1140→IBM01140, cp500→IBM500, cp273, cp1047, cp1141, cp1148, cp875.

## Type mapping
| COBOL | Avro | JSON Schema | Kafka Connect |
|---|---|---|---|
| PIC X / A / edited | `string` | string, maxLength | STRING |
| integer, max value fits int32 | `int` | integer + min/max | INT32 |
| integer, fits int64 | `long` | integer + min/max | INT64 |
| larger integer (e.g. S9(19), unsigned 8-byte COMP-5) | `bytes` decimal(p,0) | string (pattern) | Decimal(0) |
| V (scaled) | `bytes` decimal(p,s) | string `^-?[0-9]{1,p-s}\.[0-9]{s}$` | Decimal(s) + `connect.decimal.precision` |
| COMP-1 / COMP-2 | `double` | number | FLOAT64 |
| group | record | object | STRUCT |
| OCCURS | array | array, minItems/maxItems | ARRAY |
| REDEFINES participant (strategy `all`) | `["null", T]`, default null | nullable | optional |

Range is by PIC digits for DISPLAY/COMP-3/COMP (TRUNC(STD)) and by storage size for COMP-5.
Field names: lower case, `-` → `_`, leading digit → `f_`. Nested record names: PascalCase path
(`BillTo_Addr`), so they stay stable when unrelated groups are added. `--nullable-all` makes every
field optional so new fields stay BACKWARD compatible.

## Framing
Per message: one record. `framing=rdw` (Connect) / `--rdw` (CLI) for IBM variable-length records
with a 4-byte RDW. Trailing bytes after the record are an error unless `allow.trailing.bytes=true`.

## Errors
Every decode error names the COBOL path and byte offset, e.g.
`PACKED-REC.P-ODD-S @ offset 0: invalid packed sign nibble 5 in 000123455`.
In Connect they surface as `DataException`, so `errors.tolerance` and the DLQ work as usual.
The SMT also has `on.error=skip`.

## REDEFINES view selection

By default every REDEFINES view is decoded and a view that cannot be read becomes null. When a
record-type field says which view applies, name it:

```
kopybook decode trans.cpy trans.bin --redefines-when PAYMENT-DATA=IS-PAYMENT \
                                --redefines-when NOTE-DATA=REC-TYPE:N|X
# Connect: redefines.when=PAYMENT-DATA=IS-PAYMENT,NOTE-DATA=REC-TYPE:N|X
```

- A condition is a level-88 name (its VALUE / THRU list is used) or `FIELD:V1|V2`.
- In a REDEFINES group with at least one rule: a view with a rule is decoded only when the rule
  holds, and it is decoded **strictly** (bad bytes are an error, not null). If no rule in the group
  holds, the views without a rule are decoded (the "otherwise" view). All other views are null.
- The selector field must come before the REDEFINES group in the record.
- The Avro / JSON schema does not change: views stay optional.
