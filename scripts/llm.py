#!/usr/bin/env python3
"""scripts/llm.py — minimal OpenAI-compatible chat client (stdlib only).

Uses the operator-provided free endpoint by default; override with IC_LLM_URL /
IC_LLM_MODEL / IC_LLM_KEY env vars.

Usage:
  from llm import chat
  text = chat([{"role":"user","content":"..."}], temperature=0.3)
  # or CLI: .venv/bin/python scripts/llm.py "prompt here"
"""
import json
import os
import sys
import urllib.request

URL = os.environ.get("IC_LLM_URL", "")
MODEL = os.environ.get("IC_LLM_MODEL", "")
KEY = os.environ.get("IC_LLM_KEY", "")


def chat(messages, temperature=0.3, max_tokens=6000, seed=None, retries=2):
    # max_tokens 6000: the endpoint model reasons internally (usage reports
    # reasoning_tokens); a small budget returns empty content mid-thought.
    body = {"model": MODEL, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens}
    if seed is not None:
        body["seed"] = seed
    data = json.dumps(body).encode()
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(URL, data=data, headers={
                "content-type": "application/json",
                "user-agent": "ic-authorship-voice/1.0",
                **({"authorization": f"Bearer {KEY}"} if KEY else {})})
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.load(r)
            return d["choices"][0]["message"]["content"]
        except Exception as e:
            last = e
            import time
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"llm.chat failed after {retries + 1} attempts: {last}")


if __name__ == "__main__":
    print(chat([{"role": "user", "content": " ".join(sys.argv[1:])}]))
