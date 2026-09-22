#!/usr/bin/env python3
"""segment.py — split parsed text into corpus segments.

Reads extracted/<id>.json (list of {page, text}) for fetched sources and emits
extracted/<id>.segments.jsonl — one sample per line:

  Confidence sentences  class=confidence_statements  (any sentence that uses a
      UK PHIA Probability Yardstick term; these are the sentence-level register
      anchors).
  Key judgement blocks  class=key_judgements — captured only where a heading
      such as "Key Judgements / Key Points / Key findings" is present, with the
      numbered/bulleted items that follow, plus block context.

Every sample carries: id, class, origin=real, source_id (manifest id), url,
publisher, published, licence (from sources/manifest.json), page, text,
block_context, and qa=pass|flag (auto-flag on obvious OCR/redaction garble).

Usage: .venv/bin/python scripts/segment.py [manifest.json]
"""
import hashlib
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import yardstick  # shared PHIA vocab: TERM_RE / find_terms / CHROME_RE

ROOT = os.path.dirname(_HERE)
EXT = os.path.join(ROOT, "extracted")
MANIFEST = os.path.join(ROOT, "sources", "manifest.json")

# Redaction / OCR garble markers that should be QA-flagged.
GARBLE_RE = re.compile(r"\*{3,}|XXXX|\\u00|\{\{\{")

KEY_HEADINGS = re.compile(
    r"(?im)(key\s+judgements?|key\s+(points|findings|messages|headlines|takeaways)|"
    r"headline\s+findings|(main|overall)\s+judgements?|"
    r"summary\s+of\s+(key\s+)?(judgements?|points|findings))\s*:?\s*$"
)

# Explicit class allowlists — unknown classes hard-stop.
# RATIONALE: routing used to be "contrast tuple, else positive", so any class
# outside the tuple (e.g. a fetched spec-class source) flowed into training.
POSITIVE_CLASSES = ("key_judgements", "full_assessment", "confidence_statements")
CONTRAST_CLASSES = ("negative_us", "contrast_misc",
                    "ca_ic", "au_ic", "negative_llm", "spec")


def sentence_split(text):
    """Crude but sufficient sentence splitter for institutional prose."""
    text = re.sub(r"[ \t]+", " ", text)
    parts = re.split(r"(?<=[a-z0-9\)\]\"])\.(?=\s+[A-Z0-9\"])|(?<=[a-z0-9\)\]\"])\.$", text)
    return [p.strip() for p in parts if p.strip()]


def norm_ws(t):
    return re.sub(r"\s+", " ", t).strip()


def main():
    mpath = MANIFEST if len(sys.argv) < 2 else sys.argv[1]
    meta = {}
    with open(mpath) as f:
        rows = json.load(f)
    rows = rows if isinstance(rows, list) else rows["sources"]
    for r in rows:
        # RATIONALE: duplicate ids let the later row shadow the earlier one,
        # which stripped sha256 from 36 emitted samples; hard-stop instead.
        if r["id"] in meta:
            raise SystemExit("FATAL: duplicate manifest id %s" % r["id"])
        meta[r["id"]] = r

    counts = {}
    for jf in sorted(os.listdir(EXT)):
        if not jf.endswith(".json"):
            continue
        sid = jf[:-5]
        if sid not in meta:
            continue
        src = meta[sid]
        cls = src.get("class", "")
        if cls not in POSITIVE_CLASSES and cls not in CONTRAST_CLASSES:
            raise SystemExit("FATAL: %s has unknown class %r" % (sid, cls))
        # Every emitted record for a fetched source must carry its content hash.
        if not str(src.get("sha256", "")).strip():
            raise SystemExit("FATAL: %s fetched but manifest sha256 is empty" % sid)
        with open(os.path.join(EXT, jf)) as f:
            pages = json.load(f)
        out = os.path.join(EXT, sid + ".segments.jsonl")
        # Contrast classes feed the register-classifier, not the positive stream:
        # one record per non-empty page, so US/press prose never pollutes
        # confidence_statements (which would contaminate the fine-tune target).
        if cls in CONTRAST_CLASSES:
            n = 0
            with open(out, "w") as fh:
                for page in pages:
                    text = norm_ws(page.get("text", ""))
                    if not text:
                        continue
                    pno = page.get("page", 0) + 1
                    fh.write(json.dumps({
                        "id": "%s-%s-%03d" % (sid, cls, pno),
                        "class": cls,
                        "origin": "real",
                        "source_id": sid,
                        "url": src.get("url", ""),
                        "publisher": src.get("publisher", ""),
                        "published": src.get("published", ""),
                        "licence": src.get("licence", "check"),
                        "sha256": src.get("sha256", ""),
                        "page": pno,
                        "text": text[:200000],
                        "qa": "flag" if GARBLE_RE.search(text) else "pass",
                    }, ensure_ascii=False) + "\n")
                    n += len(text)
            print("%-30s contrast -> %s (%d chars)" % (sid, cls, n))
            counts[sid] = ("-", "-", "-")
            continue
        n_kj_blocks = 0
        g = 0
        recs = []  # buffered so kj records can drop their duplicate cs rows
        kj_dupes = set()  # normalised sentences shipped inside any kj record
        seen_cs = set()  # (page, sentence-hash): a sentence repeated verbatim
        # within one page (exec summaries restate findings) would emit two
        # records with the SAME content-hash id — caught by the validate gate.
        for page in pages:
            pno = page["page"]
            text = page["text"]
            # ---- block detection: a key-judgement heading page ----
            for bm in KEY_HEADINGS.finditer(text):
                block_start = bm.end()
                block = text[block_start:]
                # collect numbered/bulleted lines until an unnumbered new heading
                items = []
                for line in block.splitlines():
                    ls = line.strip()
                    if not ls:
                        continue
                    if re.match(r"^(?:[A-Z][A-Z0-9 .\-]{3,}|[A-Z][a-z]+ [A-Z][a-z]+:)$", ls):
                        break  # likely next heading
                    items.append(norm_ws(ls))
                if items:
                    # Fix A: check estimative content on the FULL collected
                    # item list BEFORE truncation — v0 checked the 600-char
                    # cut and dropped blocks whose ladder terms sat past 600.
                    full_block = " ".join(items)
                    if not yardstick.find_terms(full_block) or \
                            yardstick.CHROME_RE.search(full_block):
                        print("WARN %s: heading-path kj without estimative "
                              "content (page %d)" % (sid, pno + 1))
                        continue
                    # Fix B: chunked emission — blocks >900 chars emit up to
                    # 3 chunks split at item boundaries (~<=600 chars each),
                    # each gated per-chunk. Cap 6 records/source.
                    if len(full_block) <= 900:
                        chunks_to_emit = [full_block[:900]]
                    else:
                        chunks_to_emit = []
                        cur_chunk, cur_len = [], 0
                        for it in items:
                            ilen = len(it) + (1 if cur_chunk else 0)
                            if cur_len + ilen > 600 and cur_chunk:
                                chunks_to_emit.append(" ".join(cur_chunk))
                                if len(chunks_to_emit) >= 3:
                                    break
                                cur_chunk, cur_len = [], 0
                            cur_chunk.append(it)
                            cur_len += ilen
                        if cur_chunk and len(chunks_to_emit) < 3:
                            chunks_to_emit.append(" ".join(cur_chunk))
                    emitted_from_block = 0
                    for chunk_text in chunks_to_emit[:3]:
                        if not chunk_text.strip() or \
                                not yardstick.find_terms(chunk_text) or \
                                yardstick.CHROME_RE.search(chunk_text):
                            continue
                        if g >= 6:
                            break
                        kj_dupes.update(norm_ws(s2) for s2 in sentence_split(chunk_text))
                        recs.append({
                            "id": "%s-%s-%03d" % (sid, "kj", g),
                            "class": "key_judgements",
                            "origin": "real",
                            "source_id": sid,
                            "url": src.get("url", ""),
                            "publisher": src.get("publisher", ""),
                            "published": src.get("published", ""),
                            "licence": src.get("licence", "check"),
                            "sha256": src.get("sha256", ""),
                            "page": pno + 1,
                            "block_context": (bm.group(0)[:120]),
                            "text": chunk_text,
                            "qa": "flag" if GARBLE_RE.search(chunk_text) else "pass",
                        })
                        n_kj_blocks += 1
                        g += 1
                        emitted_from_block += 1
            # ---- sentence-level confidence statements ----
            for sent in sentence_split(text):
                if not (yardstick.TERM_RE.search(sent) and len(sent) > 60):
                    continue
                ns = norm_ws(sent)
                cs_key = (pno, hashlib.sha256(sent.encode("utf-8")).hexdigest()[:8])
                if cs_key in seen_cs:
                    continue
                seen_cs.add(cs_key)
                snippet = ns[:500]
                if len(ns) > 500:
                    # Cut at a word boundary — mid-word truncation shipped 18
                    # rows that taught truncated output as copy-task targets.
                    snippet = snippet.rsplit(" ", 1)[0]
                # The 500-char cut can land before the yardstick term; a
                # term-less sample is useless, so require survival post-cut.
                if not yardstick.find_terms(snippet):
                    continue
                # RATIONALE: hash() is PYTHONHASHSEED-salted — ids churned on
                # every rebuild and the 16-bit mask collided
                # (nca-nsa-2024-cs-006-a6a9 named two sentences); sha256 is
                # stable content-addressing.
                recs.append({
                    "id": f"{sid}-cs-{pno:03d}-{hashlib.sha256(sent.encode('utf-8')).hexdigest()[:8]}",
                    "class": "confidence_statements",
                    "origin": "real",
                    "source_id": sid,
                    "url": src.get("url", ""),
                    "publisher": src.get("publisher", ""),
                    "published": src.get("published", ""),
                    "licence": src.get("licence", "check"),
                    "sha256": src.get("sha256", ""),
                    "page": pno + 1,
                    "text": snippet,
                    "qa": "flag" if GARBLE_RE.search(sent) else "pass",
                    "_sent": ns,  # dedupe key vs the KJ fallback; popped on write
                })
        # Fallback for key_judgements-class short assessments (DIS updates: each
        # update IS one terse estimative judgement). If no heading block captured,
        # emit the 8-90-word yardstick sentences as a single KJ record. No
        # whole-page fallback: flattened pages wrote nav menus into train/val
        # as qa:pass key judgements.
        if n_kj_blocks == 0 and cls == "key_judgements" and src.get("extract", "") == "html":
            sentences = []
            for page in pages:
                for sent in sentence_split(page.get("text", "")):
                    wc = len(sent.split())
                    ns = norm_ws(sent)
                    if (yardstick.TERM_RE.search(sent) and 8 <= wc <= 90
                            and not yardstick.CHROME_RE.search(ns)):
                        sentences.append(ns)
            # Whole sentences within the 900-char budget: a hard [:900] slice
            # cut mid-sentence, and deduping against ALL candidate sentences
            # silently dropped cs rows whose sentence never shipped in the kj.
            included, total = [], 0
            for s in dict.fromkeys(sentences):
                if total + len(s) + (1 if included else 0) > 900:
                    break
                included.append(s)
                total += len(s) + (1 if total else 0)
            full = " ".join(included)
            if full.strip() and yardstick.find_terms(full):
                # RATIONALE: kj takes precedence within a doc — single-sentence
                # DIS briefs were double-counted as both kj and cs, so the same
                # sentences must not also ship as confidence_statements. Only
                # sentences the record actually carries are deduped.
                kj_dupes.update(included)
                recs.append({
                    "id": "%s-kj-000" % sid,
                    "class": "key_judgements",
                    "origin": "real",
                    "source_id": sid,
                    "url": src.get("url", ""),
                    "publisher": src.get("publisher", ""),
                    "published": src.get("published", ""),
                    "licence": src.get("licence", "check"),
                    "sha256": src.get("sha256", ""),
                    "page": 1,
                    "text": full,
                    "qa": "flag" if GARBLE_RE.search(full) else "pass",
                })
            else:
                print("WARN %s: no estimative content" % sid)
        n_ks = n_cs = n_flag = 0
        with open(out, "w") as fh:
            for rec in recs:
                sent_key = rec.pop("_sent", None)
                if sent_key is not None and sent_key in kj_dupes:
                    continue
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if rec["class"] == "key_judgements":
                    n_ks += 1
                else:
                    n_cs += 1
                n_flag += 1 if rec["qa"] == "flag" else 0
        counts[sid] = (n_ks, n_cs, n_flag)
        print("%-30s kj=%-4d cs=%-5d flag=%-3d" % (sid, n_ks, n_cs, n_flag))
    print("done")


if __name__ == "__main__":
    main()
