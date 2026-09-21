#!/usr/bin/env python3
"""parse.py — extract text (with page anchors) from fetched raw/* → extracted/.

Reads sources/manifest.json (hand-of-record; read-only here). For every fetched
source (bound to a raw/ file), verifies the raw file's sha256 against the
manifest row, then extracts per-page text and writes atomically:
  extracted/<id>.json   [{page, text, extract}]
  extracted/<id>.txt    flattened text with [PAGE N] markers

Dispatch follows the manifest `extract` field ("pdf*"/"html") with a
filename-extension fallback, and a %PDF- magic-byte check as the tiebreaker;
the extractor actually used is recorded per page. kyivpost.com mirror rows are
trimmed to the article body best-effort. Rows whose extracted/<id>.json is
newer than the raw file are skipped unless --force. sha256 mismatches and
per-row extraction failures are counted, skipped, and make the exit nonzero.

OCR fallback (scanned files) is a TODO: pymupdf can render pages to images; tie
Tesseract into a later pass when a scanned TNA source is added.

Usage: .venv/bin/python scripts/parse.py [manifest-path] [--force]
"""
import hashlib
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
EXT = os.path.join(ROOT, "extracted")
MANIFEST = os.path.join(ROOT, "sources", "manifest.json")


def load_manifest(path):
    with open(path) as f:
        return json.load(f)


def parse_rows(rows):
    """Yield (row, raw_path) for fetched rows that have a raw file."""
    for row in rows:
        fname = row.get("file")
        # NOTE: status gate matters — rows marked "invalid" carry on-disk bytes
        # (hashed for provenance) that are error/challenge pages, not documents.
        if not fname or row.get("status") != "fetched":
            continue
        yield row, os.path.join(RAW, fname)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_extractor(row, raw_path):
    """Manifest `extract` field first, extension fallback, %PDF- magic decisive."""
    ex = (row.get("extract") or "").lower()
    if ex.startswith("pdf"):
        kind = "pdf"
    elif "html" in ex:
        kind = "html"
    else:
        kind = "pdf" if raw_path.endswith(".pdf") else "html"
    with open(raw_path, "rb") as f:
        head = f.read(1024)  # spec puts %PDF- at byte 0; readers accept it within 1KB
    if b"%PDF-" in head:
        kind = "pdf"
    elif kind == "pdf":
        kind = "html"  # labeled pdf without PDF magic: an error page saved as .pdf
    return kind


def extract_pdf(path):
    import pymupdf  # deprecated `fitz` import; use pymupdf namespace

    doc = pymupdf.open(path)
    pages = []
    for i in range(len(doc)):
        pages.append({"page": i, "text": doc[i].get_text()})
    return pages


_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_BLOCK_RE = re.compile(r"<(p|li|h[1-6]|div|br|blockquote)[^>]*>", re.IGNORECASE)

def extract_html(path, max_chars=900000):
    """Crude HTML → text: drop script/style/comments, blank block-tags to
    paragraph breaks, decode entities.

    Whitespace is normalised per-line, never with norm_ws: newlines must
    survive so segment.py's $-anchored KEY_HEADINGS heading match can fire.
    Entity decoding comes AFTER tag-stripping so decoded &lt;/&gt; cannot
    reintroduce text the tag regex would then eat.
    """
    raw = open(path, encoding="utf-8", errors="replace").read()
    raw = _SCRIPT_RE.sub("\n", raw)
    raw = _COMMENT_RE.sub("\n", raw)
    raw = _BLOCK_RE.sub("\n\n", raw)
    raw = _TAG_RE.sub("", raw)
    raw = html.unescape(raw)
    # Undecoded double-escaped entities (&amp;rsquo;) need a second pass.
    raw = html.unescape(raw)
    raw = raw.replace(" ", " ")
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r" ?\n ?", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return [{"page": 0, "text": raw.strip()[:max_chars]}]


def norm_ws(t):
    return re.sub(r"\s+", " ", t).strip()


# The share bar sits BETWEEN the headline marker and the body on the same
# extracted line, so start/end trimming cannot remove it — delete any run of
# three or more consecutive share-bar tokens (the mirror renders them in
# several orders, so a fixed-order phrase match missed variants).
_SHARE_BAR_RE = re.compile(
    r"(?:(?:Content|Share|Facebook|X|\(Twitter\)|LinkedIn|Bluesky|Email|Copy"
    r"|Copied|Flip|Make\s+us\s+preferred\s+on\s+Google)\s+){3,}", re.I)


def trim_kyivpost(text, title):
    """Best-effort body isolation for kyivpost.com mirror pages (nav/footer chrome)."""
    low = text.lower()
    start = low.find("british defence intelligence update")
    if start < 0 and title:
        start = low.find(title.lower())
    if start > 0:
        text = text[start:]
        low = text.lower()
    ends = [i for i in (low.find("to suggest a correction"),
                        low.find("all materials, including photographs")) if i >= 0]
    if ends and text[:min(ends)].strip():
        text = text[:min(ends)].strip()
    return _SHARE_BAR_RE.sub("", text)


def write_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(data)
    os.replace(tmp, path)


def main():
    argv = sys.argv[1:]
    force = "--force" in argv
    args = [a for a in argv if a != "--force"]
    mpath = args[0] if args else MANIFEST
    os.makedirs(EXT, exist_ok=True)
    manifest = load_manifest(mpath)
    rows = manifest if isinstance(manifest, list) else manifest.get("sources", [])
    done = fresh = mismatched = failed = 0
    for row, raw_path in parse_rows(rows):
        rid = row["id"]
        if not os.path.exists(raw_path):
            print("skip %s (missing raw %s)" % (rid, os.path.basename(raw_path)))
            continue
        out_json = os.path.join(EXT, rid + ".json")
        out_txt = os.path.join(EXT, rid + ".txt")
        if not force and os.path.exists(out_json) \
                and os.path.getmtime(out_json) > os.path.getmtime(raw_path):
            fresh += 1
            continue
        # RATIONALE: a refetched raw silently poisoned committed provenance once
        # already — verify against the manifest sha256 before extracting.
        digest = sha256_file(raw_path)
        if digest != row.get("sha256"):
            print("ERROR %s: raw sha256 %s != manifest %s -- row skipped"
                  % (rid, digest, row.get("sha256")), file=sys.stderr)
            mismatched += 1
            continue
        try:
            kind = pick_extractor(row, raw_path)
            pages = extract_pdf(raw_path) if kind == "pdf" else extract_html(raw_path)
            if "kyivpost.com" in (row.get("url") or ""):
                for p in pages:
                    p["text"] = trim_kyivpost(p["text"], row.get("title") or "")
            for p in pages:
                p["extract"] = kind
            write_atomic(out_json, json.dumps(pages, indent=1))
            write_atomic(out_txt, "".join(
                "\n[PAGE %d]\n%s\n" % (p["page"], p["text"]) for p in pages))
        except Exception as e:
            print("ERROR %s: extract failed: %s" % (rid, e), file=sys.stderr)
            failed += 1
            continue
        n = sum(len(p["text"]) for p in pages)
        print("%-32s %3d pages  %6d chars  [%s] -> extracted/%s"
              % (rid, len(pages), n, kind, rid))
        done += 1
    total = sum(1 for r in rows if r.get("file"))
    print("parsed %d/%d fetched rows (%d fresh-skipped, %d sha256 mismatches, %d failed)"
          % (done, total, fresh, mismatched, failed))
    if mismatched or failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
