# eval — harness

- `lints.py` — deterministic rule lints on any text/corpus. Flags:
  - `yardstick_present` (a PHIA term present)
  - `us_banned` (US-confidence cadence, hedging stacks, Americanisms, `%`)
  - `contractions`, `antithesis`, `colon_label`, `sentence_variance`,
    `judgement_first`
  Each → 0..1; a fine-tuned model must be clean (`us_banned=0` banned items).
- `lints.py --corpus` — run over the built split files (report per split).

## Register classifier (`classifier.py`)

`classifier.py` — TF-IDF (bigrams) + logistic classifier over three classes
(UK-IC / US / press), trained on `corpus/train.jsonl` + `corpus/contrast.jsonl`.
The primary automated metric: fine-tuned model outputs must classify UK-IC;
base model must classify press/US.

## Judge (rubric)

Blind LLM-judge forced ranking between real KJs and model output, against
spec/style.md:
1. yardstick term present + correctly placed
2. judgement first, not buried
3. checkable specific attached
4. no US-confidence, no hedging, no antithesis, no colon-label scaffolding
5. British institutional prose, no contractions / Americanisms

## Operator blind test

5 fresh scenarios, outputs shuffled with real human blocks; operator must not
pick the model ≥4/5 times and ideally fails to identify it. This is the
definition of done.