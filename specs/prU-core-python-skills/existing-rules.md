# prU: fate of the existing core rules

Generated from the verified mapping data; do not edit by hand. Decisions: [../prU-core-python-skills.md](../prU-core-python-skills.md).

The two always rules stay in `catalog/core/rules/always/` unchanged. Every scoped rule:

| Old id | Fate | New ids |
| --- | --- | --- |
| `fastapi-app-wiring` | leaves python-tooling for web-application (brief), split | `fastapi-app-wiring`, `fastapi-dependency-overrides`, `fastapi-dependency-providers`, `fastapi-no-blocking-calls`, `sqlalchemy-session-per-request` |
| `fastapi-error-boundaries` | leaves python-tooling for web-application (brief), merge | `fastapi-error-boundaries` |
| `ml-data-transforms` | split | `ml-categorical-labels`, `ml-data-transforms`, `ml-loc-assignment`, `ml-method-chaining`, `ml-named-aggregation` |
| `ml-dtypes-and-typing` | retired-split | `ml-array-typing`, `ml-categorical-labels`, `ml-check-after-load`, `ml-dtypes-at-load`, `ml-frame-validation`, `ml-numpy-dtypes` |
| `ml-reproducibility-and-testing` | retired-split | `ml-numeric-assertions`, `ml-seeded-randomness` |
| `ml-serialization-security` | keep | `ml-serialization-security` |
| `ml-vectorization` | split | `ml-build-once`, `ml-named-aggregation`, `ml-vectorization` |
| `pydantic-boundaries` | leaves python-tooling for python-coding (D24), split (keeps id); moves from python-tooling (D24) | `pydantic-boundaries`, `pydantic-field-constraints`, `pydantic-typed-settings` |
| `pytest` | split | `pytest`, `pytest-arrange-act-assert`, `pytest-assertions`, `pytest-deterministic-tests`, `pytest-no-test-logic`, `pytest-one-behavior`, `pytest-parametrize`, `pytest-parametrize-ids` |
| `pytest-configuration` | merge (id, gate and globs kept, plus .coveragerc; pbp test-pytest merged) | `pytest-configuration` |
| `pytest-fixtures` | split | `pytest-conftest`, `pytest-factory-fixtures`, `pytest-fixtures` |
| `pytest-test-doubles` | split | `pytest-autospec`, `pytest-monkeypatch`, `pytest-test-doubles` |
| `python-async` | split (keeps id and gate) | `python-async`, `python-async-fanout`, `python-async-tasks` |
| `python-classes-and-protocols` | retired (D21); split between python-coding and design-patterns (see handoffs), retired (D21); split by line: 18-21 single responsibility, 14-16 and 23-28 lightest construct, 37-55 composition, 63-66 Liskov, 68-70 interface segregation, 72-89 open/closed, 91-96 abstractions earn their place; lines 30-35 and 57-61 go to python-coding (python-properties, python-protocols; see handoffs) | `design-composition-over-inheritance`, `design-dry-yagni-kiss`, `design-interface-segregation`, `design-lightest-construct`, `design-liskov-substitution`, `design-open-closed`, `design-single-responsibility`, `python-properties`, `python-protocols` |
| `python-context-managers` | split (keeps id) | `python-context-managers`, `python-custom-context-managers` |
| `python-data-shapes` | split (keeps id) | `python-data-shapes`, `python-frozen-dataclasses` |
| `python-dependency-injection` | split, split (keeps id); :24-27 handed to python-architecture | `arch-composition-root`, `python-dependency-injection`, `python-no-global-singletons` |
| `python-docstrings` | merge (keeps id, lint_codes and hook), stays in python-coding under its id (D53); named in plain text here, never repeated | `python-docstrings` |
| `python-error-handling` | split (keeps id, lint_codes and hook) | `python-custom-exceptions`, `python-error-boundaries`, `python-error-handling` |
| `python-idioms` | split (keeps id for the small-idioms remainder) | `python-early-return`, `python-function-signatures`, `python-idioms`, `python-imports` |
| `python-performance-idioms` | retired (D21) | `python-collection-choice`, `python-comprehensions`, `python-generators`, `python-optional-keys`, `python-str-join` |
| `python-pure-core` | merge (keeps id) | `python-pure-core` |
| `python-retries-and-timeouts` | merge (keeps id and gate) | `python-retries-and-timeouts` |
| `python-static-checks` | split | `mypy-type-checking`, `python-static-checks`, `ruff-format`, `ruff-lint` |
| `python-typing` | split (keeps id, template, lint_codes and hook) | `python-abstract-inputs`, `python-type-aliases`, `python-typing` |
| `python-uv-workflow` | split | `python-pyproject-dependencies`, `python-uv-workflow` |
