#!/usr/bin/env python3
"""validate_corpus.py — corpus-wide invariant gate.

The enforcement layer: every check is a small function returning a list of
violation strings; main prints them grouped, then a summary line, and exits
nonzero when anything failed. Missing raw files are warnings (mid-rebuild is
a legitimate state); hash mismatches are errors.

Usage: python3 scripts/validate_corpus.py
"""
import glob
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "eval"))

import yardstick

MANIFEST = os.path.join(ROOT, "sources", "manifest.json")
MYAML = os.path.join(ROOT, "sources", "manifest.yaml")
SPLITS = ("train", "val", "test")
KJ_CLASSES = ("key_judgements", "confidence_statements")
LINEAGE_FIELDS = ("source_id", "lineage_source", "source")

# RATIONALE: synthetic prose must never bind invented conduct to a real
# entity unless the row's lineage points at the real source that documents
# the claim (the FCA final notice grounds "Fast Remit") — grounded-synthetic
# is allowed; fabricated binding to real entities is not. Map: entity
# surface -> lineage substring that grounds it. Extend as real entities
# enter the corpus.
REAL_ENTITY_DENYLIST = {
    "Fast Remit": "fca-fast-remit",
}

# 'MoD (mirror)' and 'MoD Defence Intelligence (mirror)' are one publisher.
_PUB_ALIASES = {"mod": "mod defence intelligence"}

WARNINGS = []
PARSE = []  # malformed-JSONL violations, recorded once per file at first read
_JCACHE = {}


def _rel(path):
    return os.path.relpath(path, ROOT)


def read_jsonl(path):
    """Rows of a JSONL ledger; malformed lines land in PARSE once."""
    if path not in _JCACHE:
        rows = []
        with open(path) as f:
            for n, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError as e:
                    PARSE.append("%s:%d: bad JSON (%s)" % (_rel(path), n, e))
        _JCACHE[path] = rows
    return _JCACHE[path]


def load_manifest():
    if "manifest" not in _JCACHE:
        with open(MANIFEST) as f:
            _JCACHE["manifest"] = json.load(f)
    return _JCACHE["manifest"]


def norm_publisher(p):
    """Publisher identity: lowercase, parentheticals stripped, aliased."""
    s = re.sub(r"\([^)]*\)", " ", (p or "").lower())
    s = re.sub(r"\s+", " ", s).strip()
    return _PUB_ALIASES.get(s, s)


# ---- a. manifest integrity ----

def check_manifest():
    v = []
    rows = load_manifest()
    ids = [r.get("id", "") for r in rows]
    for i in sorted(set(i for i in ids if ids.count(i) > 1)):
        v.append("manifest: duplicate id %r (x%d)" % (i, ids.count(i)))
    for r in rows:
        if r.get("status") != "fetched":
            continue
        for k in ("sha256", "file", "licence"):
            if not r.get(k):
                v.append("manifest: fetched row %r missing %s" % (r.get("id"), k))
    return v


# ---- b. manifest vs raw ----

def hash_coverage():
    """(verified, empty, mismatched, missing) over fetched manifest rows.

    verified/empty are id lists; mismatched/missing are detail strings.
    Shared with eval/report_gates.py — one hashing pass, two consumers.
    """
    verified, empty, mismatched, missing = [], [], [], []
    for r in load_manifest():
        if r.get("status") != "fetched":
            continue
        rid = r.get("id", "?")
        if not r.get("sha256"):
            empty.append(rid)
            continue
        path = os.path.join(ROOT, "raw", r.get("file") or "")
        if not r.get("file") or not os.path.isfile(path):
            missing.append("%s: raw/%s not on disk" % (rid, r.get("file")))
            continue
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != r["sha256"]:
            mismatched.append("%s: raw/%s sha256 %s != manifest %s"
                              % (rid, r["file"], h.hexdigest(), r["sha256"]))
        else:
            verified.append(rid)
    return verified, empty, mismatched, missing


def check_manifest_vs_raw():
    verified, empty, mismatched, missing = hash_coverage()
    WARNINGS.extend("raw: " + m for m in missing)
    # empty sha256 already an error in check_manifest; not repeated here
    return ["raw: " + m for m in mismatched]


# ---- c. unique ids per ledger ----

def _id_ledgers():
    pats = ("corpus/*.jsonl", "corpus/curated/*.jsonl",
            "corpus/tasks/sft*.jsonl", "extracted/*.segments.jsonl")
    out = []
    for p in pats:
        out.extend(sorted(glob.glob(os.path.join(ROOT, p))))
    return out


def check_unique_ids():
    # RATIONALE: gate scoped to every ledger with an id field, not one — a
    # uniqueness gate scoped to entities-only already failed once (duplicate
    # ids accumulated undetected in the unscanned ledgers).
    v = []
    for path in _id_ledgers():
        ids = [r["id"] for r in read_jsonl(path)
               if isinstance(r, dict) and "id" in r]
        if not ids:
            continue  # ledger without an id field
        seen, dup = set(), {}
        for i in ids:
            if i in seen:
                dup[i] = dup.get(i, 1) + 1
            seen.add(i)
        for i in sorted(dup):
            v.append("%s: duplicate id %r (x%d)" % (_rel(path), i, dup[i]))
    return v


# ---- d. split hygiene ----

def _split_rows(split):
    return read_jsonl(os.path.join(ROOT, "corpus", "%s.jsonl" % split))


def check_splits():
    v = []
    known = set(r.get("id") for r in load_manifest())
    where = {}   # source_id -> splits it appears in
    pubs = {}    # split -> normalized publishers
    for split in SPLITS:
        pubs[split] = set()
        for r in _split_rows(split):
            rid = r.get("id", "?")
            sid = r.get("source_id")
            if sid not in known:
                v.append("%s: %s: orphan source_id %r" % (split, rid, sid))
            if not r.get("origin"):
                v.append("%s: %s: origin missing" % (split, rid))
            if split in ("val", "test"):
                if r.get("origin") != "real":
                    v.append("%s: %s: origin %r != real" % (split, rid, r.get("origin")))
                if r.get("qa") != "pass":
                    v.append("%s: %s: qa %r != pass" % (split, rid, r.get("qa")))
            if sid:
                where.setdefault(sid, set()).add(split)
            pubs[split].add(norm_publisher(r.get("publisher")))
    for sid in sorted(where):
        if len(where[sid]) > 1:
            v.append("splits: source_id %r in %s (doc-grouping: exactly one split)"
                     % (sid, "+".join(sorted(where[sid]))))
    for p in sorted(pubs["test"] & (pubs["train"] | pubs["val"])):
        v.append("splits: test publisher %r also in train/val (holdout broken)" % p)
    return v


# ---- e. val/test leakage into training mixes ----

# Record separator between texts so adjacent rows never concatenate into a
# false substring hit.
_SEP = "\n\x1e\n"


def _assistant_texts(path):
    texts = []
    for r in read_jsonl(path):
        if "messages" in r:
            texts.extend(m.get("content", "") for m in r["messages"]
                         if m.get("role") == "assistant")
        elif "assistant" in r:
            texts.append(r["assistant"])
    return texts


def check_leakage():
    # RATIONALE: leakage scope is the CANONICAL mix only — corpus/train.jsonl,
    # corpus/tasks/mlx/train.jsonl, corpus/tasks/sft_all.jsonl. The
    # mlx_vj/mlx_cad/mlx_nm/mlx_terse/mlx_d1/mlx_curated dirs are frozen
    # deprecated snapshots that never train again; scanning them would only
    # manufacture unfixable violations. Do not scan them.
    v = []
    # Comparison runs through yardstick.norm_text on BOTH sides: a verbatim
    # test leak once evaded an exact gate through a single curly-quote variant.
    targets = [("corpus/train.jsonl",
                _SEP.join(yardstick.norm_text(r.get("text") or "")
                          for r in _split_rows("train")))]
    for rel in ("corpus/tasks/mlx/train.jsonl", "corpus/tasks/sft_all.jsonl"):
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            WARNINGS.append("leakage: %s absent, skipped" % rel)
            continue
        targets.append((rel, _SEP.join(
            yardstick.norm_text(t) for t in _assistant_texts(path))))
    for split in ("val", "test"):
        for r in _split_rows(split):
            t = (r.get("text") or "").strip()
            if not t:
                continue
            nt = yardstick.norm_text(t)
            for name, blob in targets:
                if nt and nt in blob:
                    v.append("%s: %s: text verbatim in %s"
                             % (split, r.get("id", "?"), name))
    return v


# ---- f. mlx valid.jsonl provenance ----

def _sft_provenance():
    """assistant text -> [sft_all rows], for joining messages-format rows
    (which carry no lineage fields) back to their provenance."""
    prov = {}
    for r in read_jsonl(os.path.join(ROOT, "corpus", "tasks", "sft_all.jsonl")):
        prov.setdefault(r.get("assistant", ""), []).append(r)
    return prov


def _is_synthetic(row):
    # Real-derived sft rows carry source_id and no origin; synthetic rows
    # carry origin ("synthetic") or lineage_source instead of source_id.
    if row.get("origin") not in (None, "real"):
        return True
    return not row.get("source_id")


def check_valid_synthetic():
    path = os.path.join(ROOT, "corpus", "tasks", "mlx", "valid.jsonl")
    if not os.path.isfile(path):
        WARNINGS.append("valid: corpus/tasks/mlx/valid.jsonl absent, skipped")
        return []
    v = []
    # RATIONALE: valid.jsonl is built by build_mlx.py directly from
    # corpus/val.jsonl (val-split documents, origin=real and qa=pass by
    # build_corpus's own gates), so membership there IS the provenance —
    # sft_all holds train-doc rows only and can never vouch for valid rows.
    val_texts = {r.get("text", "")
                 for r in read_jsonl(os.path.join(ROOT, "corpus", "val.jsonl"))}
    for n, r in enumerate(read_jsonl(path), 1):
        texts = [m.get("content", "") for m in r.get("messages", [])
                 if m.get("role") == "assistant"]
        t = texts[-1] if texts else ""
        if t not in val_texts:
            v.append("valid.jsonl row %d: assistant is not a corpus/val.jsonl "
                     "text (synthetic or stray): %r" % (n, t[:60]))
    return v


# ---- g. yardstick term + chrome ----

def check_yardstick():
    # RATIONALE: scope is the pipeline-emitted splits only. segment.py
    # guarantees term-presence and chrome-absence for every kj/cs record it
    # emits, so the splits are where a violation means a broken guarantee.
    # The hand-curated ledgers (corpus/curated/*, synthetic_aug) never made
    # that promise — 8 per cent of curated register prose legitimately carries
    # no explicit yardstick term — and extracted/*.segments.jsonl are pre-QA
    # intermediates. Would need segment.py to stop guaranteeing this to drop
    # the check.
    v = []
    paths = [os.path.join(ROOT, "corpus", "%s.jsonl" % s)
             for s in ("train", "val", "test")]
    for path in paths:
        for r in read_jsonl(path):
            if r.get("class") not in KJ_CLASSES:
                continue
            t = r.get("text") or r.get("assistant") or r.get("output") or ""
            rid = r.get("id", "?")
            if not yardstick.find_terms(t):
                v.append("%s: %s: no yardstick term" % (_rel(path), rid))
            if yardstick.CHROME_RE.search(t):
                v.append("%s: %s: page chrome in text" % (_rel(path), rid))
    return v


# ---- h. lints selftest ----

def check_lints_selftest():
    try:
        import lints
    except Exception as e:
        return ["lints: import failed: %r" % (e,)]
    fn = getattr(lints, "selftest", None)
    if fn is None:
        return ["lints: eval/lints.py has no selftest()"]
    try:
        ok = fn()
    except Exception as e:
        return ["lints: selftest() failed: %r" % (e,)]
    if ok is None or ok is True:
        return []
    if isinstance(ok, (list, tuple)):
        return ["lints: selftest: %s" % x for x in ok]
    return ["lints: selftest() returned %r" % (ok,)]


# ---- i. real-entity gate ----

def _grounded(row, needle):
    return any(needle in str(row.get(k, "")) for k in LINEAGE_FIELDS)


def check_entity_gate():
    # RATIONALE: a denylisted real entity may appear only in rows whose
    # lineage grounds it in the real source (see REAL_ENTITY_DENYLIST).
    # messages-format rows carry no lineage, so they are joined back to
    # sft_all by assistant text; an unjoinable mention is a violation.
    v = []
    files = [os.path.join(ROOT, "corpus", "negative_llm.jsonl"),
             os.path.join(ROOT, "corpus", "critique_task.jsonl")]
    files += sorted(glob.glob(os.path.join(ROOT, "corpus", "tasks", "**", "*.jsonl"),
                              recursive=True))
    prov = None
    for path in files:
        if not os.path.isfile(path):
            continue
        for n, r in enumerate(read_jsonl(path), 1):
            blob = json.dumps(r)
            for entity, needle in REAL_ENTITY_DENYLIST.items():
                if entity not in blob or _grounded(r, needle):
                    continue
                if "messages" in r:
                    if prov is None:
                        prov = _sft_provenance()
                    texts = [m.get("content", "") for m in r["messages"]
                             if m.get("role") == "assistant"]
                    joined = prov.get(texts[-1] if texts else "", [])
                    if any(_grounded(x, needle) for x in joined):
                        continue
                v.append("%s row %d: real entity %r without %r lineage"
                         % (_rel(path), n, entity, needle))
    return v


# ---- j. manifest.yaml ----

def check_manifest_yaml():
    v = []
    try:
        import yaml
    except ImportError:
        yaml = None
        WARNINGS.append("yaml: PyYAML unavailable, parse check skipped")
    if yaml is not None:
        try:
            with open(MYAML) as f:
                yaml.safe_load(f)
        except Exception as e:
            v.append("yaml: sources/manifest.yaml does not parse: %s" % e)
    # Cheap equivalent of scripts/manifest.py --check: byte-compare projection.
    try:
        import manifest as manifest_mod
        text = manifest_mod._project(load_manifest())
        with open(MYAML, "rb") as f:
            if f.read() != text.encode("utf-8"):
                v.append("yaml: manifest.yaml drifted from manifest.json "
                         "projection (rerun scripts/manifest.py)")
    except SystemExit as e:
        v.append("yaml: projection failed: %s" % e)
    except Exception as e:
        v.append("yaml: --check equivalent failed: %r" % (e,))
    return v


CHECKS = [
    ("a. manifest integrity", check_manifest),
    ("b. raw hashes vs manifest", check_manifest_vs_raw),
    ("c. unique ids per ledger", check_unique_ids),
    ("d. split hygiene", check_splits),
    ("e. val/test leakage", check_leakage),
    ("f. mlx valid provenance", check_valid_synthetic),
    ("g. yardstick/chrome", check_yardstick),
    ("h. lints selftest", check_lints_selftest),
    ("i. real-entity gate", check_entity_gate),
    ("j. manifest.yaml projection", check_manifest_yaml),
]


def main():
    total = 0
    for name, fn in CHECKS:
        try:
            v = fn()
        except Exception as e:
            v = ["check crashed: %r" % (e,)]
        if v:
            print("== %s: %d violation(s) ==" % (name, len(v)))
            for line in v:
                print("  " + line)
        total += len(v)
    if PARSE:
        print("== jsonl parse: %d violation(s) ==" % len(PARSE))
        for line in PARSE:
            print("  " + line)
        total += len(PARSE)
    for w in WARNINGS:
        print("warning: " + w)
    print("validate: %d violations" % total)
    return min(total, 1)


if __name__ == "__main__":
    sys.exit(main())
