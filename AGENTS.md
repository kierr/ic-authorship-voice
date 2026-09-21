# ic-authorship-voice — agent instructions

Rules and mechanics for developing this repo. Project description and status are in `README.md`.

## Non-negotiables

1. **No case-file data.** The repo must stay publishable. No private or case-file material enters it; the only carry-over is style rules derived from public documents.
2. **Provenance by tooling, never by typing.** `sources/manifest.json` is the registry SSOT. Never hand-type or hand-edit a sha256 — mutate the registry via `scripts/fetch.py --promote` (digests computed from bytes) and re-project with `scripts/manifest.py`. `sources/manifest.yaml` is a write-only projection: never edit it, never treat it as the ledger.
3. **Licence per source (provenance AND a gate).** Every fetched row carries `licence` for the record. Licence values that forbid redistribution must be resolved before public release — restricted content must be removed or a clear legal basis for redistribution established. See `NOTICE.md`.
4. **Real/synthetic separation.** `origin` on every sample; synthetic never enters val/test — *including fine-tune `valid.jsonl` surfaces*, which is where it actually leaked once.
5. **Synthetic may fabricate freely; it may never bind fabricated conduct to a real entity.** Invented allegations use coined fictional names (rows marked `entity: fictional`); grounded synthetic that accurately restates a real public notice may keep the real name and must carry lineage to that source. RATIONALE: a generator once attached invented sanctions-evasion claims to a real FCA-noticed firm and the rows reached the training mixes; the corpus is not "wrong" for fabricating — it is wrong only when fabrication carries a real name.
6. **Polite fetching.** ≤1 req/2s, honest self-identifying UA, no ToS-violating scraping.

## Gates — run them, never restate them

- `scripts/validate_corpus.py` must pass before committing data changes; it checks every id-bearing ledger, provenance hashes, split invariants, leakage into the canonical mix, chrome, and the entity rule above.
- `eval/report_gates.py` regenerates the gate table in `eval/state.md` from measurements. Never hand-type status numbers there or in README: a status that reads as measurement suppresses the re-check that would catch it stale — every hand-typed MET row in the 2026-08 audit was falsified when measured.
- One command: `sh scripts/check.sh` runs every cheap gate (projection freshness, raw provenance, corpus validation, lint selftest) and exits nonzero on any failure. Run it before finishing any session that touched data or pipeline code.

## Mechanics that bit us (do not regress)

- Sample ids are content-hashed (`hashlib`), never `hash()` — PYTHONHASHSEED salting once churned every id on every rebuild and collided at 16 bits.
- Split membership is sticky via `corpus/splits.json`; never reshuffle — a wholesale val migration once contaminated checkpoint selection.
- One adapter directory per training run (`adapters/<run>/`); an in-place overwrite destroyed the then-best mlx_vj weights once. `mlx_lm.lora --data` takes a **directory** (train/valid.jsonl), not a file.
- `corpus/tasks/mlx/` is the canonical scripted mix (`build_sft_all.py` → `build_mlx.py`); `mlx_vj/`, `mlx_cad/`, `mlx_nm/`, `mlx_terse/`, `mlx_d1/`, `mlx_curated/` are frozen deprecated snapshots kept for provenance — never train new work from them, and the leakage gate deliberately does not scan them.
- The fine-tune and the operator blind test are by-hand; the operator blind is human-graded and never self-approvable. Billed/external API calls need explicit approval; local MLX runs do not.
