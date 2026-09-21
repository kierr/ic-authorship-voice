# Curation schema — corpus/curated/

Shared JSONL schema for the curated pipeline. Every file is one JSON per line.
All fields snake_case; no nested objects.

## Files

| file | purpose |
|---|---|
| real_clean.jsonl | curated REAL register items (from extracted/*.segments.jsonl), chrome/garble dropped |
| synth_a.jsonl | grounded synthetic register items (single writer, 5 rows) |
| critique.jsonl | critic verdicts per synthetic item |
| synth_final.jsonl | full pass set after fixer correction |

NOTE (2026-08-21): this schema originally declared a second writer file,
synth_b.jsonl ("two non-overlapping writers"). It was never produced: the
pipeline ran a single writer (synth_a.jsonl, 5 rows), with critique.jsonl
verdicts and synth_final.jsonl critique-to-final corrections over those same
5 rows. Amended to describe what exists.

## real_clean.jsonl row
```
{"id": "cur_<n>", "class": "confidence_statements"|"key_judgements",
 "origin": "real", "source": "<original sha256>", "text": "<clean register prose>"}
```

## synth_a.jsonl row
```
{"id": "cur_syn_a_<n>", "class": "key_judgements",
 "origin": "synthetic", "lineage": "<real exemplar id>",
 "text": "<2-4 sentence UK-IC Key Judgement>", "system": "<one-line register instruction>"}
```

## critique.jsonl row
```
{"id": "<synth id>", "verdict": "pass"|"fail",
 "reason": "<which register signal fires; empty if pass>"}
```

## synth_final.jsonl row
```
{"id": "<synth id>", "origin": "synthetic", "verdict": "pass",
 "was_fail": true|false, "reason": "<correction applied or blank>", "text": "<pass-prose>"}
```

## Rules (all writers)
- No inline code fences in a row's text; keep the register register.
- A "pass" must be indistinguishable from real_clean on the spec in spec/style.md:
  judgement-first, one placed Probability Yardstick term, a checkable specific,
  British prose, no US "high confidence"/"degree of confidence", no hedging stacks,
  no antithesis/colon-label scaffolding.