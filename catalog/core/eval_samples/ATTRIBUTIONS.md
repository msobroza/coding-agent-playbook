# Attributions

The `find-injected-vuln-*` evaluation fixtures in this directory are **derived
works** built from the **CrossCommitVuln-Bench** dataset.

- **Source:** CrossCommitVuln-Bench — a curated corpus of real CVEs in real
  Python projects.
- **Author / copyright:** Copyright 2026 Arunabh Majumdar.
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0) —
  <https://creativecommons.org/licenses/by/4.0/>
- **Paper:** arXiv:2604.21917
- **DOI:** 10.5281/zenodo.19338596

## Indication of changes (required by CC BY 4.0 §3(a))

The dataset's per-CVE annotations were **transformed into question-answer
scenario fixtures**. Each fixture's source files are **original code that
paraphrases only the source→sink pattern** described in the CVE's CC BY
annotation and reproduction notes. **The upstream project source code was not
consulted** when authoring any fixture, so no upstream (potentially
GPL/AGPL-licensed) code is reproduced or adapted here. The neutral,
needle-hiding task prompt was authored independently.

## Per-fixture provenance

Each fixture's `sample.toml` `description` cites the specific CVE it derives from.
The fixtures and their originating CVEs:

| Fixture | CVE | CWE |
|---|---|---|
| find-injected-vuln-modoboa-cmdi | CVE-2026-27602 | CWE-78 |
| find-injected-vuln-ormar-sqli | CVE-2026-26198 | CWE-89 |
| find-injected-vuln-changedetection-ssrf | CVE-2026-27696 | CWE-918 |
| find-injected-vuln-langroid-codeinj | CVE-2025-46724 | CWE-94 |
| find-injected-vuln-pytorch-deserial | CVE-2025-32434 | CWE-502 |
| find-injected-vuln-changedetection-pathtraversal | CVE-2026-29065 | CWE-22 |
| find-injected-vuln-authlib-sigbypass | CVE-2026-27962 | CWE-347 |
| find-injected-vuln-graphiti-queryinj | CVE-2026-32247 | CWE-943 |
| find-injected-vuln-pydash-massassign | CVE-2025-58367 | CWE-915 |
| find-injected-vuln-aiplatform-xss | CVE-2026-2472 | CWE-79 |

# CRBugBench-derived review samples

The `review-crbug-*` evaluation fixtures each paraphrase one bug from the
**CRBugBench** code-review benchmark (paper: arXiv:2610.13668), which pairs a bug
from an open-source repository's history with the pull request that introduced
it.

## What was used and what was not

- **From CRBugBench:** only the choice of pull request and the fact of its bug: a
  defect a human reviewer flagged on the pull request, or one a user reported
  and a later pull request fixed. The CRBugBench repository carries no license
  file, so none of its text (task instructions, ground-truth descriptions,
  judge prompts) is reproduced; each request, rubric and reference answer here
  is written fresh.
- **From the upstream projects:** each fixture is original, minimal code written
  to reproduce the bug pattern. It keeps the upstream function names and the
  shape of the reviewed change, so the few changed lines follow the upstream pull
  request closely; no upstream source file is copied. Every upstream project
  listed below is under a permissive license.

## Per-fixture provenance

| Fixture | Upstream project (license) | Pull request | CRBugBench track |
|---|---|---|---|
| review-crbug-netrc-env-path | requests (Apache-2.0) | 5643 | caught in review |
| review-crbug-basic-auth-not | fastapi (MIT) | 807 | caught in review |
| review-crbug-xtrim-maxlen-minid | redis-py (MIT) | 1508 | caught in review |
| review-crbug-replace-same-object | manim (MIT) | 4242 | caught in review |
| review-crbug-form-method-none | scrapy (BSD-3-Clause) | 3794 | caught in review |
| review-crbug-ftp-active-string | scrapy (BSD-3-Clause) | 3829 | caught in review |
| review-crbug-log-textio | selenium (Apache-2.0) | 12637, fixed by 12871 | fixed later |
| review-crbug-audio-input-args | frigate (MIT) | 8156, fixed by 8924 | fixed later |
