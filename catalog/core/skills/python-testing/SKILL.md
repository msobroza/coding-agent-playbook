---
id: python-testing
name: python-testing
description: "Test conventions for this repo's pytest suite."
playbook:
  use_when: "writing, changing or reviewing tests, fixtures or conftest.py"
  files: "Test files and conftest.py"
---

# Python testing

Conventions for this repo's tests: layout, naming, parametrized cases, test doubles, fixtures, test data and isolation. Production code changed alongside a test still follows the python-coding skill.

## Picking references

The references index in this file lists only the references that apply to this repo, most important first, each with the one line it requires. Open every reference whose line matches the change and read it in full before writing or changing a test.

- Any new or changed test: conventions.
- Fakes, mocks, patches, environment variables or the clock in a test: test doubles.
- Fixtures, factories or `conftest.py`: fixtures.
