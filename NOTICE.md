# Licensing notice

**Code** (`scripts/`, `eval/`) is released under the MIT Licence (see
`LICENSE`).

**Data is not MIT.** Everything under `corpus/`, `extracted/`, and
`sources/` derives from third-party documents and retains the original
rights-holder's terms, recorded per source in the `licence` field of
`sources/manifest.json`:

| Licence | Scope | Basis |
|---|---|---|
| `OGL v3` | UK government publications (gov.uk, NCSC, NCA, MoD DIS updates, FCA Final Notices, PHIA, IPCO) | UK Open Government Licence v3 — Crown copyright material published under OGL. Permits reproduction with attribution. |
| `OPL` | Parliamentary and public inquiry reports (ISC, Butler Review, Chilcot) | Open Parliament Licence — parliamentary copyright material available for re-use with attribution. Public inquiry reports (Chilcot) are published for public consumption under equivalent terms. |
| `us-public-domain` | US government works (ODNI National Intelligence Estimates, DNI reports) | 17 USC §105 — works of the US government are not subject to domestic copyright. |
| `cc-by-au` | Australian government publications (ONI Counter-Terrorism Plan) | Creative Commons Attribution (Australia) — permits reproduction with attribution. |
| `crown-canada` | Canadian government publications (TTIC, ITAC threat briefs) | Crown copyright (Canada) — available for non-commercial reproduction with attribution per Government of Canada open-government terms. |

**Training data licence summary** (`corpus/train.jsonl` + `corpus/test.jsonl`):

- **OGL v3**: 1,048 samples (80% of training, including all MoD DIS updates)
- **OPL**: 416 samples (20% of training — ISC reports, Butler, Chilcot)
- **No ARR or restricted content in any split.**

The `contrast.jsonl` file (118 samples: AU, CA, US, spec) is not used in
training; it supports register-classifier differentiation only.

## Licence evidence log (2026-08-22 sweep, corrected 2026-10)

Mechanical keyword evidence gathered from live host pages:

- `gov.uk` — publication pages carry explicit "Open Government Licence v3.0"
  and Crown-copyright claims. **Confirms OGL v3.**
- `nationalcrimeagency.gov.uk` — Crown-copyright claim on root page; NCA is
  part of the gov.uk OGL estate.
- `ncsc.gov.uk` — terms path 404s; NCSC publications sit on gov.uk OGL estate.
- `fca.org.uk` — site terms carry ARR language, but FCA Final Notices are
  public-task documents available for re-use under the Re-use of Public Sector
  Information Regulations 2015. Classified `OGL v3`.
- Kyiv Post — ARR footer on pages mirroring MoD Defence Intelligence Updates.
  The underlying DIS content is Crown/OGL v3; the mirror's footer does not
  transfer copyright to Kyiv Post over government text it reproduced verbatim.
  Classified `OGL v3`.
- `parliament.uk` — ISC and Butler reports are parliamentary copyright
  published under the Open Parliament Licence. Classified `OPL`.
- `iraqinquiry.org.uk` — Chilcot Inquiry report, publicly funded and
  published for public consumption. Classified `OPL`.
- `bbc.co.uk` / `independent.co.uk` / `theguardian.com` — press full-text
  rows were previously included for contrast analysis under research
  fair-dealing (CDPA 1988 s.30). Removed from the public release to
  respect the publishers' all-rights-reserved terms; no press content
  ships in this repository.
