---
id: docs-check-in-ci
name: Docs check
description: "Run `playbook docs-check` after editing docs and fix every finding; it runs at commit time and in CI with only the docs tools the repo configures."
version: 1
scope: scoped
globs:
  - "docs/**"
  - "README*"
  - "*.rst"
section: docs-build
priority: 67
tags: [python, docs, ci]
---

# Check the docs like code

## Description

Documentation gets the quality bar of code: it is checked on every commit and every push, and a broken link is a bug. One command does it, `playbook docs-check`, at two points:

- **Before a commit**: the local pre-commit hook, where the repo's pre-commit configuration has it, runs when the staged files include Markdown, reST, `docs/`, `mkdocs.yml` or `docs/conf.py`.
- **In CI**: the same command, on the files the branch changed.

It always checks that relative links resolve and that the Python code blocks of the changed Markdown parse. It runs only the docs tools the repo already configures: the strict MkDocs build where `mkdocs.yml` exists, the Sphinx build with warnings as errors where `docs/conf.py` exists, doctests where the pytest configuration already collects them, and markdownlint or doc8 where their config exists and the tool is installed.

After editing docs, run it and fix every finding before finishing. A tool it reports as missing was skipped (the check fails open): pass its install hint to the user and install only with their agreement. Where the repo has a CI workflow and committed docs but no step that runs the docs check or the docs build, propose one that runs the same command, never a deploy or publish step.

## Bad Example

A renamed page leaves a broken link and an unparsable block, and both are pushed past the hook:

````markdown
See [the install guide](docs/instal.md).

```python
client = OrderClient(timeout=5.0
```
````

```bash
git commit --no-verify -m "docs: rename install page"
```

A CI job builds the site and publishes it from every branch, so a feature branch replaces the live docs.

## Good Example

The check names the file, the line and the broken target; the fix is one line:

```text
README.md:12: relative link 'docs/instal.md' does not resolve
```

```markdown
See [the install guide](docs/install.md).
```

The CI job runs the same command next to the existing test step and publishes nothing:

```yaml
- name: Tests
  run: pytest
- name: Docs check
  # Flags from `playbook docs-check --help`: --base picks the branch to diff against.
  run: playbook docs-check --base origin/main
```

## Notes

- A failing hook is fixed, never bypassed: python-tooling's static-checks rule (python-static-checks) says the same for every check.
- Switching the check off is the user's guardrail setting (playbook-guardrails), not a fix.
- The check parses code blocks but does not run them; running examples is `docs-runnable-examples`.
- Where the repo builds docs with Sphinx or MkDocs, that tool's build rule in this skill says how to run the build as CI does.
- Build output (`_build/`, `site/`) is never committed.
- A docs lint hook the repo already runs is a finding to fix; no hook, linter or link checker is added unasked.
- A whole-site external link check is the repo's own job where it has one.
