#!/usr/bin/env python3
"""build_sft_all.py — deterministic consolidated SFT mix (corpus/tasks/sft_all.jsonl).

Exact recipe, in output order:
  1. corpus/tasks/sft.jsonl      real-segment tasks (mask_term / register_copy)
  2. corpus/critique_task.jsonl  critique pairs over negative_llm.jsonl rows
  3. corpus/synthetic_aug.jsonl  synthetic key-judgement augmentation

Every row is normalised to carry:
  task    mask_term | register_copy | critique | synthetic_kj
          (build_tasks.py historically wrote register_copy under "task_type";
           folded into "task" here)
  origin  "real" for sft.jsonl rows (built from real segments), "synthetic"
          for critique and synthetic rows
plus the provenance keys the source ledger has: id/source_id/sha256 for sft
rows; critique rows carry their negative-example linkage as "negative_id"
(their ledger's "source_id" holds a negative_llm.jsonl id, not a document id —
renamed so document-grouped splitting downstream never treats it as one);
synthetic rows keep their lineage fields (class, lineage_source, generator,
edit_level, fewshots) untouched.

Usage: .venv/bin/python scripts/build_sft_all.py
"""
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SFT = os.path.join(ROOT, "corpus", "tasks", "sft.jsonl")
CRITIQUE = os.path.join(ROOT, "corpus", "critique_task.jsonl")
SYNTHETIC = os.path.join(ROOT, "corpus", "synthetic_aug.jsonl")
OUT = os.path.join(ROOT, "corpus", "tasks", "sft_all.jsonl")


def read_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def normalise(rec, origin, rename=()):
    """Row with task/origin first, remaining keys in ledger order."""
    task = rec.get("task") or rec["task_type"]
    out = {"task": task, "origin": rec.get("origin", origin)}
    ren = dict(rename)
    for k, v in rec.items():
        if k in ("task", "task_type", "origin"):
            continue
        out[ren.get(k, k)] = v
    return out


def main():
    for p in (SFT, CRITIQUE, SYNTHETIC):
        if not os.path.exists(p):
            print("missing", p, file=sys.stderr)
            return 1
    rows = []
    rows += [normalise(r, "real") for r in read_jsonl(SFT)]
    rows += [normalise(r, "synthetic", rename={"source_id": "negative_id"})
             for r in read_jsonl(CRITIQUE)]
    rows += [normalise(r, "synthetic") for r in read_jsonl(SYNTHETIC)]

    with open(OUT, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    tasks = Counter(r["task"] for r in rows)
    origins = Counter(r["origin"] for r in rows)
    print("wrote %s  rows=%d  %s  %s" % (OUT, len(rows), dict(tasks), dict(origins)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
