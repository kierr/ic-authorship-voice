"""yardstick.py — canonical PHIA Probability Yardstick vocabulary and the
shared register system prompt.

spec/style.md is the human authority; this module is its one code encoding.
Importers: scripts/segment.py, scripts/build_tasks.py, eval/lints.py.
"""
import re

# The seven current PHIA terms (spec/style.md §1.1), ladder order.
CANONICAL = (
    "remote chance",
    "highly unlikely",
    "unlikely",
    "realistic possibility",
    "likely or probable",
    "highly likely",
    "almost certain",
)

# Surface variants observed in real corpus prose, mapped to canonical terms.
# NOTE bare "remote", bare "almost always", and "high likelihood" are NOT
# yardstick terms and must never match.
ALIASES = {
    "likely": "likely or probable",
    "probable": "likely or probable",
    "probably": "likely or probable",
    "almost certainly": "almost certain",
}

# Longest-first so "highly unlikely" wins over "unlikely" and "almost
# certainly" over "almost certain"; \b so "improbable"/"likelihood" never hit.
_SURFACES = sorted(CANONICAL + tuple(ALIASES), key=len, reverse=True)
TERM_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(s) for s in _SURFACES) + r")\b",
    re.IGNORECASE)


def find_terms(text):
    """Matched yardstick surfaces, in document order."""
    return [m.group(0) for m in TERM_RE.finditer(text)]


def canonicalize(surface):
    """Canonical PHIA term for a matched surface."""
    s = re.sub(r"\s+", " ", surface.strip().lower())
    return ALIASES.get(s, s)


# Page-chrome sentinels from HTML-extracted press sources (nav menus, share
# bars, correction footers, template/CMS markup); a segment containing one is
# chrome, not prose. Literal strings are site furniture; the raw patterns
# catch markup classes (HTML comments, {{template}} vars, [data-...] attrs,
# undecoded entities) rather than enumerating sites.
CHROME_RE = re.compile("|".join(
    [re.escape(s) for s in (
        "Make us preferred on Google",
        "Corruption Watch",
        "Classifieds",
        "Share Facebook",
        "Kyiv Post is Ukraine",
        "To suggest a correction",
        "Flip Share",
        "Podcasts Analysis",
        "Copy Copied",
        "LinkedIn Bluesky",
        "(Twitter)",
        "By Kyiv Post",
        "news organization, reporting since",
    )] + [
        r"<!--",                # HTML comments survive tag-stripping
        r"\{\{[^}]*\}\}",       # CMS template variables
        r"\[data-[a-z-]+",      # attribute selectors leaked as text
        r"&[a-z]+;|&#\d+;",     # undecoded HTML entities
        r"</?[a-z]+[^>]*>",     # any residual literal tag
    ]))

# Shared text normalisation for leakage/duplicate comparison. A verbatim leak
# once evaded an exact-match gate through a single curly-quote variant, so
# every gate comparing text across surfaces must compare through this.
_QUOTE_MAP = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", " ": " ",
})


def norm_text(t):
    """Whitespace-, quote-, and dash-normalised form for cross-surface
    equality and containment checks (leak gates, dedupe)."""
    return re.sub(r"\s+", " ", (t or "").translate(_QUOTE_MAP)).strip()


def shingles(t, k=12):
    """k-token shingle set of the normalised text, for near-duplicate
    containment (consecutive-day DIS reissues are ~80% identical and evade
    every exact gate)."""
    toks = norm_text(t).lower().split()
    if len(toks) < k:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1)}


# Union of the build_tasks.py and generate.py rule sets; the single shared
# system prompt for SFT pairs, generation, and eval.
REGISTER_SYSTEM = (
    "Write in the UK intelligence community assessment register: "
    "judgement-first British institutional prose; one correctly placed "
    "PHIA Probability Yardstick term and no other estimative vocabulary "
    "(remote chance, highly unlikely, unlikely, realistic possibility, "
    "likely or probable, highly likely, almost certain); a checkable "
    "specific; British spelling, no Americanisms; 'per cent', never '%'; "
    "no contractions; no US 'we assess with confidence' cadence; "
    "no hedging stacks."
)
