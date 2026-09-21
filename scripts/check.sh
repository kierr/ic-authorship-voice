#!/bin/sh
# scripts/check.sh — run every cheap gate in one command.
# AGENTS.md "Gates" section in executable form; nonzero exit on any failure.
set -e
cd "$(dirname "$0")/.."
PY="${IC_PYTHON:-.venv/bin/python}"
echo "== manifest projection check =="
"$PY" scripts/manifest.py --check
echo "== raw provenance verify =="
"$PY" scripts/fetch.py --verify
echo "== corpus validation (0 violations required) =="
"$PY" scripts/validate_corpus.py
echo "== lint selftest + strict corpus lint =="
"$PY" -c "import sys; sys.path.insert(0,'eval'); sys.path.insert(0,'scripts'); import lints; lints.selftest(); print('selftest PASS')"
echo "ALL GATES GREEN"
