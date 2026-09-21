#!/usr/bin/env python3
"""eval/bench.py — fine-tuned vs frozen-base A/B across fresh scenario prompts.

Generates each prompt with the LFM2.5 adapter and the frozen base, scores with
eval/metrics.py (lints + register), writes eval/bench_out.jsonl (model output
must not live beside training data in corpus/tasks/), and aggregates pass
rates. First output line is run metadata {timestamp, model, adapter_path,
sha256}; refuses to overwrite an existing output unless --force. Quantifies
whether the fine-tune actually moved the register over several fresh
(non-training) scenarios.

Usage: .venv/bin/python eval/bench.py [--adapter adapters/lfm2.5] [--out PATH] [--force]
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "eval"))
from metrics import lint_text  # noqa: E402
from lints import LINTS  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import yardstick  # noqa: E402  shared REGISTER_SYSTEM: inference must match the SFT system prompt

# Grounding checks are not register checks: a factless open-scenario prompt
# can never carry specifics or attach probability to a statistic, so folding
# them into `clean` made the headline number structurally impossible.
# Register lints gate; grounding is reported separately as grounded=N/8.
GROUNDING_LINTS = {"specifics", "category"}
REGISTER_LINTS = [name for name, _ in LINTS if name not in GROUNDING_LINTS]
FAIL_BELOW = 0.6

# Base must match the adapter's training run; --base / env override for
# non-default runs (e.g. the 2.6B capacity test).
BASE_MODEL = os.environ.get(
    "IC_BASE_MODEL", "mlx-community/LFM2.5-1.2B-Instruct-4bit")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_one(model, tokenizer, prompt, max_tokens=220,
                 temp=0.1, top_k=50, top_p=0.1, rep_penalty=1.05):
    """ChatML-templated generation against an already-loaded model.

    Same sampling config as scripts/generate.py; local so the model loads once
    per variant instead of once per prompt (measured 7.2-8.5s x 14-16 loads).
    """
    from mlx_lm import generate
    from mlx_lm.sample_utils import make_sampler, make_repetition_penalty
    sampler = make_sampler(temp=temp, top_p=top_p, top_k=top_k)
    lps = [make_repetition_penalty(rep_penalty)] if rep_penalty else []
    msgs = [{"role": "system", "content": yardstick.REGISTER_SYSTEM},
            {"role": "user", "content": prompt}]
    toks = tokenizer.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True)
    return generate(model, tokenizer, toks, max_tokens=max_tokens,
                    sampler=sampler, logits_processors=lps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default="adapters/lfm2.5")
    ap.add_argument("--base", default=None, help="base model path (must match the adapter's training run)")
    ap.add_argument("--out", default=os.path.join(ROOT, "eval", "bench_out.jsonl"))
    ap.add_argument("--force", action="store_true", help="overwrite an existing output file")
    ap.add_argument("--temp", type=float, default=0.3)
    ap.add_argument("--top-p", dest="top_p", type=float, default=0.9)
    args = ap.parse_args()

    out_path = args.out
    if os.path.exists(out_path) and not args.force:
        sys.exit("refusing to overwrite %s (pass --force)" % out_path)

    # anchor a relative adapter path on the repo root, not the cwd
    adapter_path = args.adapter if os.path.isabs(args.adapter) else os.path.join(ROOT, args.adapter)
    weights = os.path.join(adapter_path, "adapters.safetensors")
    meta = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": BASE_MODEL,
        "adapter_path": adapter_path,
        "sha256": _sha256(weights) if os.path.exists(weights) else None,
    }

    from mlx_lm import load
    # load each variant once, outside the prompt loop
    base_path = args.base or BASE_MODEL
    ft_model, ft_tok = load(base_path, adapter_path=adapter_path)[:2]
    base_model, base_tok = load(BASE_MODEL)[:2]

    prompts = [l.strip() for l in open(os.path.join(ROOT, "eval", "bench_prompts.txt")) if l.strip()]
    agg = {t: {"n": 0, "reg": 0, "grnd": 0, "banned": 0, "jf": 0} for t in ("ft", "base")}
    with open(out_path, "w") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for i, p in enumerate(prompts):
            ft = generate_one(ft_model, ft_tok, p, temp=args.temp, top_p=args.top_p)
            base = generate_one(base_model, base_tok, p)
            row = {"i": i, "prompt": p, "ft": ft, "base": base,
                   "temp": args.temp, "top_p": args.top_p}
            for tag, txt in (("ft", ft), ("base", base)):
                r, hits = lint_text(txt)
                reg_ok = all(r[n] >= FAIL_BELOW for n in REGISTER_LINTS)
                grnd_ok = all(r[n] >= FAIL_BELOW for n in GROUNDING_LINTS)
                row[tag + "_register"] = 1.0 if reg_ok else 0.0
                row[tag + "_grounded"] = 1.0 if grnd_ok else 0.0
                row[tag + "_lints"] = r
                agg[tag]["n"] += 1
                agg[tag]["reg"] += 1 if reg_ok else 0
                agg[tag]["grnd"] += 1 if grnd_ok else 0
                agg[tag]["banned"] += 1 if r["us_banned"] < 0.5 else 0
                agg[tag]["jf"] += 1 if r["judgement_first"] == 1.0 else 0
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{i}] FT_reg={row['ft_register']} FT_grounded={row['ft_grounded']} base_reg={row['base_register']}")
            print(f"   FT : {ft[:130]}")
            print(f"   BSE: {base[:130]}")
    print("\n===== aggregate (register lints gate; grounding reported separately) =====")
    for t in ("ft", "base"):
        a = agg[t]
        print("%-4s register=%d/%d  grounded=%d/%d  banned_rate=%.2f  judgement_first=%d/%d"
              % (t, a["reg"], a["n"], a["grnd"], a["n"],
                 a["banned"] / max(1, a["n"]), a["jf"], a["n"]))
    print("wrote", out_path)


if __name__ == "__main__":
    main()
