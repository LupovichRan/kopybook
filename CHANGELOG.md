# Changelog

All notable changes to Kopybook are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- Field errors no longer include field data: no raw bytes (hex or otherwise), no decoded or
  encoded values and no text. This covers COMP-3, zoned and separate-sign errors (which now give
  the byte position and the kind of fault), the binary `exceeds PIC digits` error under
  `trunc=std`, the ODO counter range error, text that is not valid in the code page, and all
  encode errors. Messages still name the COBOL path, byte offset, field length and reason.
- Python `invalid RDW` errors (`--rdw`) no longer print the RDW bytes; they give the offset only.

### Fixed

- Java `FieldCodec.packed` checks the offset and length against the buffer and throws
  `FieldException` instead of `ArrayIndexOutOfBoundsException`. Python already raised a field or
  decode error here; both now have tests.
- Python wraps code-page errors in text fields in a field error, as Java already did.
- Python record encode reports a non-numeric value (bad string, NaN or infinity, or a
  non-number type) for a numeric or COMP-1/COMP-2 field as `PATH: value is not a number` (or
  `not a finite number`), as Java does, instead of a raw `ValueError`, `TypeError` or
  `InvalidOperation` that could quote the input.

### Documentation

- SPEC: COMP-3 byte length (`digits // 2 + 1`), `0D` decodes as 0 on signed fields, and `D`/`B`
  signs are invalid on unsigned fields.

## [0.1.2] - 2026-10-24

### Security

- **`kopybook register` no longer accepts credentials in the `--registry` URL.** In 0.1.1 and
  earlier, credentials written into the URL (for example `https://user:password@host`) were not
  used to authenticate; they were treated as part of the host name and could appear in error
  messages and logs, or be sent in a DNS lookup. Such URLs are now refused, without echoing them.
  Credentials are read from `KOPYBOOK_REGISTRY_USER` and `KOPYBOOK_REGISTRY_PASSWORD`, sent only
  as an HTTP Basic `Authorization` header to an `https://` registry, and error messages never
  include the URL or credentials. Only `kopybook register` is affected. If you ever passed
  credentials in `--registry`, upgrade and rotate them.

### Fixed

- Packed decimal (COMP-3): an unsigned field (`PIC 9`) with a negative sign nibble (`D` or `B`) was
  decoded as a negative number. It is now rejected as invalid data, in both Python and Java.
- Packed decimal: a value with more digits than the PIC allows (a non-zero spare leading half-byte
  for an even digit count, for example `PIC 9(2)` holding `12 3C`) or a field whose byte length does
  not match the PIC is now rejected instead of decoded. In Java, such values no longer escape as an
  `ArithmeticException`; they are reported as decode errors, so `on.error=skip` and optional
  REDEFINES views handle them.
- Packed decimal: an empty field now raises a field error instead of an internal `IndexError`.
- Packed decimal: a negative zero (`0D`) decodes as `0`.

## [0.1.1] - 2026-10-22

### Security

- **COPY member resolution no longer reads files outside the copy library.** In 0.1.0, a crafted
  copybook could use a `COPY` statement with a path (for example `COPY '../../etc/hostname'`) to
  read any file the process could read, and the file's contents could be echoed back in the
  parser's error message. This affects the 0.1.0 Python CLI and library and the 0.1.0 Java parser,
  including the Kafka Connect converter and SMT, whenever they process copybooks from an untrusted
  source. COPY member and library names containing `/`, `\`, `..`, NUL or an absolute path are now
  rejected; resolved members must stay inside a configured copy directory (symlink escapes are
  rejected); and error messages never include member file contents.
- **Record length is now capped.** Any single field or record larger than 1,000,000 bytes (for
  example `PIC X(999999999)` or an oversized OCCURS) is rejected with a clear error before memory is
  allocated. The Java parser now computes sizes in `long` to avoid integer overflow.

Users of 0.1.0 who process copybooks from untrusted sources should upgrade to 0.1.1.

### Changed

- Jackson (test scope only) upgraded from 2.17.2 to 2.18.12 through `jackson-bom`, so every
  `com.fasterxml.jackson.*` artifact is pinned to one version. The Connect plugin's runtime
  dependencies are unchanged.
- The Pro schema-compatibility tests are opt-in: the Java suite reads the Pro corpus only from the
  `-Dkopybook.pro.compat` system property and reports a skipped test when it is not set, and
  `integration/roundtrip.py` uses Pro only when the `KOPYBOOK_PRO` environment variable is set.
- Version is now `0.1.1` everywhere (the Java artifact is no longer a `-SNAPSHOT`).

## [0.1.0] - 2026-10-22

### Added

- First public release.
- COBOL copybook parser (fixed and free format, COPY ... REPLACING, levels 66 and 88, OCCURS and
  OCCURS DEPENDING ON, REDEFINES with view selection).
- EBCDIC decoder and encoder: zoned decimal (all sign forms), COMP-3, COMP/COMP-4/BINARY,
  COMP-5, COMP-1/COMP-2 (IBM hex float), RDW framing, and EBCDIC code pages including cp037,
  cp1140 and cp500.
- Avro and JSON Schema generation with exact decimal precision and scale.
- `kopybook` CLI (`schema`, `layout`, `decode`, `encode`, `register`) and a Docker image.
- Kafka Connect Converter and Value/Key SMTs with no runtime dependencies beyond the Connect API.
- Public synthetic golden corpus (42 copybooks, 43 cases, 1,075 records) decoded identically by
  the Python and Java implementations.

[Unreleased]: https://github.com/LupovichRan/kopybook/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/LupovichRan/kopybook/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/LupovichRan/kopybook/compare/1c80067...v0.1.1
[0.1.0]: https://github.com/LupovichRan/kopybook/commit/1c80067
