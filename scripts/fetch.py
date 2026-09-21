#!/usr/bin/env python3
"""scripts/fetch.py — download raw sources from sources/manifest.json.

Polite fetching (<=1 req/2s: 2.0s pace before every network call, retry with
backoff). Default mode calls fetch() unconditionally for
every non-candidate row with file+url: present-and-hash-ok files skip without
touching the network, absent or stale files download url -> raw/<file> streamed
in chunks (incremental sha256, 200MB cap, min 2048-byte body, redirects
printed). A hash-mismatch keeps the bytes at raw/<file>.mismatch and prints
got-vs-want digests. 4xx responses (except 429) are never retried; 429/5xx and
network errors retry with backoff, honouring Retry-After.

Usage: .venv/bin/python scripts/fetch.py [--all | --verify | --promote <id>]
  --all           also fetch candidate rows that have url and file; candidates
                  with a null file are skipped with a printed reason (promote
                  them instead).
  --verify        no downloads: re-hash every row's raw/<file> against the
                  manifest sha256, print per-row mismatches and a summary,
                  exit nonzero on any mismatch or missing file.
  --promote <id>  fetch a candidate row's url to raw/<id><ext>, compute sha256
                  from the downloaded bytes, and rewrite the row in-place in
                  manifest.json as status=fetched.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MJSON = os.path.join(ROOT, "sources", "manifest.json")
RAW = os.path.join(ROOT, "raw")
UA = {"User-Agent": "ic-authorship-voice/0.1 (research; polite; contact: via repo)"}
RETRIES = 3
PACE = 2.0  # seconds before every network call: documented commitment is <=1 req/2s
CAP = 200 * 1024 * 1024
MIN_BODY = 2048


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def fetch(url, dest, want_sha):
    os.makedirs(RAW, exist_ok=True)
    d = os.path.join(RAW, dest)
    if os.path.exists(d) and want_sha and sha256(d) == want_sha:
        return "skip(hash-ok)"
    # NOTE: pace here, after the hash-ok skip, so idempotent re-runs pay no
    # sleep for already-verified files while every network call is preceded
    # by PACE seconds (including --promote, which routes through fetch()).
    time.sleep(PACE)
    tmp = d + ".tmp"
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                if r.status != 200:
                    return "err:status %s" % r.status
                if r.geturl() != url:
                    print("  redirect: %s -> %s" % (url, r.geturl()))
                h = hashlib.sha256()
                size = 0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1 << 16)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > CAP:
                            os.remove(tmp)
                            return "err:body>200MB"
                        h.update(chunk)
                        f.write(chunk)
            if size < MIN_BODY:
                os.remove(tmp)
                return "err:short-body(%dB)" % size
            hd = h.hexdigest()
            if want_sha and hd != want_sha:
                # keep the bytes for diagnosis instead of discarding them
                os.replace(tmp, d + ".mismatch")
                print("  hash-mismatch %s got=%s want=%s (kept %s.mismatch)"
                      % (dest, hd, want_sha, dest))
                return "hash-mismatch"
            os.replace(tmp, d)
            return "ok:%d" % size
        except urllib.error.HTTPError as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            # 4xx is deterministic — retrying re-fails identically; 429/5xx are transient
            if not (e.code == 429 or e.code >= 500) or attempt == RETRIES - 1:
                return "err:HTTP %d" % e.code
            ra = (e.headers.get("Retry-After") or "").strip()
            # PACE floors the retry too: a server sending Retry-After: 0 is
            # still owed the documented 2s between requests.
            time.sleep(max(PACE, min(int(ra), 120)) if ra.isdigit()
                       else 2 * (attempt + 1))
        except Exception as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            if attempt == RETRIES - 1:
                return "err:%s" % e
            time.sleep(2 * (attempt + 1))
    return "err"


def verify(rows):
    ok = bad = 0
    for r in rows:
        f = r.get("file")
        if not f:
            continue
        p = os.path.join(RAW, f)
        if not os.path.exists(p):
            print("MISSING  %s" % f)
            bad += 1
            continue
        got = sha256(p)
        want = r.get("sha256", "")
        if got != want:
            print("MISMATCH %s got=%s want=%s" % (f, got, want))
            bad += 1
        else:
            ok += 1
    print("verify: ok=%d bad=%d (%d rows with file)" % (ok, bad, ok + bad))
    return 1 if bad else 0


def promote(pid):
    rows = json.load(open(MJSON))
    idx = next((i for i, r in enumerate(rows) if r.get("id") == pid), None)
    if idx is None:
        print("promote: no manifest row with id %r" % pid)
        return 1
    row = rows[idx]
    if row.get("status") != "candidate":
        # Only candidates are promotable: an 'invalid' row must never be
        # silently resurrected to fetched (its bytes are known-bad).
        print("promote: %s is %s, not candidate — refusing" % (pid, row.get("status")))
        return 1
    # url_text is the document itself when url is a listing/landing page
    # (isc-china-2023's url is the ISC reports index; url_text is the report).
    url = row.get("url_text") or row.get("url")
    if not url:
        print("promote: %s has no url" % pid)
        return 1
    # NOTE: extension-less candidate urls are article/landing pages -> .html
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or ".html"
    dest = pid + ext
    out = fetch(url, dest, "")
    if not out.startswith("ok"):
        print("promote: fetch failed: %s" % out)
        return 1
    # RATIONALE: sha256 is computed from the downloaded bytes on disk, never
    # hand-typed — hand-edited hashes are a known error class in this repo.
    digest = sha256(os.path.join(RAW, dest))
    new = {"id": row["id"], "file": dest}  # fetched-row key order: id, file, ..., sha256, status
    for k, v in row.items():
        if k not in ("id", "file", "sha256", "status"):
            new[k] = v
    new["sha256"] = digest
    new["status"] = "fetched"
    rows[idx] = new
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        # explicit raise, not assert: assert strips under python -O and this
        # gate has fired for real in this repo's history.
        raise SystemExit("promote: duplicate ids in manifest — refusing to write")
    # Atomic registry write: a truncating open(MJSON, "w") that crashes
    # mid-dump leaves a 0-byte or half-written manifest (verified failure).
    tmp = MJSON + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(rows, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, MJSON)
    print("promote: %s -> %s sha256=%s" % (pid, dest, digest))
    return 0


def main():
    args = sys.argv[1:]
    if "--verify" in args:
        sys.exit(verify(json.load(open(MJSON))))
    if "--promote" in args:
        i = args.index("--promote")
        if i + 1 >= len(args):
            print("usage: fetch.py --promote <id>")
            sys.exit(2)
        sys.exit(promote(args[i + 1]))
    all_mode = "--all" in args
    rows = json.load(open(MJSON))
    ok = skip_hashok = skip_nolink = mismatch = 0
    err = []
    for r in rows:
        if r.get("status") == "candidate" and not all_mode:
            continue
        f = r.get("file")
        url = r.get("url_text") or r.get("url")
        if not f:
            if all_mode and url:
                print("  skip %s: candidate file is null — use --promote %s"
                      % (r.get("id"), r.get("id")))
                skip_nolink += 1
            continue
        if not url:
            # file-bearing row with no url (e.g. status=invalid orphans) —
            # counted separately: it was never hash-checked, unlike skip_hashok.
            skip_nolink += 1
            continue
        out = fetch(url, f, r.get("sha256", ""))
        if out.startswith("ok"):
            ok += 1
        elif out.startswith("skip"):
            skip_hashok += 1
        elif out.startswith("hash"):
            mismatch += 1
        else:
            err.append((f, out))
    print("fetch: ok=%d skip_hashok=%d skip_nolink=%d hash_mismatch=%d errs=%d"
          % (ok, skip_hashok, skip_nolink, mismatch, len(err)))
    for f, e in err[:10]:
        print("  ERR", f, e)
    # Errors and hash mismatches fail the run: run_all gates stages on the
    # exit code, and a silent exit-0 once let a poisoned fetch read as success.
    sys.exit(1 if (err or mismatch) else 0)


if __name__ == "__main__":
    main()
