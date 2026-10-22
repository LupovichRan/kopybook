# Status (local only, nothing published)

| Suite | Result |
|---|---|
| Python, Community (`python/tests`) | 325 passed, 5 skipped (the skips need optional tools) |
| Java (`java`, `mvn test`) | 303 passed |
| End-to-end (`integration/roundtrip.py`, Kafka + Schema Registry + Connect 7.8.0, all 43 cases) | 1,075/1,075 records match the golden JSON; 54/54 live-registry compat verdicts agree (with Pro installed) |

The corpus has 42 copybooks (plus 4 COPY members in `corpus/copybooks/copylib/`), 43 cases and
1,075 records. All of it is synthetic.

Not supported yet (rejected with a clear error): SYNC, national/DBCS (N/G),
PIC P scaling, external floating point, REDEFINES of variable-length data, and multi-line
pseudo-text.
