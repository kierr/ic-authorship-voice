# Security Policy

## Reporting a vulnerability

If you find a security vulnerability in this repository, please report it
privately via GitHub's security advisory feature:

https://github.com/kierr/ic-authorship-voice/security/advisories/new

Replace `kierr` with the repository owner if the repo is transferred. Do not file security
vulnerabilities as public issues.

## Scope

This repository contains a public-domain training corpus and pipeline scripts.
Security issues in scope include:

- Exposure of private or case-file data in the corpus
- Provenance hash collisions or bypasses that allow data tampering
- Supply-chain issues in fetched source documents

Out of scope: model behaviour prompts, style preferences, or content
disagreements with published source material.
