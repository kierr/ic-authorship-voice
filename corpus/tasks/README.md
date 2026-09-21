# corpus/tasks — which files are canonical

**Canonical (scripted, gated):**
- `sft.jsonl` — built by `scripts/build_tasks.py` from `corpus/train.jsonl`.
- `sft_all.jsonl` — built by `scripts/build_sft_all.py`
  (sft + critique + synthetic, normalised keys).
- `mlx/` — the fine-tune mix, built by `scripts/build_mlx.py`
  (`train.jsonl` from sft_all; `valid.jsonl` from `corpus/val.jsonl`,
  document-grouped, real-only). `scripts/validate_corpus.py` leak-gates it.

**Frozen deprecated snapshots (provenance only — never train from these):**
`mlx_vj/`, `mlx_cad/`, `mlx_curated/`, `mlx_nm/`, `mlx_terse/`, `mlx_d1/`,
`mlx_chat.jsonl`. These are the hand-assembled 2026-08 experiment mixes,
kept because notes/decisions.md's results refer to them. They predate the
decontamination and are known-contaminated (held-out Chilcot text in train,
synthetic rows in some valid files); the entity-binding redaction was applied
to them, but the leakage was deliberately left as history. The validate gate
does not scan them (RATIONALE in scripts/validate_corpus.py).

`bench_out.jsonl` here is the historical bench location; `eval/bench.py` now
writes `eval/bench_out.jsonl` with run metadata.
