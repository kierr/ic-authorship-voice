#!/usr/bin/env python3
"""run_all.py — reproduce the full corpus build in order.

One-command reproducibility: fetch(bootstrap) -> parse -> segment -> build ->
tasks -> sft_all -> mlx -> project -> validate. Fine-tuning (mlx-lm QLoRA) and
the operator blind test are documented in notes/decisions and eval/register.md;
they remain by-hand against the same built corpus.

Usage: .venv/bin/python scripts/run_all.py [--fetch] [--only INDEX]
  --fetch     download missing raw/ (off by default on an already-fetched repo)
Steps print their stage so a fresh clone's output is auditable.
"""
import os
import subprocess
import sys

# index -> (stage, script); fetch stays gated by --fetch.
STEPS = {
    1: ("fetch", "fetch.py"),               # download missing raw/ per manifest.json
    2: ("parse", "parse.py"),               # pdf/html -> extracted/
    3: ("segment", "segment.py"),           # extracted -> segments
    4: ("build", "build_corpus.py"),        # corpus/ splits (document-grouped, held-out)
    5: ("tasks", "build_tasks.py"),         # SFT instruction-pair build (real + critique)
    6: ("sft_all", "build_sft_all.py"),     # consolidate task builds -> sft_all.jsonl
    7: ("mlx", "build_mlx.py"),             # sft_all -> mlx-lm chat format for QLoRA
    8: ("project", "manifest.py"),          # project manifest.json -> manifest.yaml ledger
    9: ("validate", "validate_corpus.py"),  # invariant checks over the built artifacts
}
# Anchored on this file, not the cwd, so run_all works from any directory.
BASE = os.path.dirname(os.path.abspath(__file__))


def run(stage, cmd):
    print("== %s ==" % stage)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit("FAILED at %s" % stage)


def parse_only(val):
    try:
        return int(val)
    except ValueError:
        sys.exit("--only expects an integer stage index, got %r" % val)


def main():
    args = sys.argv[1:]
    do_fetch = "--fetch" in args
    only = None
    for i, a in enumerate(args):
        if a == "--only":
            if i + 1 >= len(args):
                sys.exit("--only requires a stage index (1-%d)" % max(STEPS))
            only = parse_only(args[i + 1])
        elif a.startswith("--only="):
            only = parse_only(a.split("=", 1)[1])
    if only is not None:
        if only not in STEPS:
            sys.exit("--only %d: unknown stage (valid: 1-%d)" % (only, max(STEPS)))
        if STEPS[only][0] == "fetch" and not do_fetch:
            sys.exit("--only %d selects fetch, which is gated off; add --fetch" % only)
    for i in sorted(STEPS):
        if only is not None and i != only:
            continue
        stage, script = STEPS[i]
        if stage == "fetch" and not do_fetch:
            continue
        run(stage, [sys.executable, os.path.join(BASE, script)])
    print("run_all complete (fetch=%s)" % do_fetch)


if __name__ == "__main__":
    main()
