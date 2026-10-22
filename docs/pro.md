# Kopybook Pro: schema-evolution checker

Copybooks change: a field grows, a FILLER is carved up, a table gets more occurrences. Schema
Registry checks only the Avro side of such a change. It cannot see that every later byte has
moved, and that the consumer will decode garbage.

`kopybook compat` (part of the commercial **Kopybook Pro** add-on, package `kopybook-pro`) reports both sides:

```
$ kopybook compat balance_v1.cpy balance_v2.cpy --level BACKWARD
Schema Registry BACKWARD: COMPATIBLE
Semantic warnings (Avro accepts these, data meaning changes):
  - DECIMAL_SCALE_CHANGED at /balance: scale 2 -> 3: Avro accepts it, but bytes are re-interpreted (values change by a power of 10)
Wire layout: BREAKING (record length 5 -> 5)
  - CHANGED /balance: PIC S9(7)V99->S9(6)V9(3)
```

- Avro verdicts follow the Schema Registry rules: BACKWARD, FORWARD and FULL, plus their
  transitive variants. They are cross-checked against Confluent's own checker and a live
  registry.
- Wire-layout verdicts: IDENTICAL, ADDITIVE_SAME_LENGTH, APPEND_ONLY, BREAKING. Renames and
  FILLER carve-outs are recognised.
- `--registry URL --subject S` also asks your running registry.
- CI-friendly exit codes. The license key is verified offline, with no phone-home.
