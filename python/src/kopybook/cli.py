"""kopybook command line."""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from . import __version__, avro, codec, jsonschema_gen, parser
from .model import CopybookError, DecodeError


_COPY_PATHS: list = []


def _load(path, record, fmt):
    return parser.parse_file(path, fmt, _COPY_PATHS).record(record)


def _schema_kwargs(a):
    return dict(meta=not a.no_meta, nullable_all=a.nullable_all, redefines=a.redefines,
                keep_filler=a.keep_filler, trunc=a.trunc)


def _avro(a, path):
    return avro.to_avro(_load(path, a.record, a.source_format), namespace=a.namespace, **_schema_kwargs(a))


def cmd_schema(a):
    root = _load(a.copybook, a.record, a.source_format)
    if a.format == "avro":
        s = avro.to_avro(root, namespace=a.namespace, **_schema_kwargs(a))
    else:
        s = jsonschema_gen.to_json_schema(root, **_schema_kwargs(a))
    text = json.dumps(s, indent=2, ensure_ascii=False)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


def _opts(a):
    return codec.Options(codepage=a.codepage, trim=a.trim, keep_filler=a.keep_filler,
                         redefines=a.redefines, trunc=a.trunc,
                         redefines_when=codec.parse_when(getattr(a, "redefines_when", None) or []) or None)


def cmd_decode(a):
    root = _load(a.copybook, a.record, a.source_format)
    data = open(a.data, "rb").read()
    recs = codec.iter_rdw(data) if a.rdw else codec.iter_fixed(data, a.record_length or root.size)
    o = _opts(a)
    o.allow_trailing = a.allow_trailing
    out = open(a.output, "w", encoding="utf-8") if a.output else sys.stdout
    bad = 0
    for i, r in enumerate(recs):
        try:
            v = codec.decode(root, r, o)
            out.write(json.dumps(codec.to_jsonable(v), ensure_ascii=False) + "\n")
        except DecodeError as e:
            bad += 1
            print(f"record {i}: {e}", file=sys.stderr)
            if not a.keep_going:
                return 2
    return 2 if bad else 0


def cmd_encode(a):
    root = _load(a.copybook, a.record, a.source_format)
    o = _opts(a)
    recs = [codec.encode(root, json.loads(l), o) for l in open(a.jsonl, encoding="utf-8") if l.strip()]
    data = codec.write_rdw(recs) if a.rdw else b"".join(recs)
    open(a.output, "wb").write(data)
    print(f"wrote {len(recs)} records ({len(data)} bytes) to {a.output}", file=sys.stderr)
    return 0


def cmd_layout(a):
    root = _load(a.copybook, a.record, a.source_format)
    print(f"{'OFFSET':>6} {'SIZE':>5}  {'LVL':>3}  {'FIELD':<40} {'PIC':<16} USAGE")
    for n in root.walk():
        if n is root:
            continue
        ind = "  " * (len(n.path().split(".")) - 2)
        occ = ""
        if n.occurs_max is not None:
            occ = f" OCCURS {n.occurs_min}..{n.occurs_max}" + (f" DEP {n.depending_on}" if n.depending_on else "")
        red = f" REDEFINES {n.redefines}" if n.redefines else ""
        print(f"{n.offset + 1:>6} {n.size:>5}  {n.level:>3}  {(ind + n.name):<40} "
              f"{(n.pic.raw if n.pic else ''):<16} {'' if n.children else n.eff_usage}{occ}{red}")
    print(f"record length: {root.size} bytes" + (f" (min {root.min_size}, variable)" if root.variable else ""))
    return 0


def _pro():
    try:
        from kopybook_pro import cli as pro_cli
    except ImportError:
        return None
    return pro_cli


COMPAT_LEVELS = ("BACKWARD", "BACKWARD_TRANSITIVE", "FORWARD", "FORWARD_TRANSITIVE", "FULL", "FULL_TRANSITIVE", "NONE")


def cmd_compat(a):
    pro = _pro()
    if pro is None:
        print("kopybook compat is a Kopybook Pro feature (schema-evolution checker). Install kopybook-pro to use it.",
              file=sys.stderr)
        return 3
    return pro.compat_command(a, _avro, _load)


def cmd_license(a):
    pro = _pro()
    if pro is None:
        print("Kopybook Pro is not installed.", file=sys.stderr)
        return 3
    return pro.license_command(a)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # never forward the Authorization header to another location


def _registry_request(registry, subject, body):
    """Build the POST request. Errors never include the URL or credentials."""
    try:
        parts = urllib.parse.urlsplit(registry)
    except ValueError:
        raise ValueError("--registry is not a valid URL") from None
    if "@" in parts.netloc:
        raise ValueError("--registry must not contain credentials; "
                         "set KOPYBOOK_REGISTRY_USER and KOPYBOOK_REGISTRY_PASSWORD instead")
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("--registry must be an http:// or https:// URL")
    headers = {"Content-Type": "application/vnd.schemaregistry.v1+json"}
    user = os.environ.get("KOPYBOOK_REGISTRY_USER")
    password = os.environ.get("KOPYBOOK_REGISTRY_PASSWORD")
    if user or password:
        if not (user and password):
            raise ValueError("set both KOPYBOOK_REGISTRY_USER and KOPYBOOK_REGISTRY_PASSWORD, or neither")
        if parts.scheme != "https":
            raise ValueError("refusing to send registry credentials over plain http; use an https:// --registry")
        headers["Authorization"] = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
    return urllib.request.Request(f"{registry.rstrip('/')}/subjects/{subject}/versions", data=body,
                                  method="POST", headers=headers)


def cmd_register(a):
    s = _avro(a, a.copybook)
    body = json.dumps({"schemaType": "AVRO", "schema": json.dumps(s)}).encode()
    req = _registry_request(a.registry, a.subject, body)
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=10) as r:
            print(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"error: Schema Registry returned HTTP {e.code}", file=sys.stderr)
        return 69
    except Exception as e:  # URLError, InvalidURL, timeouts: the text may contain the URL
        print(f"error: could not reach Schema Registry ({type(e).__name__})", file=sys.stderr)
        return 69
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="kopybook", description="COBOL copybook to Kafka toolkit")
    p.add_argument("--version", action="version", version=f"kopybook {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, schema=True):
        sp.add_argument("--record", help="01-level record name (default: first)")
        sp.add_argument("--source-format", default="auto", choices=["auto", "fixed", "free"])
        sp.add_argument("-I", "--copy-path", action="append", default=[],
                        help="directory searched for COPY members (repeatable; the copybook's own dir is always searched)")
        sp.add_argument("--redefines", default="all", choices=["all", "first"])
        sp.add_argument("--keep-filler", action="store_true")
        sp.add_argument("--trunc", default="std", choices=["std", "bin"],
                        help="COMP/COMP-4 value range: std = PIC digits, bin = full storage")
        if schema:
            sp.add_argument("--namespace")
            sp.add_argument("--no-meta", action="store_true", help="omit the 'cobol' metadata properties")
            sp.add_argument("--nullable-all", action="store_true",
                            help="make every field optional (null default) so fields can be added later")

    def data_opts(sp):
        sp.add_argument("--codepage", default="cp037", help="cp037 (default), cp1140, cp500, cp273, ...")
        sp.add_argument("--trim", default="right", choices=["right", "both", "none"])
        sp.add_argument("--redefines-when", action="append", metavar="VIEW=COND",
                        help="decode a REDEFINES view only when COND holds: an 88-level name, or FIELD:V1|V2 (repeatable)")

    s = sub.add_parser("schema", help="copybook -> Avro or JSON Schema")
    s.add_argument("copybook")
    s.add_argument("--format", "-f", default="avro", choices=["avro", "json"])
    s.add_argument("--output", "-o")
    common(s)
    s.set_defaults(fn=cmd_schema)

    s = sub.add_parser("decode", help="EBCDIC file -> JSON lines")
    s.add_argument("copybook")
    s.add_argument("data")
    s.add_argument("--rdw", action="store_true", help="variable-length records with 4-byte RDW")
    s.add_argument("--record-length", type=int)
    s.add_argument("--allow-trailing", action="store_true")
    s.add_argument("--keep-going", action="store_true")
    s.add_argument("--output", "-o")
    common(s, schema=False)
    data_opts(s)
    s.set_defaults(fn=cmd_decode)

    s = sub.add_parser("encode", help="JSON lines -> EBCDIC file (test data)")
    s.add_argument("copybook")
    s.add_argument("jsonl")
    s.add_argument("--output", "-o", required=True)
    s.add_argument("--rdw", action="store_true")
    common(s, schema=False)
    data_opts(s)
    s.set_defaults(fn=cmd_encode)

    s = sub.add_parser("layout", help="print the byte layout of a copybook")
    s.add_argument("copybook")
    common(s, schema=False)
    s.set_defaults(fn=cmd_layout)

    s = sub.add_parser("compat", help="[Pro] copybook v1 [v2 ...] vN: Schema Registry + wire-layout verdict")
    s.add_argument("copybooks", nargs="+", help="oldest first, newest last")
    s.add_argument("--level", default="BACKWARD", choices=list(COMPAT_LEVELS))
    s.add_argument("--json", action="store_true")
    s.add_argument("--allow-wire-break", action="store_true")
    s.add_argument("--registry", help="Schema Registry URL for a live check")
    s.add_argument("--subject")
    s.add_argument("--license", help="Pro license key or key file (default: $KOPYBOOK_LICENSE, ~/.config/kopybook/license.key)")
    common(s)
    s.set_defaults(fn=cmd_compat)

    s = sub.add_parser("license", help="[Pro] show the installed license")
    s.add_argument("--license")
    s.set_defaults(fn=cmd_license)

    s = sub.add_parser("register", help="register the Avro schema in Schema Registry")
    s.add_argument("copybook")
    s.add_argument("--registry", required=True,
                   help="Schema Registry URL, without credentials (use $KOPYBOOK_REGISTRY_USER / $KOPYBOOK_REGISTRY_PASSWORD)")
    s.add_argument("--subject", required=True)
    common(s)
    s.set_defaults(fn=cmd_register)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    _COPY_PATHS[:] = getattr(a, "copy_path", []) or []
    try:
        return a.fn(a)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 64
    except CopybookError as e:
        print(f"copybook error: {e}", file=sys.stderr)
        return 65


if __name__ == "__main__":
    sys.exit(main())
