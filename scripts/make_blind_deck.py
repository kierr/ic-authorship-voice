#!/usr/bin/env python3
"""make_blind_deck.py — build the operator blind-test deck.

Pairs N real, human-written UK Key-Judgement snippets — drawn ONLY from the
held-out test split (corpus/test.jsonl, class=key_judgements, origin=real) —
with the model's output on thematically matched fresh scenarios, shuffles each
pair, and writes eval/blind_deck.md for the operator. The answer key goes to
eval/blind_key.md so the operator reads the deck blind. Definition of done:
the operator must NOT correctly spot the model output >=4/5 times (ideally
fails to identify it).

Every chosen anchor is leak-gated at build time: the run aborts if the anchor
text appears as any assistant text in corpus/tasks/sft_all.jsonl or any
corpus/tasks/mlx*/ train/valid file — otherwise the blind test measures
memorisation, not register.

Usage: .venv/bin/python scripts/make_blind_deck.py [--force] [--bench-out PATH]
Deterministic: inputs are sorted, pairing is keyed by index, and the shuffle
seed is fixed, so re-running gives the same board. Refuses to overwrite an
existing eval/blind_deck.md unless --force (a rerun must not clobber a
historical deck).
"""
import argparse
import glob
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


def norm(t):
    return " ".join(t.split())


def first2(t):
    parts = [x.strip() for x in t.replace("\n", " ").split(". ") if x.strip()]
    return ". ".join(parts[:2]) + "." if parts else t


def assistant_texts():
    """Every assistant-side string the adapter under test could have memorised.

    RATIONALE: scope is the CANONICAL training surfaces (sft_all.jsonl +
    corpus/tasks/mlx/ + the legacy mlx_chat.jsonl) — the surfaces that train
    current adapters. The deprecated snapshot mixes (mlx_vj/ etc., see
    corpus/tasks/README.md) are known-contaminated with val/test text and
    trained only the legacy adapters; scanning them would veto every honest
    anchor while guarding nothing the current adapter saw. The deck header
    records this scope: the deck is NOT fair for legacy mlx_vj-era adapters.
    Would need a deck built for a legacy adapter to widen the scan again.
    """
    out = []
    for r in load(os.path.join(ROOT, "corpus", "tasks", "sft_all.jsonl")):
        if r.get("assistant"):
            out.append(norm(r["assistant"]))
    # mlx/train.jsonl only: valid.jsonl is never trained on (gradient-free
    # loss monitoring — scanning it would veto every val anchor by
    # construction), and mlx_chat.jsonl is a pre-decontamination legacy
    # snapshot that trained no current adapter.
    fp = os.path.join(ROOT, "corpus", "tasks", "mlx", "train.jsonl")
    if os.path.exists(fp):
        for r in load(fp):
            for m in r.get("messages", []):
                if m.get("role") == "assistant" and m.get("content"):
                    out.append(norm(m["content"]))
    return out


def anchor_leaks(snip, full, asst):
    """True if the anchor overlaps any training assistant text.

    Containment runs both ways: a training row may be the anchor's segment
    quoted or truncated differently, so equality is too narrow. The reverse
    direction (assistant inside the anchor's full segment) skips strings
    <40 chars — mask_term one-worders ("likely") would match everything.
    """
    s, t = norm(snip), norm(full)
    for a in asst:
        if s in a or t in a:
            return True
        if len(a) >= 40 and a in t:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing eval/blind_deck.md")
    ap.add_argument("--bench-out", default=None,
                    help="bench output jsonl (default eval/bench_out.jsonl, "
                         "falling back to corpus/tasks/bench_out.jsonl)")
    args = ap.parse_args()

    deck_path = os.path.join(ROOT, "eval", "blind_deck.md")
    key_path = os.path.join(ROOT, "eval", "blind_key.md")
    if os.path.exists(deck_path) and not args.force:
        sys.exit("refusing to overwrite existing %s (historical deck); pass --force to rebuild"
                 % os.path.relpath(deck_path, ROOT))

    # Real anchors ONLY from splits no training surface contains: test first,
    # then val. The heading-path quality bar leaves the publisher-held-out
    # test split with ~1 usable KJ, so val KJs fill the deck — they are never
    # trained on (loss monitoring only; a mild selection coupling, noted in
    # the deck header) and every anchor still passes the leak gate below.
    def kj_rows(split):
        rows = [r for r in load(os.path.join(ROOT, "corpus", "%s.jsonl" % split))
                if r.get("class") == "key_judgements" and r.get("origin") == "real"]
        rows.sort(key=lambda r: r["id"])
        return rows
    cands = kj_rows("test") + kj_rows("val")

    # Model outputs on thematically-matched fresh scenarios from the bench.
    # bench.py is moving its output to eval/; keep the old path as fallback.
    if args.bench_out:
        bench_path = args.bench_out
    else:
        bench_path = os.path.join(ROOT, "eval", "bench_out.jsonl")
        if not os.path.exists(bench_path):
            bench_path = os.path.join(ROOT, "corpus", "tasks", "bench_out.jsonl")
    bench = load(bench_path)
    # bench.py's first line is run metadata (timestamp/adapter hash), not a row.
    bench = [r for r in bench if "ft" in r]
    bench.sort(key=lambda r: r.get("i", 0))
    # A degenerate one-liner (the mask-echo failure mode) is trivially
    # distinguishable and makes the pair worthless — pair only substantive
    # model passages.
    mo = [r["ft"] for r in bench if len(r["ft"].strip()) >= 120]
    if not mo:
        sys.exit("no bench outputs at %s; run eval/bench.py first (or pass --bench-out)" % bench_path)

    n = min(5, len(cands), len(mo))
    asst = assistant_texts()
    anchors = []
    leaked = []
    for r in cands[:n]:
        snip = first2(r["text"])[:380]
        if anchor_leaks(snip, r["text"], asst):
            leaked.append(r["id"])
        anchors.append((r["id"], r["source_id"], snip))
    if leaked:
        sys.exit("LEAK GATE: %d/%d chosen test-split anchors appear as assistant text in "
                 "sft_all.jsonl / mlx* train/valid: %s\nThe test split has leaked into the "
                 "task files; fix the split before building a deck." % (len(leaked), n, ", ".join(leaked)))

    random.seed(2026)
    pairs = []
    for i in range(n):
        rid, sid, real = anchors[i]
        mod = first2(mo[i])[:380]
        a, b = (("real", real), ("model", mod))
        if random.random() < 0.5:
            a, b = b, a
        pairs.append((i + 1, a, b, rid, sid))

    with open(deck_path, "w") as f:
        f.write("# Operator blind test — UK IC register (definition of done)\n\n")
        f.write("For each scenario, one passage is a genuine published UK intelligence\n")
        f.write("assessment; the other is model output. Mark which you believe is machine\n")
        f.write("generated — no blanks; both are meant to read as plausible.\n")
        f.write("Score against eval/blind_key.md only after marking every scenario.\n\n")
        for num, a, b, _rid, _sid in pairs:
            f.write("\n## Scenario %d\n\n" % num)
            f.write("**A** — %s\n\n" % a[1])
            f.write("**B** — %s\n\n" % b[1])

    with open(key_path, "w") as f:
        f.write("# Blind-deck answer key\n\n")
        f.write("Operator: mark every scenario in eval/blind_deck.md FIRST; do not read\n")
        f.write("past this header until you have scored the deck.\n\n")
        for num, a, b, rid, sid in pairs:
            f.write("Scenario %d: A=%s, B=%s  <!-- real anchor: %s (source %s) -->\n"
                    % (num, a[0], b[0], rid, sid))
    print("wrote eval/blind_deck.md (%d scenarios) and eval/blind_key.md" % len(pairs))


if __name__ == "__main__":
    main()
