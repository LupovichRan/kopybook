"""Builds docs/assets/demo.cast (asciicast v2) by running real kopybook commands, then agg -> demo.gif.

Deterministic: commands run for real, typing is simulated at a fixed speed.
Usage: python docs/demo/make_demo.py [--gif]
"""
import json, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KOPYBOOK = [sys.executable, "-m", "kopybook"]
CMDS = [
    ("kopybook layout corpus/copybooks/41_copy_replacing.cpy -I corpus/copybooks/copylib",
     ["layout", "corpus/copybooks/41_copy_replacing.cpy", "-I", "corpus/copybooks/copylib"]),
    ("kopybook decode corpus/copybooks/19_redefines_multi.cpy corpus/data/19_redefines_multi.bin \\\r\n"
     "    --redefines-when PAYMENT-DATA=IS-PAYMENT --redefines-when REFUND-DATA=IS-REFUND | head -3",
     ["decode", "corpus/copybooks/19_redefines_multi.cpy", "corpus/data/19_redefines_multi.bin",
      "--redefines-when", "PAYMENT-DATA=IS-PAYMENT", "--redefines-when", "REFUND-DATA=IS-REFUND"], 3),
    ("kopybook schema corpus/copybooks/19_redefines_multi.cpy -f avro | head -20",
     ["schema", "corpus/copybooks/19_redefines_multi.cpy", "-f", "avro"], 20),
]
PROMPT = "\x1b[1;32m$\x1b[0m "


def main():
    t, ev = 0.4, []
    for spec in CMDS:
        shown, args = spec[0], spec[1]
        limit = spec[2] if len(spec) > 2 else None
        ev.append([round(t, 3), "o", PROMPT]); t += 0.3
        for ch in shown:
            ev.append([round(t, 3), "o", ch]); t += 0.025
        ev.append([round(t, 3), "o", "\r\n"]); t += 0.4
        out = subprocess.run(KOPYBOOK + args, cwd=ROOT, capture_output=True, text=True, check=True).stdout
        lines = out.splitlines()[:limit] if limit else out.splitlines()
        for ln in lines:
            ev.append([round(t, 3), "o", ln + "\r\n"]); t += 0.04
        t += 2.2
    ev.append([round(t, 3), "o", PROMPT])
    cast = os.path.join(ROOT, "docs", "assets", "demo.cast")
    os.makedirs(os.path.dirname(cast), exist_ok=True)
    with open(cast, "w") as f:
        f.write(json.dumps({"version": 2, "width": 110, "height": 30, "title": "kopybook demo",
                            "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"}}) + "\n")
        for e in ev:
            f.write(json.dumps(e) + "\n")
    print(f"wrote {cast} ({t:.1f}s)")
    if "--gif" in sys.argv:
        agg = shutil.which("agg") or os.path.expanduser("~/.local/bin/agg")
        subprocess.run([agg, "--font-size", "14", "--idle-time-limit", "3", cast,
                        os.path.join(ROOT, "docs", "assets", "demo.gif")], check=True)
        print("wrote docs/assets/demo.gif")


if __name__ == "__main__":
    main()
