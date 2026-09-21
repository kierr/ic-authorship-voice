# Dork pack — ic-authorship-voice source discovery

Every dork is a Google query (fall back to Bing/DDG — Google rate-limits).
Run each across the search tooling available; every *results-page* hit worth
carding becomes a row in `sources/manifest.json`. Verify each URL resolves
(webfetch / read_url); dead → Wayback CDX
(`web.archive.org/cdx/search/cdx?url=<host>&output=json&filter=statuscode:200&fl=original,timestamp,statuscode&collapse=urlkey&limit=20`).

Acceptance bar for a *positive-class* source ("key judgements type report"):
numbered or bulleted judgement block, estimative terms present, institutional
author, published by a government / parliamentary / inquiry body. Think-tank
and press go to contrast classes, never the positive class.

---

## P0 — positive class, high-value register product

| # | Dork | Intent |
|---|------|--------|
| 1 | `"key judgements" site:gov.uk filetype:pdf` | Direct KJ-section products. PHIA despatches / JIC assessments often attach a "Key Judgements" block. |
| 2 | `"key judgements" site:gov.uk` | Non-PDF pages with KJ content (collection pages, HTML despatches). |
| 3 | `"key points" site:isc.independent.gov.uk filetype:pdf` | ISC report "Key Points" sections (committee-over-IC register). |
| 4 | `"we assess" "highly likely" site:assets.publishing.service.gov.uk filetype:pdf` | JIC/PHIA despatches on the assets host. |
| 5 | `"joint intelligence committee" assessment filetype:pdf site:webarchive.nationalarchives.gov.uk` | Declassified JIC assessments in TNA webarchive. |
| 6 | `"probability yardstick" site:gov.uk` | The PHIA vocabulary spec page itself (spec input, not prose). |
| 7 | `"national strategic assessment" site:nationalcrimeagency.gov.uk filetype:pdf` | NCA law-enforcement-intelligence register; KJ sections. |
| 8 | `"report of the iraq inquiry" "executive summary" filetype:pdf` | Chilcot executive summary — the primary register commentary. |
| 9 | `"butler review" "weapons of mass destruction" filetype:pdf` | The Butler critique of JIC certainty-language drift (negative direction). |
| 10 | `"intelligence and security committee" "key points" filetype:pdf` | Redundant net for ISC KJ blocks. |
| 11 | `site:gov.uk novichok salisbury assessment filetype:pdf` | 2018 Salisbury attribution — a modern JIC assessment event. |
| 12 | `"hostile state activity" OR "foreign interference" site:gov.uk filetype:pdf assessment` | Modern threats register (IPS, counter-disinformation). |
| 13 | `site:discovery.nationalarchives.gov.uk "joint intelligence committee" assessment` | TNA Discovery catalogue entries → CAB 158/163 JIC series records. |
| 14 | `"intelligence community assessment" site:dni.gov filetype:pdf` | US ODNI ICA contrast source. |

## P1 — adjacent register / vocabulary spec

| # | Dork | Intent |
|---|------|--------|
| 15 | `"professional head of intelligence assessment" site:gov.uk` | PHIA publications index (probability yardstick, analytical standards). |
| 16 | `"defence intelligence" "update" ukraine site:gov.uk` | Defence Intelligence Ukraine despatches — terse dated DIS sub-register. |
| 17 | `"iraq's weapons of mass destruction" "assessment of the british government" filetype:pdf` | September Dossier 2002 — cautionary calibration set. |
| 18 | `"hutton inquiry" "iraq" filetype:pdf site:webarchive.nationalarchives.gov.uk` | Hutton Report — same period, foreword critique. |
| 19 | `"investigatory powers commissioner" annual report filetype:pdf site:ipco.org.uk` | Oversight register. |
| 20 | `"active cyber defence" ncsc annual review filetype:pdf site:ncsc.gov.uk` | Cyber-analytic gov register. |
| 21 | `"mutual evaluation" uk filetype:pdf site:fatf-gafi.org` | FATF UK ME — financial-crime register. |
| 22 | `site:fca.org.uk "final notice" filetype:pdf` | FCA financial-crime sanction register. |

## C — contrast classes (never positive)

| # | Dork | Intent |
|---|------|--------|
| 23 | `site:dni.gov "with high confidence" filetype:pdf` | US ICA wording — the US convention, for UK/US discriminator training. |
| 24 | `"russia report" isc guardian summary` | Press pair for the ISC Russia Report. |
| 25 | `"iraq inquiry" chilcot guardian analysis` | Press pair for Chilcot. |
| 26 | `site:rusi.org "key judgements" filetype:pdf` | Think-tank adjacent register. |
| 27 | `site:iiss.org "key judgements"` | IISS equivalent. |
| 28 | `("on the record" OR "clean skin" OR "hostile state") RUSI` | Think-tank hostile-state and cyber treatments. |

## Discovery maintenance

- Re-run quarterly (sources rot, new despatches publish).
- For a dead host: Wayback CDX first hit with statuscode 200 → use as the
  fetch URL; keep the original in `url_original` in the manifest.
- TNA Discovery catalogue search (`discovery.nationalarchives.gov.uk/results/r?_sd=&_q=...`)
  for CAB 158 (JIC post-war assessments) and CAB 163 (JIC after 1968) series;
  these are scanned — mark `extraction: ocr`.
- PHIA publications are discovered at
  `gov.uk/government/collections/...` — search "PHIA" / "Professional Head of
  Intelligence Assessment".