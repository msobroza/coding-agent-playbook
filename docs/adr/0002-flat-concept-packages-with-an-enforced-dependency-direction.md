---
status: accepted
---

# Flat concept packages with an enforced dependency direction

`src/coding_agent_playbook` grew 48 root-level modules and packages that split one concept across several places (sync logic inside `commands/`, the hook concept across `hook_policy/`, `hook_registrations/` and `hook_runtime/`, `evals/` next to `evaluators/`). We reorganise it into about 22 flat top-level packages, each named after a glossary concept (`catalog/`, `detector/`, `config/`, `skills/`, `rendering/`, `sync/`, `validation/`, `adapters/`, `grading/` and so on). A package imports only from packages below it in one declared order, and an underscore module is imported only from inside its own package. import-linter enforces both rules from a pytest test, so the CI gate keeps its four commands. Package `__init__.py` files hold only a docstring: a package's interface is its non-underscore modules, which keeps every import line searchable and costs nothing at import time, which the hook hot path needs.

## Considered Options

- **Group packages under three stacks** (`engine/`, `hook_runtime/`, `grading/`). This adds a path segment to every import and hides nothing, because the declared dependency order already says how packages relate.
- **Re-export the public names from each package `__init__`.** It is convenient for callers, but it costs import time on the hook hot path and gives two spellings for every name.
- **Keep re-export shims at the old module paths for a release.** No consumer had installed the engine yet, so only the external contract stays fixed: the `hook_runtime` module path that committed launchers run, `cli:main`, `hook_runtime.cli:main`, `adapters.base` for out-of-tree adapters, and the entry-point group names.

## Consequences

- Files move in move-only PRs, separate from behaviour changes. Packages the in-flight ticket chain does not touch move first; the rest move after it merges.
- Tests for a package live in `tests/<package>/`; `tests/cli/` and `tests/integration/` stay as they are.
- Each move PR rewrites the module paths in SPEC.md, README.md and MIGRATION.md with the same script. Line numbers in the docs stay best-effort.
- A few packages and root modules are named after no glossary term, on purpose, and the glossary does not gain one for them: `commands/` holds the CLI subcommands, an implementation layer rather than a domain concept; `security/` holds the stdlib-only secret, PII and path judges plus the trust store; `precommit.py` holds the pre-commit template and its text merge; `exit_two.py` holds `ExitTwoError`, the one error type the CLI maps to exit code 2; `toml_writer.py` holds the TOML writer. The rest are named after what they run or their place in the external contract: `cli/` (the `playbook` entry point), `metrics_gate/` (`playbook metrics`) and `hook_runtime/`, whose path committed launchers run.
