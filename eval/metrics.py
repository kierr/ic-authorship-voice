#!/usr/bin/env python3
"""eval/metrics.py — single gate for UK-IC register text.

Combines the rule lints with (optionally) the register classifier. Intended to
be run on model output vs real KJ exemplars to drive the fine-tune A/B loop.
The operator blind test and LLM-judge ranking are declared here
as the definition of done; the judge prompt lives in eval/judge_prompt.md.

Usage:
  .venv/bin/python eval/metrics.py FILE.txt            # lint + clean flag
  .venv/bin/python eval/metrics.py --classify FILE.txt # + register classifier
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lints import LINTS, BAN_RE, FAIL_BELOW  # noqa: E402


def lint_text(text):
    res = {name: fn(text)[0] for name, fn in LINTS}
    hits = list(dict.fromkeys(BAN_RE.findall(text)))
    # clean gates on ALL lints (it used to omit contractions and
    # yardstick_present); FAIL_BELOW is lints.py's shared threshold — binary
    # lints emit only 0/1, so it demands a full pass on them
    res["clean"] = 1.0 if all(res[name] >= FAIL_BELOW for name, _ in LINTS) else 0.0
    return res, hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--classify", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = open(args.path).read()
    res, hits = lint_text(text)

    if args.classify:
        try:
            from classifier import load, label_of, train_classifier
            train = load(os.path.join(ROOT, "corpus", "train.jsonl"))
            contrast = load(os.path.join(ROOT, "corpus", "contrast.jsonl"))
            X, y = [], []
            for s in train + contrast:
                X.append(s.get("text", "")); y.append(label_of(s))
            clf = train_classifier(X, y)
            labels = list(clf.classes_)
            proba = clf.predict_proba([text])[0]
            res["classifier"] = labels[int(proba.argmax())]
            res["classifier_p_uk"] = round(float(proba[labels.index("uk_ic")]) if "uk_ic" in labels else 0.0, 3)
        except (ImportError, ValueError) as e:
            # NOTE narrow: sklearn missing or an empty/degenerate corpus only;
            # anything else (KeyError from an unknown class, IO errors)
            # re-raises rather than masquerading as "unavailable"
            res["classifier"] = f"unavailable ({e})"

    if args.json:
        print(json.dumps(res, default=float))
        return
    print("==== %s ====" % args.path)
    for k, v in sorted(res.items()):
        print(f"  {k:<14} {v:.2f}" if isinstance(v, float) else f"  {k:<14} {v}")
    if hits:
        print("  banned:", hits)


if __name__ == "__main__":
    main()
