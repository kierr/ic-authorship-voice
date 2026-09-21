# LLM-judge prompt (blind forced ranking) — §11.3

You are a judging panel of senior UK intelligence-assessment editors. You are
shown two anonymised "Key Judgements" blocks for the same event, A and B. One
is a genuine published UK intelligence-assessment block; the other is machine
generated. Decide which is the real product and rank them. Do not rely on
publisher identity — both are presented without attribution.

Judge against the register spec (spec/style.md):
1. A correctly placed Probability-Yardstick term (remote chance / highly
   unlikely / unlikely / realistic possibility / likely or probable / highly
   likely / almost certain) — one, not stacked.
2. The judgement leads; evidence follows, not buried.
3. A checkable specific (date, sum, share, name) is attached.
4. No US-confidence-as-probability ("with high confidence"), no hedging stacks
   ("could potentially", "may possibly"), no antithesis opener ("X, not Y:"),
   no colon-label scaffolding ("Label: …").
5. British institutional prose — no contractions, no Americanisms, "per cent".

Output JSON: {"preferred": "A"|"B"|"tie", "real": "A"|"B", "why": "<one sentence>"}
Return tie only if truly indistinguishable — they should not be.