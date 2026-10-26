---
id: docs-readme-essentials
name: README essentials
description: "Keep the README short and true: what it is, install with the real distribution name, a minimal runnable example, links to docs, architecture, contributing and license."
scope: scoped
globs:
  - "README*"
section: repo-files
priority: 60
tags: [python, docs, readme]
---

# README essentials

## Description

The README is the entry point of the repo, and often also the project's page on the package index. It answers, briefly and in this order:

- what the project does and for whom, in one to three sentences;
- how to install it, with the distribution's real name and the Python floor from `requires-python`;
- a minimal example that runs as written, with its expected output (`docs-runnable-examples`);
- where the full documentation lives, and a pointer to docs/architecture.md;
- how to contribute (CONTRIBUTING) and the license;
- how to cite the project, when a CITATION.cff exists.

Every command must work in this repo: console scripts by their names in `[project.scripts]`, extras by their real names. Long material (tutorials, API listings, design discussion) moves to docs/ with a link.

## Bad Example

```markdown
# mypkg

    pip install mypkg

    from mypkg import run_report
    run_report("orders.csv")
```

The distribution is `my-pkg`, so the install fails; `run_report` was renamed to `build_report`; and 300 more lines mix a tutorial with a hand-written API listing.

## Good Example

````markdown
# my-pkg

Builds daily order reports from CSV exports, for finance teams.
Requires Python 3.10 or newer.

## Install

    pip install my-pkg

## Quick start

```python
from my_pkg import build_report

print(build_report("examples/orders.csv").total)
# 1240.50
```

## Learn more

- Documentation: docs/index.md
- How the code is organized: docs/architecture.md
- Contributing: CONTRIBUTING.md
- License: MIT (LICENSE)
````

Installing a published distribution with `pip install` works whatever the repo's own package manager is.

## Notes

- The developer setup in the README or CONTRIBUTING uses the repo's own commands (uv's only in a uv project); `docs-contributing-guide` covers it.
- When pyproject's `readme` feeds the package index page, relative links and images do not resolve there.
- Existing badges stay, but no badge rows are added: they are decoration that needs URLs.
- Any link is a reserved host (example.com) inside a fenced block.
- The README is an entry point, not every kind of documentation at once.
