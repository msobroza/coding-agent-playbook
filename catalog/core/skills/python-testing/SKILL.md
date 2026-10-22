---
id: python-testing
name: python-testing
description: "Guides how tests in this repo's pytest suite are written and reviewed."
playbook:
  use_when: "writing, changing or reviewing tests, fixtures or conftest.py"
  files: "Test files and conftest.py"
  sections:
    - id: mocking
      title: "Mocking"
      impact: CRITICAL
      summary: "Double only what the code does not own, and keep every double faithful to the real interface."
      open_when: "A test stands in for a collaborator with a fake class, a stub, Mock, create_autospec, mock.patch or mocker."
    - id: structure
      title: "Test Structure"
      impact: HIGH
      summary: "Lay out, name and shape each test so a failure points at one behavior and an assertion that could fail."
      open_when: "A test function is added or reworked: its name, asserts, pytest.raises, if/for/try in the body, or async or skip marks."
    - id: isolation
      title: "Test Isolation"
      impact: HIGH
      summary: "Keep every test independent of run order, the environment, the clock and randomness."
      open_when: "A test touches os.environ, the clock, random numbers, the network or module state, or fails only in some run orders."
    - id: fixtures
      title: "Fixtures"
      impact: HIGH
      summary: "Share setup without hiding it: narrow scope, nearest conftest.py, factories for variations."
      open_when: "A @pytest.fixture or conftest.py is added or changed, or several tests build the same objects in their Arrange step."
    - id: parametrization
      title: "Parametrization"
      impact: MEDIUM
      summary: "Collapse duplicated tests into case tables that run and report each case on its own."
      open_when: "Two tests differ only in inputs and expected values, or a parametrize decorator, ids= or pytest.param is edited."
    - id: coverage
      title: "Coverage"
      impact: MEDIUM
      summary: "Find the inputs and paths the suite still misses: edge-case checklists, branch coverage and property-based tests."
      open_when: "Deciding which cases to add: boundary and error inputs, a coverage report's misses, a regression test, or Hypothesis."
---

# Python testing

Conventions for this repo's tests: layout, naming, parametrized cases, test doubles, fixtures, test data and isolation. Production code changed alongside a test still follows the python-coding skill.

## Picking rules

The rules index in this file lists only the rules that apply to this repo, most important first, each with the one line it requires. Open every rule whose line matches the change and read it in full before writing or changing a test.

- Any new or changed test: conventions.
- Fakes, mocks, patches, environment variables or the clock in a test: test doubles.
- Fixtures, factories or `conftest.py`: fixtures.
