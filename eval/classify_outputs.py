#!/usr/bin/env python3
"""eval/classify_outputs.py — run the register classifier over bench outputs.

Trains the Five-Eyes register classifier once (corpus/train + contrast, via
classifier.train_classifier), then classifies each fine-tuned and frozen-base
bench row from eval/bench_out.jsonl (bench.py's default output; its first
line is run metadata and is skipped), and aggregates. This is §11.2's headline
gate: fine-tuned output should classify uk_ic; frozen base output should not.

Usage: .venv/bin/python eval/classify_outputs.py [BENCH_OUT.jsonl]
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classifier import load, label_of, train_classifier  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    train = load(os.path.join(ROOT, "corpus", "train.jsonl"))
    contrast = load(os.path.join(ROOT, "corpus", "contrast.jsonl"))
    X, y = [], []
    for s in train + contrast:
        X.append(s.get("text", ""))
        y.append(label_of(s))
    clf = train_classifier(X, y)

    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "eval", "bench_out.jsonl")
    bench = [r for r in load(path) if "ft" in r]  # drops the metadata line
    agg = {t: collections.Counter() for t in ("ft", "base")}
    print("per-row classification (ft | base):")
    for r in bench:
        preds = {tag: clf.predict([r[tag]])[0] for tag in ("ft", "base")}
        for tag in ("ft", "base"):
            agg[tag][preds[tag]] += 1
        print("  [%d] ft=%s base=%s" % (r["i"], preds["ft"], preds["base"]))
    print("\n===== aggregate =====")
    for tag in ("ft", "base"):
        print("%-4s  %s" % (tag, dict(agg[tag])))


if __name__ == "__main__":
    main()
