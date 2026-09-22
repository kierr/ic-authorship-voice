# ic-authorship-voice

A training corpus and fine-tune to teach a small model (LFM2.5, QLoRA/MLX) how to write in the UK IC authorship voice, and how to distinguish between UK/US/CA/AU IC assessment register.

It was developed because every general-purpose model, including SOTA/frontier closed models, fails to author content in the UK IC style. Observed failure modes:

- contamination with US IC/CIA-ICA cadence
- antithesis tics (X, not Y)
- hedging stacks (rather than PHIA Probability Yardstick + AncR)
- journalese, adjectives instead of evidence
- abstract vagueness, non-specific judgements

One contingent requirement: the model must be trained on unclassified sources, then used to build a synthetic corpus.

End goal: a fine-tuned model + eval harness + reproducible corpus.

## Quick start

```bash
# Clone and set up
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run all cheap gates (projection freshness, provenance, corpus validation, lint)
sh scripts/check.sh
```

## Target register

- **Estimative language is a controlled vocabulary.** The PHIA Probability Yardstick, 7 ascending terms: *remote chance, highly unlikely, unlikely, realistic possibility, likely or probable, highly likely, almost certain*.
- **Judgement first.** The assessment leads and evidence should follow.
- **Checkable specifics attached.** Dates, sums, names, filing references.
- **British institutional prose.** British spelling, no Americanisms, no contractions.
- **First-person institutional voice** ("we assess") is legitimate UK usage; "confidence" as a probability qualifier is US usage and banned.

## Pipeline

fetch → parse → segment → QA → build splits (sticky membership) → SFT tasks → consolidate → fine-tune mix → fine-tune (QLoRA/MLX, LFM2.5) → eval. One command: `sh scripts/check.sh` runs all cheap gates. See `AGENTS.md` for pipeline rules and `scripts/` for source code.

## Status

See `eval/state.md` (regenerated from measurements, never hand-typed). As of 2026-08-23: 128/150 real KJ items (≥150 gate UNMET), 8 publishers, best adapter passes 8/8 open-register and 7/8 grounded fact-bearing. Blind reading still distinguishes unanimously — this is a register-stylistics demonstrator with a measured gap, not an indistinguishability claim.

## Licencing

Code: MIT. Data: per-source — see `LICENSE` and `NOTICE.md`.
