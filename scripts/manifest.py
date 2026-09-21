#!/usr/bin/env python3
"""manifest.py — project sources/manifest.json -> sources/manifest.yaml.

manifest.json is the hand-of-record registry, mutated via scripts/fetch.py
--promote; this module only projects it to the human-readable YAML ledger.
Hashes live in the JSON (computed at fetch, never typed here). Why thin: the
earlier manifest.py carried huge literal FETCHED/CANDIDATES lists that
repeatedly corrupted under edit — the JSON registry is the single source of
truth, and this projects it.

Usage: python3 scripts/manifest.py          rewrite sources/manifest.yaml
       python3 scripts/manifest.py --check  verify YAML matches projection, write nothing
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MJSON = os.path.join(ROOT, "sources", "manifest.json")
MYAML = os.path.join(ROOT, "sources", "manifest.yaml")

_ORDER = ["id", "file", "url", "url_text", "publisher", "title", "published",
          "class", "licence", "extract", "status", "sha256", "note"]

# NOTE: chars that break YAML plain scalars in this ledger's value position
# (": " in titles was the real yaml.safe_load failure); json.dumps output is a
# valid YAML double-quoted scalar.
_NEEDS_QUOTE = set(":#'\"{}[]")

USAGE = "usage: python3 scripts/manifest.py [--check]"


def _scalar(v):
    s = str(v)
    if s != s.strip() or any(c in _NEEDS_QUOTE for c in s):
        return json.dumps(s)
    return s


def _project(rows):
    ids = [r["id"] for r in rows]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise SystemExit("duplicate ids in %s: %s" % (MJSON, ", ".join(dupes)))
    lines = [
        "# sources/manifest.yaml - provenance ledger (projected from manifest.json).",
        "# Sample -> source_id -> sha256_source; no orphan samples.",
        "# classes: key_judgements | full_assessment | confidence_statements |",
        "#   negative_us | negative_press | negative_llm | spec | contrast_misc | ca_ic | au_ic",
        "", "sources:", "",
    ]
    for r in rows:
        lines.append("  - id: %s" % _scalar(r["id"]))
        for k in _ORDER:
            if k == "id" or k not in r or r[k] in (None, ""):
                continue
            lines.append("    %s: %s" % (k, _scalar(r[k])))
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv):
    if argv not in ([], ["--check"]):
        raise SystemExit(USAGE)
    with open(MJSON) as f:
        rows = json.load(f)
    text = _project(rows)
    if argv == ["--check"]:
        if not os.path.exists(MYAML):
            raise SystemExit("%s missing; run scripts/manifest.py" % MYAML)
        with open(MYAML, "rb") as f:
            on_disk = f.read()
        if on_disk != text.encode("utf-8"):
            raise SystemExit("%s drifted from manifest.json projection; rerun scripts/manifest.py" % MYAML)
        print("ok: %s matches projection (%d rows)" % (MYAML, len(rows)))
        return
    with open(MYAML, "w") as f:
        f.write(text)
    print("wrote %s (%d rows)" % (MYAML, len(rows)))


if __name__ == "__main__":
    main(sys.argv[1:])
