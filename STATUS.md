# Status (0.1.3)

Test results for the current release. See [CHANGELOG.md](CHANGELOG.md) for what changed.

| Suite | Result |
|---|---|
| Python, Community (`python/tests`) | 478 passed, 5 skipped (the skips need optional tools) |
| Java (`java`, `mvn verify`) | 345 passed, 1 skipped (the Pro compat test runs only with `-Dkopybook.pro.compat`) |
| End-to-end, last run on 0.1.0 (`integration/roundtrip.py`, Kafka + Schema Registry + Connect 7.8.0, all 43 cases) | 1,075/1,075 records match the golden JSON; 54/54 live-registry compat verdicts agree (with Pro installed) |

The corpus has 42 copybooks (plus 4 COPY members in `corpus/copybooks/copylib/`), 43 cases and
1,075 records. All of it is synthetic.

Not supported yet (rejected with a clear error): SYNC, national/DBCS (N/G),
PIC P scaling, external floating point, REDEFINES of variable-length data, and multi-line
pseudo-text.
