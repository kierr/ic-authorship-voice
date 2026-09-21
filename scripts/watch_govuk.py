#!/usr/bin/env python3
"""watch_govuk.py — sweep gov.uk for new assessment-class publications.

Runs the discovery queries that produced the session's kj-bearing
acquisitions (UKHSA briefings, OFSI threat assessments, Companies House SIA,
Nature Security Assessment), diffs against a known-URLs state file, and
prints only NEW candidates worth probing for Key Judgements structure.

Usage: .venv/bin/python scripts/watch_govuk.py [--all]
  --all   print every hit, not just new ones.
State: sources/.watch_known_urls.txt (committed; extend by acquisition).
"""
import os, sys, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "sources", ".watch_known_urls.txt")
UA = {"User-Agent": "ic-authorship-voice/0.1 (research; polite; contact: via repo)"}
QUERIES = [
    "threat assessment",
    "intelligence assessment",
    "national security risk assessment",
    "key judgements",
    "strategic intelligence assessment",
]
SKIP = ("accessible", "prevent-duty", "threat-levels", "national-risk-register-202",
        "unlocking-space", "sanctions-compliance-in-the-cryptoassets",
        "sanctions-compliance-in-the-financial", "sanctions-compliance-in-the-art",
        "sanctions-compliance-in-the-property", "sanctions-compliance-in-the-legal",
        "companies-house-strategic", "nature-security-assessment",
        "health-security-risk-assessment", "explaining-uncertainty",
        "teacher-assessment", "regulatory-judgement-cross-keys",
        "rpc-opinion-impact-of-national-security", "state-threats-act-2026-information",
        "statement-about-exercise-of-the-call-in-power", "phia-common-analytical",
        "advice-letter-grant-shapps")


def search(q):
    u = f"https://www.gov.uk/search/all?keywords={urllib.parse.quote(q)}&order=relevance"
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60) as r:
        h = r.read().decode("utf-8", "replace")
    return sorted(set(re.findall(r'href="(/government/publications/[^"#]+)"', h)))


import re  # late import keeps the query table above the plumbing

known = set()
if os.path.exists(STATE):
    with open(STATE) as f:
        known = {l.strip() for l in f if l.strip()}

fresh = []
for q in QUERIES:
    try:
        hits = search(q)
    except Exception as e:
        print(f"WARN {q!r}: {e}", file=sys.stderr)
        continue
    for x in hits:
        if x in known or any(p in x for p in SKIP):
            continue
        fresh.append(x)
    import time
    time.sleep(2.0)

if "--all" in sys.argv:
    for q in QUERIES:
        print("QUERY", q)
for x in sorted(set(fresh)):
    tag = "" if x in known else "NEW"
    if "--all" in sys.argv or tag:
        print(tag, x)
    known.add(x)

with open(STATE, "w") as f:
    f.write("\n".join(sorted(known)) + "\n")
print(f"watch: {len(fresh)} new candidates (state: {len(known)} known)")
