#!/usr/bin/env python3
"""format_ic.py — transform investigation notes into UK/US IC assessment format.

The operator-facing tool: point it at messy notes (markdown/plain text),
get back a judgement-first assessment document in the target register.
Uses the champion adapter locally via mlx-lm; no network, no data leaves
the machine.

Pipeline per section of input:
  1. Facts are stated as facts (documentary evidence, no yardstick terms).
  2. Inferences beyond evidence carry PHIA yardstick terms.
  3. Judgement-first structure; checkable specifics preserved.
  4. Institutional diction throughout (slang rendered into register).

Usage:
  .venv/bin/python scripts/format_ic.py notes.md [--style uk|us] \
      [--adapter adapters/lfm2.5-clean7-fable] [--out assessment.md] \
      [--temperature 0.3]

Style 'uk' = PHIA Probability Yardstick register (default).
Style 'us' = ICD-203 confidence-register variant (system-prompt swap).
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from llm import chat  # noqa: E402

STYLE_PROMPTS = {
    "uk": (
        "You are a UK intelligence-community assessment drafter. Transform "
        "the investigator's notes below into a formal UK IC assessment.\n"
        "Rules: lead with Key Judgements; attach PHIA Probability Yardstick "
        "terms (remote chance / highly unlikely / unlikely / realistic "
        "possibility / likely or probable / highly likely / almost certain) "
        "to inferences ONLY — documentary facts are stated plainly without "
        "probability language; keep every specific (dates, sums, names, "
        "references); British institutional prose ('per cent', no "
        "contractions); render slang into institutional diction; end with an "
        "outlook line graded by the same yardstick."
    ),
    "us": (
        "You are a US intelligence-community assessment drafter (ICD-203 "
        "style). Transform the investigator's notes below into a formal "
        "analytic assessment. Rules: lead with key judgements; express "
        "likelihood as probability language attached to inferences; state "
        "documented facts plainly; add confidence levels (high/moderate/low) "
        "with stated grounds only where evidential basis warrants; preserve "
        "all specifics; professional analytic prose."
    ),
}


def read_input(path):
    if path == "-":
        return sys.stdin.read()
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        import pymupdf
        return "\n".join(p.get_text() for p in pymupdf.open(path))
    return open(path, encoding="utf-8", errors="replace").read()


def chunk_notes(text, max_chars=6000):
    """Split long notes at heading boundaries so each chunk fits the model."""
    if len(text) <= max_chars:
        return [text]
    lines = text.split("\n")
    chunks, cur = [], []
    cur_len = 0
    for line in lines:
        if cur_len + len(line) > max_chars and (
                line.startswith("#") or line.strip() == "") and cur:
            chunks.append("\n".join(cur))
            cur, cur_len = [], 0
        cur.append(line)
        cur_len += len(line)
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def main():
    ap = argparse.ArgumentParser(
        description="Transform investigation notes into IC assessment format")
    ap.add_argument("input", help="notes file (.md/.txt/.pdf) or - for stdin")
    ap.add_argument("--style", choices=["uk", "us"], default="uk")
    ap.add_argument("--adapter", default="adapters/lfm2.5-clean7-fable")
    ap.add_argument("--base", default=None,
                    help="base model path (must match adapter's training run)")
    ap.add_argument("--out", default=None, help="output file (default stdout)")
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--engine", choices=["local", "api"], default="api",
                    help="api = OpenAI-compatible endpoint (best quality, default); local = mlx-lm on this Mac (private, no network)")
    args = ap.parse_args()

    text = read_input(args.input)
    if not text.strip():
        sys.exit("empty input")

    base = args.base or os.environ.get("IC_BASE_MODEL",
                                       "mlx-community/LFM2.5-1.2B-Instruct-4bit")
    os.environ["IC_BASE_MODEL"] = base

    from generate import run_templated
    system_style = STYLE_PROMPTS[args.style]
    prompt = f"{system_style}\n\nNOTES:\n{text}"

    if args.engine == "api":
        from llm import chat
        result = chat([{"role": "system", "content": system_style},
                       {"role": "user", "content": text}],
                      temperature=args.temperature, max_tokens=4000)
    else:
        result = run_templated(prompt, adapter=args.adapter,
                               max_tokens=2000, temp=args.temperature)

    header = (f"# Assessment ({args.style.upper()} style)\n\n"
              f"_Source: {os.path.basename(args.input)}_\n\n")
    output = header + result
    if args.out:
        with open(args.out, "w") as f:
            f.write(output)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
