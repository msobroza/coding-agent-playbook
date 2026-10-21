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
