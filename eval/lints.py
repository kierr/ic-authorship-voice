#!/usr/bin/env python3
"""eval/lints.py — rule lints for UK-IC register text.

Runs on any text (corpus samples, model output). Each lint returns a score in
[0,1] and a list of violations. Sum/average gives a register-health signal.
Expected: fine-tuned output scores high; base-model and press output score low
(esp. BANNED + FIRST + VARLEN which are the contamination and cadence checks).

Usage: .venv/bin/python eval/lints.py FILE [FILE ...]
       (each FILE one or more documents; or pass --corpus to lint corpus/{train,val,test}.jsonl)
       [--strict] exit nonzero on any failure; [--json] dump per-file results
"""
import argparse
import glob
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
import yardstick  # noqa: E402  single code encoding of the PHIA vocabulary

# ---- UK Probability Yardstick terms (positive) ----
# yardstick.TERM_RE is word-bounded and longest-first: adjectival "almost
# certain" matches; "improbable"/"remote working" do not; bare "remote",
# "almost always" and "high likelihood" are not yardstick terms.
POS_RE = yardstick.TERM_RE

# ---- Banned: US-register contamination + model-slop ----
# Americanism patterns are word-anchored so ".program" matches US "program(s)"
# but not the British "programme(s)"; likewise center/behavior/modeling.
BANNED = [
    # US confidence-as-probability cadence (incl. "high degree of confidence")
    "high confidence", "moderate confidence", "low confidence",
    "with high confidence", "we assess with confidence", "degree of confidence",
    # US probability noun-phrases (UK would say "highly likely", not "high
    # probability"/"high likelihood" as a probability qualifier)
    "high probability", "high likelihood",
    # hedging stacks / model-slop
    "could potentially", "may possibly", "it could be argued",
    "very likely", "somewhat", "arguably",
    # Americanisms: explicit US spellings only (behaviour/centre/modelling are
    # correct British register and must NOT flag; "programmed"/"programming"
    # are standard in both registers, so only the single-m US variants
    # "programed"/"programing" are tells)
    "behavior", "behaviors", "center", "centers",
    "program", "programs", "programed", "programing",
    "modeling", "modeled", "utilize", "utilized", "utilizing",
    "e.g.", "i.e.", "%",
]
_ALT_SEP = "|"
_BANNED_PAT = _ALT_SEP.join(re.escape(b) for b in BANNED)
# Word-bound: US bare words (program, behavior) never match inside British
# forms (programme, behaviour, modelling).
BAN_RE = re.compile(r"(?<![A-Za-z])(" + _BANNED_PAT + r")(?![A-Za-z])", re.IGNORECASE)


def selftest():
    """Assert every BANNED entry individually matches BAN_RE.

    Guards the implicit-concat comma bug: a missing comma fused
    "high likelihood" + "could potentially" into one dead literal, silently
    unenforcing both through every published "0% banned" result.
    validate_corpus.py calls this.
    """
    # A count pin catches any NEW fusion: implicit concatenation collapses two
    # entries into one, so the list length changes (29 in the fused state).
    # Bump EXPECTED_BANNED only when deliberately adding/removing entries.
    EXPECTED_BANNED = 30
    assert len(BANNED) == EXPECTED_BANNED, (
        "BANNED has %d entries, expected %d — a missing comma fuses two "
        "entries into one dead literal; check the last edit"
        % (len(BANNED), EXPECTED_BANNED))
    for b in BANNED:
        assert BAN_RE.search(b), "BANNED entry unenforced: %r" % b
    # NOTE a fused entry still self-matches the loop above (its own escaped
    # literal is in the alternation), so probe the historically-fused phrases
    # as standalone text too.
    for b in ("high likelihood", "could potentially"):
        assert BAN_RE.search(b), "BANNED phrase unenforced: %r" % b
    # ADOPTED confidence-position rule: grounded parenthetical passes, all
    # same-clause or ungrounded uses flag.
    assert lint_confidence("We assess with high confidence that X will happen.")[1]
    assert not lint_confidence(
        "X is highly likely (moderate confidence: single-source reporting).")[1]
    assert lint_confidence("X is likely (high confidence).")[1]
    # Category tell: likelihood welded to a statistic/capability.
    assert lint_category("The doubling of crossings in a quarter is highly likely.")[1]
    assert lint_category("The network's ability to exploit this is almost certain.")[1]
    assert not lint_category("Russia is highly likely to redeploy forces.")[1]
    # Specifics tell: shape without content (score 0 = no checkable specific).
    assert lint_specifics("We assess that the group is highly likely to continue.")[0] == 0.0
    assert lint_specifics("Russia has likely lost more than 240 tanks since 9 February.")[0] == 1.0


# NOTE it's/we're require the apostrophe: the optional-apostrophe forms
# matched possessive "its" and plain "were" (measured: all 103 contraction
# flags in train.jsonl were those two false positives)
CONTRACTIONS = re.compile(r"\b(?:don'?t|won'?t|can'?t|isn'?t|aren'?t|haven'?t|hasn'?t|it's|we're|they'?re|there'?s|that'?s)\b", re.IGNORECASE)

# Antithesis opener: "X, not Y:" / "X, rather than Y:"
ANTITHESIS = re.compile(r"^\s*[A-Z][A-Za-z ,'\-]{0,40},\s*(?:not|rather than)\s+[A-Za-z ,'\-]{2,40}:", re.M)

# Colon-label opener density: "Label: content" paragraph openers
COLON_LABEL = re.compile(r"(?m)^\s*[A-Za-z][A-Za-z ]{2,30}:\s+[A-Z][a-z]")

# --- Plausibility: at least one positive term required ---


def lint_py(text):
    return 1.0 if POS_RE.search(text) else 0.0, []


def lint_banned(text, banned_re=BAN_RE):
    hits = list(dict.fromkeys(banned_re.findall(text)))
    score = 0.0 if len(hits) > 0 else 1.0
    return score, hits


def lint_contractions(text):
    hits = list(dict.fromkeys(CONTRACTIONS.findall(text)))
    return (0.0 if hits else 1.0), hits


def lint_antithesis(text):
    hits = ANTITHESIS.findall(text)
    return (0.0 if hits else 1.0), hits


def lint_colon_label(text):
    hits = COLON_LABEL.findall(text)
    density = len(hits)
    # allow occasional; flag if it's the dominant opener
    score = 1.0 if density < 2 else max(0.0, 1.0 - density / 8.0)
    return score, ["%d colon-label openers" % density]


def lint_sentence_variance(text):
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sents) < 3:
        return 1.0, []
    lengths = [len(s.split()) for s in sents]
    var = (max(lengths) - min(lengths)) / max(1, sum(lengths) / len(lengths))
    score = min(1.0, var)
    # uniform mechanical sentence shape (low variance) is a tell
    if max(lengths) - min(lengths) < 6:
        score = min(score, 0.3)
    return score, lengths


def lint_judgement_first(text):
    first = text.split(".", 1)[0]
    ok = bool(POS_RE.search(first) or re.search(r"\b(assess|judge)\b", first, re.I))
    return (1.0 if ok else 0.0), []


# Judges' consensus tells (2026-08-22 blind run) made machine-checkable.

# Tell 2: probability attached to non-propositions — "the doubling of
# crossings ... is highly likely", "the network's ability ... is almost
# certain". Real assessments attach likelihood to events, not statistics or
# capabilities. Heuristic: a yardstick term whose subject NP (within the
# preceding ~6 tokens) is headed by a statistic/capability noun.
_CATEGORY_NOUNS = (
    "doubling|number|ability|capacity|growth|increase|decrease|reduction|"
    "rate|total|capability|size|level|figure|amount|volume|share|trend|"
    "decline|rise|fall|count")
_CATEGORY_RE = re.compile(
    r"\b(?:the|a|an|its|their)\s+(?:[a-z\']+\s+){0,3}(?:%s)s?\b"
    r"[^.]{0,40}?\b(?:%s)\b" % (_CATEGORY_NOUNS, "likely|unlikely|certain|probable"),
    re.IGNORECASE)


def lint_category(text):
    hits = [m.group(0) for m in _CATEGORY_RE.finditer(text)]
    return (0.0 if hits else 1.0), hits


# Tell 5: checkable specifics absent — shape without content. Real anchors
# carry dates, sums, counts, or names; model output often carries none.
_SPECIFIC_RE = re.compile(
    r"\b\d"                      # any digit (dates, sums, counts, units)
    r"|£|\$|\u20ac"              # currency
    r"|\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\b"           # month names
    r"|(?:[A-Z][a-z]+\s){1,2}[A-Z][a-z]+" )    # a Proper Name Pair


def lint_specifics(text):
    ok = bool(_SPECIFIC_RE.search(text))
    return (1.0 if ok else 0.0), [] if ok else ["no checkable specific"]


# ADOPTED spec amendment 2026-08-22: analytic confidence is legal only
# grammatically detached from the judgement AND with stated evidential
# grounds. Same-clause exclusion: any confidence phrase outside a
# grounds-bearing parenthetical is a violation (covers confidence-as-
# probability, the US tell, and bare ungrounded parentheticals alike).
_CONF_RE = re.compile(r"\b(?:high|moderate|low)\s+confidence\b", re.IGNORECASE)
_GROUNDS_RE = re.compile(
    r"single[- ]source|based on|reporting|coverage|uncorroborated|"
    r"evidence|provenance|sources?\b", re.IGNORECASE)


def _grounded_parens(text):
    ok = set()
    for m in re.finditer(r"\([^()]*\)", text):
        if _GROUNDS_RE.search(m.group(0)):
            for c in range(m.start(), m.end()):
                ok.add(c)
    return ok


def lint_confidence(text):
    grounded = _grounded_parens(text)
    hits = [m.group(0) for m in _CONF_RE.finditer(text)
            if m.start() not in grounded]
    return (1.0 if not hits else 0.0, hits)


LINTS = [
    ("yardstick_present", lint_py),
    ("us_banned", lint_banned),
    ("contractions", lint_contractions),
    ("antithesis", lint_antithesis),
    ("colon_label", lint_colon_label),
    ("sentence_variance", lint_sentence_variance),
    ("judgement_first", lint_judgement_first),
    ("confidence", lint_confidence),
    ("category", lint_category),
    ("specifics", lint_specifics),]

# NOTE failure threshold shared by --corpus flagging and --strict: binary
# lints emit only 0/1 so this demands a full pass on them; graded lints
# (colon_label, sentence_variance) pass above the same bar.
FAIL_BELOW = 0.6



def lint_doc(text, verbose=True):
    res = {}
    for name, fn in LINTS:
        score, hits = fn(text)
        res[name] = score
        if verbose and hits:
            print("  [%s] %.2f  hits=%r" % (name, score, hits))
    return res


def from_jsonl(path):
    with open(path) as f:
        for line in f:
            j = json.loads(line)
            yield j.get("text") or j.get("assistant") or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--json", action="store_true", help="dump per-file results as JSON")
    ap.add_argument("--strict", action="store_true", help="exit nonzero when any file has failures")
    ap.add_argument("--corpus", action="store_true", help="lint corpus/{train,val,test}.jsonl")
    args = ap.parse_args()

    failed = False
    if args.corpus:
        report = {}
        for split in ("train", "val", "test"):
            # anchored on the repo root: a cwd-relative glob silently no-ops
            # (exit 0, zero files) when run from anywhere but the root
            for p in glob.glob(os.path.join(_ROOT, "corpus", "%s.jsonl" % split)):
                rel = os.path.relpath(p, _ROOT)
                docs = 0
                fails = []
                for text in from_jsonl(p):
                    docs += 1
                    res = lint_doc(text, verbose=False)
                    if min(res.values()) < FAIL_BELOW:
                        fails.append({"snippet": text[:60],
                                      "checks": {k: v for k, v in res.items() if v < FAIL_BELOW}})
                report[rel] = {"docs": docs, "flagged": len(fails), "fails": fails}
                failed = failed or bool(fails)
        if args.json:
            print(json.dumps(report))
        else:
            for rel, r in report.items():
                print("%-18s docs=%d flagged=%d" % (rel, r["docs"], r["flagged"]))
                for f in r["fails"]:
                    print("  FAIL %r %s" % (f["snippet"], f["checks"]))
        return 1 if (args.strict and failed) else 0

    results = {}
    for p in args.paths:
        text = open(p).read()
        if not args.json:
            print("==== %s ====" % p)
        res = lint_doc(text, verbose=not args.json)
        results[p] = res
        failed = failed or min(res.values()) < FAIL_BELOW
        if not args.json:
            print("  yardstick_present=%.2f us_banned=%.2f contractions=%.2f antithesis=%.2f colon=%.2f var=%.2f jf=%.2f" % (
                res["yardstick_present"], res["us_banned"], res["contractions"],
                res["antithesis"], res["colon_label"], res["sentence_variance"],
                res["judgement_first"]))
    if args.json:
        print(json.dumps(results))
    return 1 if (args.strict and failed) else 0


if __name__ == "__main__":
    sys.exit(main())
