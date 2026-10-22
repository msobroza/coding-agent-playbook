---
id: docs-citation-file
name: Citation file
description: "Keep CITATION.cff's version, release date, title, authors and license in step with pyproject.toml, and never invent a DOI, ORCID or author."
version: 1
scope: scoped
globs:
  - "CITATION.cff"
applies_if:
  has_file: ["CITATION.cff"]
section: repo-files
priority: 63
tags: [python, docs, citation]
---

# Citation file

## Description

CITATION.cff at the repo root tells people how to cite the software. At each release, `version` and `date-released` (an ISO date) change together with the package version. The title, authors and license agree with pyproject.toml and with the README's citation section. The file stays valid `cff-version: 1.2.0`.

A DOI, an ORCID or an author is never invented: a made-up identifier sends citations nowhere. `preferred-citation` names a paper only when the user supplies one.

## Bad Example

```yaml
cff-version: 1.2.0
title: my-pkg
version: 1.4.0          # pyproject.toml says 2.0.0
date-released: 2025-06-01
doi: 10.1234/made-up.567      # never issued
authors:
  - family-names: Doe
    given-names: Jane
```

## Good Example

```yaml
cff-version: 1.2.0
message: "If you use this software, please cite it as below."
title: my-pkg
version: 2.0.0
date-released: 2026-03-04
license: MIT
repository-code: "https://git.example.com/acme/my-pkg"
authors:
  - family-names: Doe
    given-names: Jane
```

No `doi` key until one is issued.

## Notes

- Validate with the repo's own validator only if it has one; no tool is added for it.
- Archive and DOI services are account setup the user does, not part of a change.
- A BibTeX block in the README, when present, matches the file.
