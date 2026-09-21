#!/usr/bin/env python3
"""build_mlx.py — corpus/tasks/mlx/{train,valid}.jsonl in mlx-lm chat format.

Reads corpus/tasks/sft_all.jsonl (build_sft_all.py) and emits the canonical
scripted mix as a DIRECTORY of train.jsonl + valid.jsonl:

  {"messages": [
      {"role":"system","content":REGISTER_SYSTEM},
      {"role":"user","content":"<task>"},
      {"role":"assistant","content":"<target>"}]}

The system message is forced to yardstick.REGISTER_SYSTEM for every row — one
shared register prompt for training, generation, and eval.

Split rules (both violated by the deprecated hand mixes mlx_vj/ etc.):
  document-grouped  a source_id appears in exactly one of train/valid. valid
                    source_ids come from corpus/splits.json "val" membership
                    when present, else ~10% of source_ids by sha1 hash.
  origin-filtered   valid contains ONLY origin=="real" rows; synthetic never
                    enters valid. Rows without a source_id (critique,
                    synthetic) go to train only.

Verified fine-tune recipe (against installed mlx-lm 0.31.3):
  python -m mlx_lm.lora --model mlx-community/LFM2.5-1.2B-Instruct-4bit \
    --train --data corpus/tasks/mlx --batch-size 1 --num-layers 8 \
    --iters 300 --max-seq-length 2048 --adapter-path adapters/<new-run-dir>
NOTE --data must be a directory (train/valid.jsonl), not a file, and each run
needs a fresh adapter directory — an in-place overwrite destroyed the mlx_vj
weights once.

Usage: .venv/bin/python scripts/build_mlx.py
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yardstick import REGISTER_SYSTEM
from yardstick import norm_text as yardstick_norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "corpus", "tasks", "sft_all.jsonl")
SPLITS = os.path.join(ROOT, "corpus", "splits.json")
OUT_DIR = os.path.join(ROOT, "corpus", "tasks", "mlx")


def val_source_ids(source_ids):
    if os.path.exists(SPLITS):
        with open(SPLITS) as f:
            sp = json.load(f)
        # Accept {"val": [source_id, ...]} or {source_id: "train"|"val"|"test"}.
        if isinstance(sp.get("val"), list):
            return set(sp["val"])
        return {k for k, v in sp.items() if v == "val"}
    # No splits.json: sticky ~10% by content hash (sha1, never hash() —
    # PYTHONHASHSEED salting reshuffles membership per run; AGENTS.md).
    val = {s for s in source_ids
           if int(hashlib.sha1(s.encode()).hexdigest(), 16) % 10 == 0}
    if source_ids and not val:  # tiny corpora can miss the hash bucket
        val = {min(source_ids,
                   key=lambda s: hashlib.sha1(s.encode()).hexdigest())}
    return val


def chat(r):
    return {"messages": [
        {"role": "system", "content": REGISTER_SYSTEM},
        {"role": "user", "content": r["user"]},
        {"role": "assistant", "content": r.get("assistant", "")}]}


SRC_OVERRIDE = None

def main():
    global SRC_OVERRIDE
    argv = sys.argv[1:]
    # Class-balance control (2026-08-23): oversight/strategy/inquiry sources
    # are cs-heavy and diluted the judgement density that drives register
    # scores (clean9 4/8 vs clean7-fable 8/8). --exclude-prefixes filters by
    # provenance; --out-dir writes an experimental variant without touching
    # the canonical mix.
    out_dir = OUT_DIR
    excl = []
    i = 0
    while i < len(argv):
        if argv[i] == "--out-dir" and i + 1 < len(argv):
            out_dir = os.path.join(ROOT, argv[i + 1]); i += 2
        elif argv[i] == "--exclude-prefixes" and i + 1 < len(argv):
            excl = [x for x in argv[i + 1].split(",") if x]; i += 2
        elif argv[i] == "--src" and i + 1 < len(argv):
            SRC_OVERRIDE = os.path.join(ROOT, argv[i + 1]); i += 2
        else:
            i += 1

    src_path = SRC_OVERRIDE or SRC
    if not os.path.exists(src_path):
        print("missing", src_path, file=sys.stderr)
        return 1
    with open(src_path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if excl:
        before = len(rows)
        rows = [r for r in rows
                if not any(str(r.get("source_id", "")).startswith(p) for p in excl)]
        print("excluded %d rows by source prefix" % (before - len(rows)))

    # RATIONALE: mask_term rows have bare-yardstick-term assistants; at ~half
    # the mix they re-taught the degenerate "[TERM]-echo" output the mlx_nm
    # rebalance fixed this, and a clean1 bench reproduced the
    # collapse ("The UK Key Judgement is: almost certain."). The chat mix is a
    # register-WRITING surface; mask stays an eval task. --include-mask
    # overrides for ablations. Would need a bench showing no echo with masks
    # included to reconsider.
    if "--include-mask" not in sys.argv:
        before = len(rows)
        rows = [r for r in rows if r.get("task") != "mask_term"]
        print("excluded %d mask_term rows (--include-mask to keep)"
              % (before - len(rows)))

    val_ids = val_source_ids({r["source_id"] for r in rows if "source_id" in r})
    train, valid, dropped = [], [], 0
    for r in rows:
        sid = r.get("source_id")
        if sid in val_ids:
            if r.get("origin") == "real":
                valid.append(r)
            else:
                # Synthetic derivative of a val document: dropping it (not
                # moving to train) preserves document-grouping, mirroring
                # build_corpus.py emit(..., allow_synth=False).
                dropped += 1
        else:
            train.append(r)

    # Intra-mix dedupe: duplicate train texts (cross-DOC repeats that survived
    # split-level gates, or one text yielding both task kinds) overweight
    # memorised content — drop later exact-duplicate assistants (normalised).
    seen = set()
    deduped = []
    for r in train:
        key = yardstick_norm(r.get("assistant", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    if len(deduped) != len(train):
        print("dropped %d duplicate-assistant train rows" % (len(train) - len(deduped)))
    train = deduped

    if not valid:
        # sft_all is built from corpus/train.jsonl only, so partitioning it by
        # splits.json cannot yield valid rows. The loss-monitoring split comes
        # from corpus/val.jsonl directly: val-split documents by definition,
        # real-only and qa-pass by build_corpus's own gates, formatted through
        # the same copy-task builder training uses.
        import build_tasks
        val_path = os.path.join(ROOT, "corpus", "val.jsonl")
        with open(val_path) as f:
            for line in f:
                rec = json.loads(line)
                task = build_tasks.make_copy_task(rec)
                task["origin"] = rec.get("origin", "real")
                valid.append(task)

    out_dir_final = out_dir
    os.makedirs(out_dir_final, exist_ok=True)
    for name, part in (("train.jsonl", train), ("valid.jsonl", valid)):
        with open(os.path.join(out_dir_final, name), "w") as f:
            for r in part:
                f.write(json.dumps(chat(r), ensure_ascii=False) + "\n")

    train_ids = {r["source_id"] for r in train if "source_id" in r}
    valid_ids = {r["source_id"] for r in valid if "source_id" in r}
    print("wrote %s  train=%d valid=%d dropped_synth_on_val_doc=%d" % (
        out_dir_final, len(train), len(valid), dropped))
    print("source_ids  train=%d valid=%d overlap=%d" % (
        len(train_ids), len(valid_ids), len(train_ids & valid_ids)))

    # Verify against what was actually written, not the in-memory lists.
    assert train, "empty train split"
    assert valid, "empty valid split (mlx_lm.lora requires one)"
    assert not train_ids & valid_ids, \
        "document-grouped violation: %s" % sorted(train_ids & valid_ids)
    for r in valid:
        assert r.get("origin") == "real", "synthetic row in valid: %r" % r
        assert "source_id" in r, "valid row without source_id: %r" % r
    for name, part in (("train.jsonl", train), ("valid.jsonl", valid)):
        with open(os.path.join(out_dir_final, name)) as f:
            disk = [json.loads(line) for line in f]
        assert disk == [chat(r) for r in part], "%s does not round-trip" % name
        for m in disk:
            assert m["messages"][0] == {"role": "system",
                                        "content": REGISTER_SYSTEM}
    print("verify OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
