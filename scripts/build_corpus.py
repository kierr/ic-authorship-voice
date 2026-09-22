#!/usr/bin/env python3
"""build_corpus.py — assemble corpus splits from extracted/*.segments.jsonl.

Grouping is by document: a source's items never split across splits.
Publisher-held-out test: HOLD_OUT_PUBLISHERS move entirely to test — the
generalisation signal (see AGENTS.md; at 7 docs, holding out Chilcot alone keeps
train large enough; ISC + Chilcot would remove too many training rows).

Split membership is sticky: corpus/splits.json maps source_id -> split and is
the durable assignment (a shuffle reshuffled val wholesale on any doc-count
change, contaminating val-based selection). Unseen docs: held-out publisher ->
test, else a stable hash of source_id -> val/train, so adding docs never
migrates existing ones.

origin: synthetic is enforced out of val/test; it may appear in train only.
qa=flag rows never enter any split. val/test rows whose exact text also
appears in train are dropped (verbatim cross-split leakage).

Usage: .venv/bin/python scripts/build_corpus.py
"""
import glob
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))
import yardstick  # norm_text/shingles: shared leak-gate comparison

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "extracted")
CORPUS = os.path.join(ROOT, "corpus")
SPLITS = os.path.join(CORPUS, "splits.json")
VAL_PCT = 15  # unseen doc -> val iff sha1(source_id) % 100 < VAL_PCT
HOLD_OUT_PUBLISHERS = {"Chilcot"}

PUBLISHER_KEYS = {
    "Intelligence and Security Committee": "ISC",
    "ISC": "ISC",
    "Review of Intelligence on WMD": "Butler Review",
    "The Report of the Iraq Inquiry (Chair: Sir John Chilcot)": "Chilcot",
    "National Crime Agency": "NCA",
    "HM Government": "September Dossier",
    # Both MoD variants ship in segments; one key so they count as one publisher.
    "MoD Defence Intelligence (mirror)": "MoD DI",
    "MoD (mirror)": "MoD DI",
}

# Positive stream allowlist — anything not positive or contrast is fatal.
# RATIONALE: full_assessment removed — segment.py never emits that class, so
# the >=40 target was never producible. Would need a long-form
# segmenter that emits full_assessment to re-add.
POSITIVE = {"key_judgements", "confidence_statements"}
# Contrast classes segment.py emits: register classifier, never the SFT splits.
CONTRAST = {"negative_us", "contrast_misc", "ca_ic", "au_ic",
            "negative_llm", "spec"}


def publisher_key(pub):
    return PUBLISHER_KEYS.get(pub, pub)


def load_splits():
    """Sticky split membership. Absent splits.json is seeded from the committed
    corpus/{train,val,test}.jsonl so cutover preserves today's membership
    exactly (zero churn)."""
    if os.path.exists(SPLITS):
        with open(SPLITS) as f:
            return json.load(f)
    splits = {}
    for split in ("train", "val", "test"):
        path = os.path.join(CORPUS, split + ".jsonl")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                sid = json.loads(line)["source_id"]
                if splits.get(sid, split) != split:
                    raise SystemExit("source_id %s maps to two splits: %s and %s"
                                     % (sid, splits[sid], split))
                splits[sid] = split
    return splits


def main():
    samples = []
    for p in sorted(glob.glob(os.path.join(EXT, "*.segments.jsonl"))):
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    samples.append(json.loads(line))

    by_doc = defaultdict(list)
    contrast = []
    flagged = []
    for s in samples:
        cls = s.get("class")
        if cls in POSITIVE:
            # RATIONALE: origin fail-closed — defaulting a missing origin to
            # "real" inverts the synthetic firewall (synthetic could reach
            # val/test). Would need origin stamped upstream at every emitter
            # plus a schema gate to relax.
            if "origin" not in s:
                raise SystemExit("positive row %s missing origin" % s.get("id", "?"))
            if s.get("qa") == "flag":
                flagged.append(s.get("id", "?"))  # flag rows never enter any split
                continue
            key = (publisher_key(s.get("publisher", "")), s["source_id"])
            by_doc[key].append(s)
        elif cls in CONTRAST:
            contrast.append(s)
        else:
            raise SystemExit("unknown class %r on row %s" % (cls, s.get("id", "?")))

    splits = load_splits()
    assigned = defaultdict(set)  # split name -> doc keys
    for k in sorted(by_doc):
        pub, sid = k
        split = splits.get(sid)
        if split is None:  # unseen doc: holdout first, then stable hash
            if pub in HOLD_OUT_PUBLISHERS:
                split = "test"
            elif int(hashlib.sha1(sid.encode()).hexdigest(), 16) % 100 < VAL_PCT:
                split = "val"
            else:
                split = "train"
            splits[sid] = split
        assigned[split].add(k)

    os.makedirs(CORPUS, exist_ok=True)
    with open(SPLITS, "w") as f:
        json.dump(splits, f, indent=2, sort_keys=True)
        f.write("\n")

    # Train texts gate val/test. Comparison is through yardstick.norm_text —
    # a verbatim test leak once evaded an exact gate through a single
    # curly-quote variant — and near-duplicates are caught by 12-token
    # shingle containment: consecutive-day DIS reissues are ~80% identical
    # (dis-ukraine-2024-09-01 vs -09-02) and Butler text is quoted inside
    # Chilcot rows, neither visible to exact equality.
    train_texts = set()
    train_shingles = set()
    for k in assigned["train"]:
        for s in by_doc[k]:
            train_texts.add(yardstick.norm_text(s["text"]))
            train_shingles.update(yardstick.shingles(s["text"]))

    def near_train(text):
        nt = yardstick.norm_text(text)
        if nt in train_texts:
            return "verbatim"
        sh = yardstick.shingles(text)
        if sh and len(sh & train_shingles) / len(sh) >= 0.8:
            return "near-dup"
        return None

    def emit(docs, path, allow_synth, gate_train=False):
        dropped = []
        seen = set()  # within-split exact dedupe (exec summary quoting vol IV)
        with open(path, "w") as f:
            for k in sorted(docs):  # sorted: deterministic byte order per run
                for s in by_doc[k]:
                    if s["origin"] != "real" and not allow_synth:
                        continue
                    nt = yardstick.norm_text(s["text"])
                    if nt in seen:
                        dropped.append(s["id"] + "(intra-dup)")
                        continue
                    if gate_train:
                        why = near_train(s["text"])
                        if why:
                            dropped.append("%s(%s)" % (s["id"], why))
                            continue
                    seen.add(nt)
                    f.write(json.dumps(s, ensure_ascii=False) + "\n")
        return dropped

    leaked = emit(assigned["train"], os.path.join(CORPUS, "train.jsonl"),
                  allow_synth=True)
    leaked += emit(assigned["test"], os.path.join(CORPUS, "test.jsonl"),
                   allow_synth=False, gate_train=True)
    leaked += emit(assigned["val"], os.path.join(CORPUS, "val.jsonl"),
                   allow_synth=False, gate_train=True)

    # Contrast / negative classes feed the register classifier, never the SFT splits.
    with open(os.path.join(CORPUS, "contrast.jsonl"), "w") as f:
        for s in contrast:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print("dropped %d qa=flag rows: %s" % (len(flagged), " ".join(flagged) or "-"))
    print("dropped %d duplicate/leaked rows: %s"
          % (len(leaked), " ".join(leaked) or "-"))
    print("documents  train=%d val=%d test=%d"
          % (len(assigned["train"]), len(assigned["val"]), len(assigned["test"])))
    print("test docs (held out publishers):", sorted(k[1] for k in assigned["test"]))
    for split in ("train", "val", "test"):
        path = os.path.join(CORPUS, split + ".jsonl")
        n = 0
        cc = Counter()
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                cc[r["class"]] += 1
                n += 1
        print("%-5s %-4d samples  %s" % (split, n, dict(cc)))
    print("contrast  samples:", len(contrast))


if __name__ == "__main__":
    sys.exit(main())
