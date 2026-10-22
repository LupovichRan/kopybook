# Quickstart

## Install

=== "pip"

    ```bash
    pip install ./python          # from a checkout; Python 3.10+
    kopybook --version
    ```

=== "Docker"

    ```bash
    docker build -t kopybook .
    alias kopybook='docker run --rm -v "$PWD:/work" -w /work kopybook'
    ```

## 1. Look at the layout

```bash
kopybook layout corpus/copybooks/30_customer_master.cpy
```

This prints the offset, size, level, PIC and USAGE of every field, followed by the record
length. Compare the length with the LRECL of your dataset. A mismatch nearly always means the
wrong copybook or a missing COPY member.

## 2. Generate a schema

```bash
kopybook schema corpus/copybooks/31_insurance_claim.cpy -f avro --namespace acme.claims > claim.avsc
kopybook schema corpus/copybooks/31_insurance_claim.cpy -f json > claim.schema.json
```

## 3. Decode a file

```bash
kopybook decode corpus/copybooks/31_insurance_claim.cpy corpus/data/31_insurance_claim.bin --rdw | head -2
```

Fixed-length files need no flag, because the record length comes from the copybook. Use `--rdw`
for variable-length (RECFM=VB) transfers that keep the record descriptor word.

## 4. Copybooks that use COPY

```bash
kopybook layout -I corpus/copybooks/copylib corpus/copybooks/41_copy_replacing.cpy
```

## 5. Pick the right REDEFINES view

```bash
kopybook decode corpus/copybooks/19_redefines_multi.cpy corpus/data/19_redefines_multi.bin \
  --redefines-when PAYMENT-DATA=IS-PAYMENT --redefines-when REFUND-DATA=IS-REFUND \
  --redefines-when NOTE-DATA=IS-NOTE
```

## 6. Register in Schema Registry

```bash
kopybook register corpus/copybooks/30_customer_master.cpy \
  --registry http://localhost:8081 --subject customers-value
```

Next: run the same decoding inside [Kafka Connect](connect.md).
