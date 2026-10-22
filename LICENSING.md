# Licensing model (open core): DRAFT, not published

| Part | Where | License |
|---|---|---|
| **Community**: copybook parser (including COPY/REPLACING), EBCDIC decoder and encoder, REDEFINES view selection, Avro and JSON Schema generator, CLI (`schema`, `decode`, `encode`, `layout`, `register`), Kafka Connect Converter and SMT, Dockerfile, docs, and the public synthetic corpus | this repository | **Apache-2.0** (`LICENSE`, `NOTICE`) |
| **Pro**: schema-evolution checker (`kopybook compat` gives Schema Registry BACKWARD/FORWARD/FULL[_TRANSITIVE] verdicts, a wire-layout diff, semantic warnings and a live-registry check), offline license verification, and the evolution corpus | separate commercial package, not part of this repo | Proprietary (commercial license) |

Rules for this repository:
- No Pro code lives here, and no code here imports Pro code at module load. `kopybook compat` and
  `kopybook license` look for the optional `kopybook_pro` package at run time. Without it they print how
  to get Pro and exit with code 3.
- No third-party code is vendored. Cobrix was not used.
- The Connect plugin needs nothing at run time beyond the Kafka Connect API that the worker
  supplies.
