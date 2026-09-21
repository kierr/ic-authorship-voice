# Contributing to ic-authorship-voice

## Data changes

Any change to corpus data must pass `sh scripts/check.sh` before committing.
This runs provenance validation, split invariants, leakage gates, and
projection freshness checks. Do not hand-edit `sources/manifest.yaml` — it is
a write-only projection of `sources/manifest.json`.

## Adding sources

1. Add the source entry to `sources/manifest.json` via `scripts/fetch.py --promote`
   (digests are computed from fetched bytes — never hand-type a sha256).
2. Re-project with `scripts/manifest.py`.
3. Run `sh scripts/check.sh`.

## Synthetic data rules

- Every synthetic row must carry `"origin": "synthetic"`.
- Synthetic samples must never appear in val or test splits.
- Invented allegations must use coined fictional names (`"entity": "fictional"`);
  grounded synthetic that restates a real public notice may keep the real name
  and must carry lineage to that source.

## Code style

Python 3.11+. Type hints on public functions. No external dependencies beyond
the standard library and PyYAML (for manifest projection).

## Reporting issues

Open a GitHub issue with a clear description and reproduction steps.
