#!/usr/bin/env python3
"""scripts/generate.py — register text from the LFM2.5 QLoRA adapter.

Base: mlx-community/LFM2.5-1.2B-Instruct-4bit. Adapter: adapters/lfm2.5.
Sampling: temp 0.3 / top_p 0.9 — the measured-best register cell of the
2026-08-22 sweep (8/8 register-clean; t0.5 buys
diversity at a register cost). Applies the ChatML template (system + user).

Exposes run_templated() for embedding (eval/bench.py) and a CLI.

Usage: .venv/bin/python scripts/generate.py --prompt "<task>" [--adapter adapters/lfm2.5]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yardstick  # shared REGISTER_SYSTEM: inference must match the SFT system prompt


def run_templated(prompt, adapter="adapters/lfm2.5", max_tokens=400,
                  temp=0.3, top_k=50, top_p=0.9, rep_penalty=1.05,
                  base_model=None):
    from mlx_lm import load, generate
    from mlx_lm.sample_utils import make_sampler, make_repetition_penalty
    # Base must match the adapter's training run (an adapter trained on the
    # 2.6B cannot load onto the 1.2B); env override for non-default bases.
    base = base_model or os.environ.get("IC_BASE_MODEL",
                                        "mlx-community/LFM2.5-1.2B-Instruct-4bit")
    adapter = adapter or None
    model, tokenizer = load(base, adapter_path=adapter)[:2]
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
    ap.add_argument("--base", default=None)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--max", type=int, default=400)
    ap.add_argument("--temp", type=float, default=0.3)
    args = ap.parse_args()
    print(run_templated(args.prompt, args.adapter, args.max, temp=args.temp, base_model=args.base))


if __name__ == "__main__":
    main()