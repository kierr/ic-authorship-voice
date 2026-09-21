#!/usr/bin/env python3
"""build_tasks.py — build SFT instruction pairs from the real corpus (§9).

Honest v1 tasks manufacturable from *real* data (no synthetic needed, no
press→KJ mapping yet):

  mask_term        vocabulary anchoring: blank a PHIA yardstick term in a real
                   assessment sentence; target = the term. High-signal, cheap,
                   self-supervised.
  register_copy    register copy/continued-pretraining: real assessment line as
                   assistant; user invites a register line on the same topic.

The negative_llm and contrast classes exist in the corpus but are never SFT
targets here (class filter in main); press→KJ (style transfer) and critique
(flawed→corrected) tasks are out of scope for this script.

Every task carries the source provenance (id, source_id, sha256) so synthetic
never leaks into val/test and provenance survives (§2).

Usage: .venv/bin/python scripts/build_tasks.py corpus/train.jsonl
       (writes corpus/tasks/sft.jsonl)
"""
import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yardstick



# Prose gate shared by fact collection and grounded-target eligibility:
# PDF/HTML extraction leaves page furniture ("Quick Links: Home | Overview",
# "<-- back to Contents") that reads as sentences but is navigation.
_FURNITURE_RE = re.compile(
    r"\||<--|Quick Links|back to Contents|^Contents|Home \||http|@|"
    r"^\s*(Overview|Chapter|Section|Annex)\b")


def _prose_ok(sent):
    words = sent.split()
    if len(words) < 8 or _FURNITURE_RE.search(sent):
        return False
    alpha = sum(c.isalpha() for c in sent)
    if alpha < 0.7 * len(sent):
        return False
    low = " " + sent.lower() + " "
    return sum(f" {w} " in low for w in
               ("the", "of", "and", "to", "in", "for", "was", "were")) >= 2


def make_mask_task(rec):
    text = rec["text"]
    m = yardstick.TERM_RE.search(text)
    if not m:
        return None
    # NOTE the stored answer must be one of the seven choices the prompt
    # offers, so canonicalize the matched surface ("probably" -> "likely or
    # probable") and drop any surface without a canonical mapping.
    term = yardstick.canonicalize(m.group(0))
    if term not in yardstick.CANONICAL:
        return None
    masked = yardstick.TERM_RE.sub("[TERM]", text, count=1)
    user = ("Complete this UK intelligence assessment with the correct "
            "probability-yardstick term from the given choices "
            "(remote chance, highly unlikely, unlikely, realistic possibility, "
            "likely or probable, highly likely, almost certain):\n%s" % masked)
    return {"task": "mask_term", "system": yardstick.REGISTER_SYSTEM,
            "user": user, "assistant": term,
            "source_id": rec["source_id"], "id": rec["id"] + "-mask", "sha256": rec["sha256"]}


def make_copy_task(rec):
    # The cue must not contain the answer: strip the estimative terms the
    # task exists to teach, then truncate at a word boundary. The old cue was
    # the target's verbatim first 120 chars ("…" appended even when nothing
    # was cut, so short rows carried their complete answer in the prompt).
    cue = yardstick.TERM_RE.sub("", rec["text"]).strip()
    cue = re.sub(r"\s{2,}", " ", cue)
    if len(cue) > 100:
        cue = cue[:100].rsplit(" ", 1)[0] + "…"
    if not cue:
        return None
    user = ("Write one short line in the UK intelligence community assessment "
            "register on this subject:\n%s" % cue)
    return {"task": "register_copy", "system": yardstick.REGISTER_SYSTEM,
            "user": user, "assistant": rec["text"], "source_id": rec["source_id"],
            "id": rec["id"] + "-copy", "sha256": rec["sha256"]}




def make_grounded_task(rec, doc_facts=None):
    """Facts -> judgement: prompt carries real non-estimative content, the
    assistant is the real specifics-bearing judgement sentence.

    v2 (2026-08-22): v1's fallback stripped the yardstick term from the
    target itself — a fill-in-the-blank, not facts->judgement (big1/clean3
    both failed the grounded bench on parroted fragments). Now facts come
    from SIBLING sentences of the same document (grouped by caller via
    doc_facts); single-sentence docs without siblings yield no task rather
    than a fake one.
    """
    text = rec["text"]
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
    jd = [x for x in sents if yardstick.TERM_RE.search(x) and _prose_ok(x)]
    if not jd or not _prose_ok(text):
        return None
    facts = [f for f in (doc_facts or []) if f not in sents]
    if len(facts) < 1 or sum(len(x) for x in facts) < 40:
        return None
    ctx = ""
    if rec.get("published"):
        ctx = " (assessment of %s)" % rec["published"]
    # Prompt phrasing VARIES per row (stable hash pick): blind v2 caught the
    # model emitting "the reported facts are consistent with..." — the single
    # fixed user template leaked into free generation as a verbal tic. Five
    # framings keep no one opener bound to the response shape.
    fact_str = " ".join(facts)[:400]
    variants = [
        "From these reported facts, write the UK intelligence Key "
        "Judgement%s:\n%s" % (ctx, fact_str),
        "On the basis of the reporting below, write the Key Judgement%s "
        "in register:\n%s" % (ctx, fact_str),
        "Assess the following reporting%s. Lead with the judgement:\n%s"
        % (ctx, fact_str),
        "Draft one estimative line for the assessment file%s:\n%s"
        % (ctx, fact_str),
        "Write the Key Judgement this reporting supports%s:\n%s"
        % (ctx, fact_str),
    ]
    user = variants[int(hashlib.sha1(rec["id"].encode()).hexdigest(), 16)
                    % len(variants)]
    return {"task": "grounded_judgement", "system": yardstick.REGISTER_SYSTEM,
            "user": user, "assistant": text, "source_id": rec["source_id"],
            "id": rec["id"] + "-grd", "sha256": rec["sha256"]}


def main():

    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", default="corpus/train.jsonl")
    ap.add_argument("--out", default="corpus/tasks/sft.jsonl")
    args = ap.parse_args()

    out_dir = os.path.dirname(args.out)
    if out_dir:  # bare filename -> dirname is "", which makedirs rejects
        os.makedirs(out_dir, exist_ok=True)
    n = {"mask": 0, "copy": 0, "grd": 0}
    # Two passes: first collect per-document sibling sentences (facts for the
    # grounded task), then emit. Facts = sentences from OTHER rows of the same
    # document that carry no yardstick term — real reporting, not the target.
    rows = []
    doc_sents = {}
    with open(args.input) as fin:
        for line in fin:
            rec = json.loads(line)
            if rec.get("class") not in ("key_judgements", "confidence_statements", "full_assessment"):
                continue  # never build SFT from contrast/negative prose
            rows.append(rec)
            sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", rec["text"]) if x.strip()]
            for sent in sents:
                if yardstick.TERM_RE.search(sent):
                    continue
                if _prose_ok(sent):
                    doc_sents.setdefault(rec["source_id"], []).append(sent)
    with open(args.out, "w") as f:
        for rec in rows:
            own = {x.strip() for x in re.split(r"(?<=[.!?])\s+", rec["text"]) if x.strip()}
            facts = [x for x in doc_sents.get(rec["source_id"], []) if x not in own]
            for kind, fn in (("mask", make_mask_task), ("copy", make_copy_task),
                             ("grd", lambda r: make_grounded_task(r, doc_facts=facts))):
                t = fn(rec)
                if t:
                    f.write(json.dumps(t, ensure_ascii=False) + "\n")
                    n[kind] += 1
    print("wrote %s  mask=%d copy=%d grd=%d" % (args.out, n["mask"], n["copy"], n["grd"]))


if __name__ == "__main__":
    main()