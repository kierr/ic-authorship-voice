# Register spec — UK intelligence-community assessment prose

Long-form register definition for fine-tuning. Three inputs, reconciled:
the current public PHIA vocabulary pages, Butler's style critique, and what is
actually observed in the corpus (`extracted/*.segments.jsonl`, `corpus/`).

Scope: this is the *base register*. House conventions (anonymisation, surname
styling) layer on at inference time, never into these weights.

---

## 1. Estimative language is a controlled vocabulary

### 1.1 The Probability Yardstick

The PHIA Probability Yardstick maps seven terms to probability ranges. Current
public version (`gov.uk` Explaining Uncertainty page; verified 2026-08-19):

| Term | Approx. range |
|---|---|
| Remote chance | >0% – ≈5% |
| Highly unlikely | ≈10% – ≈20% |
| Unlikely | ≈25% – ≈35% |
| Realistic possibility | ≈40% – <50% |
| Likely or probable | ≈55% – ≈75% |
| Highly likely | ≈80% – ≈90% |
| Almost certain | ≈95% – <100% |

The ranges omit the exact midpoints; terms are deliberately not numerically
precise (intelligence assessments are not based on quantitative data; the
Yardstick communicates intended range without false precision).

- A judgement carries **one** scaled term, correctly placed, **not** stacked.
- **note:** the yardstick was revised over time. The NCA National Strategic
  Assessment 2020 (fetched) reproduces an *older* split (e.g. "Almost Certain
  75/95–100%", eight-ish bands with percentages inline). The current page's
  seven-range split above is authoritative for fine-tuning; old and new both
  appear in the corpus — keep `era` in mind, and prefer the newer bands.

### 1.2 Confidence is the evidence base, not the likelihood

UK assessments carry **two orthogonal axes**:
  - Probability (Yardstick above) — how likely.
  - Analytical Confidence Rating (AnCR) — how *sound and stable* the basis is:
    High / Moderate / Low, judged on Information Base, Analytical Rigour,
    Complexity & Volatility.

The US register conflates these: "we assess **with high confidence**" treats
confidence as the probability qualifier. **That is the banned US usage.** A UK
assessment may say "we assess the probability as X **with moderate confidence**"
only when "moderate confidence" refers to the evidence base, and the Yardstick
term (not the confidence word) carries the likelihood. When in doubt, prefer
the Yardstick term + a confidence *statement*, not "confident as probability".

### 1.3 Register tells (observed corpus)

- "we assess", "we judge", "the JIC assessed" — first-person institution.
- Constructive example: "we assess that Iraq had played no role in the 9/11 attacks" — judgement leads, evidence follows.
- Single-source marks itself ("on one source", "single-source reporting").
- Corroboration signalled where it matters ("on the basis of… and…").

---

## 2. Judgement first, evidence after

The assessment leads the sentence; evidence follows after the semicolon or in
the following sentence. Never bury a judgement in a subordinate clause so the
reader cannot find it. Butler's critique: the opposite — burying the qualifier
and letting certainty creep up without the supporting base.

---

## 3. Checkable specifics attached

A real judgement carries the fact, the date, the sum, the share count, the
name, the filing reference. Vagueness is the model-slop signature — an
assessment with no checkable specific fails the register.

---

## 4. British institutional prose

- "per cent" (not %), £8m, "behaviour", no Americanisms (not "program"/"center").
- No contractions in formal product.
- Tight subordination; varied cadence (a uniform mechanical sentence is a tell).
- Distribution: real prose mixes the long multi-clause assessment sentence with
  short declarative judgements.

---

## 5. Banned (model-slop and US-contamination checklist)

US / contaminated:
- "high confidence", "moderate confidence" **as a probability qualifier**,
  "with high likelihood"-US cadence, "very likely".
- "we assess with high confidence" — rewrite as Yardstick term + evidence-base.

Model tics:
- Antithesis opener "X, not Y:" ("The scheme is a reprint, not an invention:").
- Colon-label scaffolding ("Assessment: …", "Likelihood: …" paragraph openers).
- Hedging stacks: "could potentially", "may possibly", "it could be argued",
  "somewhat", "arguably".
- Journalese: adjectives doing the work of evidence, throat-clearing, narrative
  tension, rhetorical questions.
- American "program/%%", "%", contractions.

---

## 6. Butler's critique — the negative dimension

Butler (2004) reports **assessment creep**: certainty-language drift vs the
evidence base — a judgement's confidence ratcheting up between drafts without
new information. This is the *negative* register: do not let the model drift
upwards either; the Yardstick term must match what the evidence supports.
A model output that infers "almost certain" where the source only supports
"realistic possibility" fails as surely as US contamination.

---

## 7. Anti-contamination directives

- No case-file data, no house conventions, no client names (§2).
- Synthetic augmentation must be grounded (§8) and is always labelled.
- The fine-tune teaches the base register; any client layers house rules at
  inference time only.

---

## Maintenance

- Re-derive the spec with each added decade (Cold War CAB 158 JIC prose differs
  an open decision).
- Re-confirm the Yardstick bands against the live PHIA page before every
  public release (they are versioned and may again be amended).
## ADOPTED 2026-08-22 (operator delegation; 3-reviewer consensus ADOPT-WITH-CHANGES):
analytic confidence vs event probability

Fresh-context generation (corpus/synth_fable.jsonl, zero-shot batch) showed a
strong model's native UK register separates two axes the current spec
conflates:

- event probability — the 7-term Yardstick ("highly likely ...");
- analytic confidence in the evidence base — "We have moderate confidence in
  this judgement" — which is genuine PHIA doctrine (PHIA's professional
  development material uses confidence-in-source separate from likelihood)
  and standard JIC-adjacent practice.

The current blanket ban (US cadence rule: no "confidence" qualifiers) exists
because the failure mode it targets is the US ICA pattern "we assess with
HIGH CONFIDENCE that X" — confidence welded to the assessment verb as a
probability substitute. That is not what analytic-confidence statements do.

Amendment (as adopted, with the reviewers' tightenings):
1. Confidence-as-probability stays banned ("with high confidence, X will
   happen") — the US tell. Same-clause exclusion: no confidence term may
   appear in ANY position within the clause that carries the estimative
   judgement.
2. Analytic-confidence clauses are permitted only grammatically detached
   from the judgement — parenthetical, footnote, or appended clause — AND
   every one must state its evidential grounds, e.g. "(moderate confidence:
   single-source reporting of uncertain provenance)". A bare confidence
   parenthetical without grounds is still a violation.
3. Enforced by eval/lints.py lint_confidence: any confidence phrase outside
   a grounds-bearing parenthetical is a failure.

OVERTURNING CONDITION (consensus 2026-08-23): any observed fabricated-grounds
parenthetical pattern — grounds-free confidence clauses or boilerplate grounds
gaming the allowance — triggers immediate tightening to a blanket ban.

## Lexical register (operator critique 2026-08-23)

Institutional diction only: render investigative or fintech slang into
formal register ("payment infrastructure"/"transfer corridors", never
"rails"; "funds", never "money moves"). The model must not echo source-note
vocabulary — rendering messy input into house prose is the style-transfer
task. Enforced by judge screening (slang echo fails) rather than an
enumerated lexicon: the slang surface is unbounded, the register target is
not.
