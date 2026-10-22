# Which check failed, and which rule fixes it

Find the code or the message the failing check printed, open the rule its row names, fix the cause, then rerun the repo's own command: the one in the CI workflow, the Makefile or the pre-commit config, with its arguments. Never edit a setting or add a blanket suppression to clear a finding (python-static-checks).

A code appears only where the repo selects it; a row here is no reason to enable one. Rule ids from this skill are given bare; a rule of another skill carries its skill name, and each fix line stands on its own when that rule is not in this repo's index.

## The run itself

| What you see | Fix | Rule |
| --- | --- | --- |
| The check passes locally and fails in CI | Rerun with CI's arguments, paths and tool version; fix what that run reports | python-static-checks |
| A pre-commit hook fails or rewrites files | Read and stage the rewrite, fix the rest, commit again; never `--no-verify` or `SKIP=` | python-static-checks |
| The gate-weakening guard flags a suppression without a reason, or a loosened setting | Fix the finding, or name the code and the reason on the suppression; restore the setting | python-static-checks |
| The gate-weakening guard flags a skipped, xfailed or deleted test | Make the test pass, or report why it cannot yet | python-testing's pytest |
| The Stop gate reports a red check | Fix it, or say plainly that it still fails | python-static-checks |
| A tool is not installed | Ask the user before installing anything; the toolchain hint names the project's command | none |

## Ruff findings, by code family

| Codes | Usually means | Fix | Rule |
| --- | --- | --- | --- |
| F401, F841, ERA001 | Dead imports, variables or code | Delete what the change created or touched; an `__init__.py` re-export follows the repo's per-file-ignores | ruff-lint |
| RUF100, PGH004 | A stale or blanket `# noqa` | Delete the stale one; a needed one names its code and reason | python-static-checks |
| I001 | Unsorted imports | Run the formatter's import sorting on the changed files; grouping is python-coding's python-imports | ruff-format |
| E501 | A line too long | Restructure the line; never raise `line-length` | ruff-format |
| The UP family | Syntax older than the target version | Apply the fix; `target-version`, or `requires-python` when it is unset, decides which fixes appear and is never changed to silence one; python-version-idioms.md in the python-coding skill gives each version's form | ruff-lint |
| UP006, UP007, UP035, UP040, UP045 | Old typing forms | Use the form the target version allows | python-coding's python-typing |
| The ANN family, B006, PGH003 | Missing annotations, a mutable default, a bare `# type: ignore` | Annotate, default to `None`, name the ignored code | python-coding's python-typing |
| The D1 family | A missing docstring | Write the docstring the repo's convention asks for | python-coding's python-docstrings |
| E722, BLE001, S110, S112, B904, TRY400, TRY401, S101 | A broad or silent handler, a lost cause, an assert used as a check | Catch the specific error, chain with `from`, log with the traceback, raise instead of asserting | python-coding's python-error-handling |
| S608 | SQL built from strings | Bind parameters | python-coding's python-parameterized-queries |
| The PD and NPY families; S301, S403 or S506 on loaded data | pandas, NumPy or unsafe-loading findings | Fix the cause `ruff rule <CODE>` explains; never load untrusted data unsafely. In NumPy, pandas or polars repos, review-signals.md in the ml-data skill maps each code to its rule | the ml-data skill |
| The PT family | pytest style findings | Fix the cause `ruff rule <CODE>` explains. In pytest repos, reviewing-tests.md in the python-testing skill maps each PT code to its rule | the python-testing skill |
| C901, PLR0911, PLR0912, PLR0913, PLR0915 | A function too complex or with too many arguments | Restructure with python-coding's python-early-return and python-function-signatures; or split the class with the design-patterns skill's design-split-god-class (its lint-guardrails.md maps smells to codes); never raise the limit | ruff-lint |
| A fix ruff holds back as unsafe | The fix can change behavior | Read each one before applying it | ruff-lint |
| A code the repo does not select | Not a finding here | Leave it; propose an `extend-select` change only when asked | ruff-lint |

## Formatter diffs

| What you see | Fix | Rule |
| --- | --- | --- |
| "Would reformat" for a file you changed | `ruff format` on that file | ruff-format |
| "Would reformat" for files outside the change | Report them; do not reformat them in this change | ruff-format |
| A format run keeps undoing hand alignment, or a construct formats badly | Restructure the code instead of fighting the formatter | ruff-format |
| Ruff warns that a lint rule conflicts with the formatter, or the lint and format line lengths differ | Report the mismatch; never edit the settings | ruff-format |
| Black is the configured formatter (`black --check` fails) | The same rows, with Black's command | ruff-format |

## mypy and pyright errors, by error code

| Code | Usually means | Fix | Rule |
| --- | --- | --- | --- |
| import-untyped, import-not-found | A library without stubs or `py.typed` | Propose a stub package for the dev dependencies, or a per-module override for that import alone; never repo-wide | mypy-type-checking |
| no-untyped-def, no-untyped-call | A function without annotations | Annotate it | python-coding's python-typing |
| arg-type, assignment, return-value | A value of the wrong type | Fix the annotation or the value; narrow before silencing | mypy-type-checking; python-coding's python-typing |
| union-attr, pyright's reportOptionalMemberAccess | An attribute read on a value that may be `None` | Narrow with `isinstance` or an early return | mypy-type-checking |
| no-any-return, `Any` leaking from an untyped library | A precise type lost | Give the precise type, or `cast()` with a comment saying what you know | mypy-type-checking |
| attr-defined | A real bug, or an incomplete stub | Fix the bug; for a stub gap, a local stub or a scoped ignore with its code | mypy-type-checking |
| unused-ignore | A stale `# type: ignore` | Delete it | python-static-checks |
| ignore-without-code | A bare `# type: ignore` | Name the code and why | python-coding's python-typing |
| A "Revealed type is" note | A leftover `reveal_type` | Remove it before committing | mypy-type-checking |
| A new module fails the strict level a legacy override relaxes | New code held to the old level | Meet the strict level; never join the override | mypy-type-checking |
| pyright's own rule names, `# pyright: ignore[rule]` | The same findings in pyright's words | The same rows apply | mypy-type-checking |

## pytest stops on its configuration

For repos that run pytest.

| What you see | Fix | Rule |
| --- | --- | --- |
| A marker "not found in `markers` configuration option", or PytestUnknownMarkWarning | Fix the typo, or register the marker with a meaning | pytest-configuration |
| A warning raised as an error by `filterwarnings` | Our code: fix the cause; a third-party package: a narrow, commented filter | pytest-configuration |
| PytestConfigWarning about an unknown option | Keep the settings in one home, or report the missing plugin | pytest-configuration |
| "Required test coverage of N% not reached", or the coverage gate blocks | Never lower `fail_under` or turn off branch coverage; add the missing tests (python-testing's pytest-branch-coverage) | pytest-configuration |
| "no tests ran", or a new test missing from the count | Check `pytest --collect-only -q`, `testpaths` and the file patterns | pytest-configuration |
| Passes alone or with `--lf`, fails in the full run | Find the shared state or ordering the test depends on | python-testing's pytest-deterministic-tests |

## When no row fits

`ruff rule <CODE>` prints a ruff code's explanation; mypy prints its error code in brackets at the end of the message. Fix the cause, and propose any settings change to the user as a separate step that names the finding (python-static-checks).
