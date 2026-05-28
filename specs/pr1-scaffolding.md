# PR 1 — Project scaffolding + adapter ABC + source ABCs

| Field | Value |
| --- | --- |
| Track | 1 |
| Estimated LoC | ~400 (Python + config) |
| Prerequisites | None (lands first; targets `main`) |
| Spec refs | SPEC.md §4.1, §4.2, §5.1, §6.6, §10.1, §10.5, §16, §17, §20 |

---

## 1. Goal & scope

PR 1 lands the engine's project skeleton, packaging, dev tooling, CI, and the three public abstract base classes (`Adapter`, `ArtifactSource`, `StateSource`) that PRs 2–13 will extend. It is *interfaces and tooling only*: no detector, no renderer, no concrete adapter implementations, no overlay merge logic, no real `cap` subcommands beyond `cap --version`. After PR 1 merges, a contributor can `uv sync --dev`, `pre-commit run --all-files`, and `pytest` against a green tree, install the package and run `cap --version`, and import `coding_agent_playbook.adapters.base.Adapter` plus `coding_agent_playbook.sources.base.{ArtifactSource, StateSource}`. The ABC signatures match SPEC §10.1 and §20.2 verbatim so PRs 6–9 (adapters) and PR 5 (filesystem source) can subclass them without churn. Entry-point tables are declared but empty; PRs 2–13 populate them.

---

## 2. In-scope file inventory

All paths are relative to repo root. LoC counts are approximate (≤ targets in SPEC table at line 2077: ~400 total).

| File | Purpose | LoC |
| --- | --- | --- |
| `pyproject.toml` | Build backend, deps, scripts, entry-point tables, tool configs | ~110 |
| `.pre-commit-hooks.yaml` | Empty placeholder (top-level file referenced by consumers; PR 12 populates) | ~3 (comment-only stub) |
| `.pre-commit-config.yaml` | Engine's own dev-loop hooks (ruff, mypy, hygiene) | ~40 |
| `.github/workflows/ci.yml` | GitHub Actions: uv sync, pre-commit, pytest, smoke test | ~45 |
| `src/coding_agent_playbook/__init__.py` | Package marker; exposes `__version__` from `importlib.metadata` | ~10 |
| `src/coding_agent_playbook/py.typed` | PEP 561 marker (empty file) | 0 |
| `src/coding_agent_playbook/cli.py` | `main()` entry; `cap --version` stub; deferred-impl message for everything else | ~35 |
| `src/coding_agent_playbook/_typing.py` | Forward-ref placeholders for `Rule`, `Prompt`, `Skill`, `EvalTask`, `Config`, `Lockfile` (replaced in PR 2 / PR 3 / PR 4) | ~30 |
| `src/coding_agent_playbook/adapters/__init__.py` | Empty package marker | 0 |
| `src/coding_agent_playbook/adapters/base.py` | `Adapter` ABC verbatim from SPEC §10.1 | ~60 |
| `src/coding_agent_playbook/sources/__init__.py` | Empty package marker | 0 |
| `src/coding_agent_playbook/sources/base.py` | `ArtifactSource` + `StateSource` ABCs verbatim from SPEC §20.2 | ~45 |
| `tests/__init__.py` | Empty | 0 |
| `tests/unit/__init__.py` | Empty | 0 |
| `tests/unit/test_cli.py` | `cap --version` exit-code + output assertion | ~20 |
| `tests/unit/test_adapter_base.py` | `Adapter` ABC cannot instantiate; concrete subclass can | ~30 |
| `tests/unit/test_sources_base.py` | `ArtifactSource` + `StateSource` ABCs cannot instantiate; subclasses can | ~30 |
| `tests/unit/test_entry_points.py` | Entry-point tables load without crashing; each table returns an iterable (possibly empty) | ~25 |
| `tests/conftest.py` | Empty; placeholder for shared fixtures in future PRs | 0 |
| `README.md` | Append a one-paragraph "status: PR 1 scaffolding" pointer; existing content kept | +5 |
| `.gitignore` | Already exists; no changes needed in PR 1 | — |

Total: ~490 lines including config and tests, ~360 lines if measuring only Python source. Within the ~400 LoC envelope.

---

## 3. Out of scope

| Item | Track / PR | SPEC ref |
| --- | --- | --- |
| `Rule` / `Prompt` / `Skill` real dataclasses with `from_markdown` / `to_markdown` | Track 1b / PR 2 | §6.6 |
| Detector subsystem and `Facts` TypedDict | Track 2a / PR 3 | §8 |
| Renderer subsystem and Jinja env | Track 2b / PR 4 | §9 |
| `FileSystemArtifactSource` + `FileSystemStateSource` concrete impls | Track 2c / PR 5 | §20.3 |
| Continue / Claude Code / OpenCode / AGENTS.md adapter implementations | Tracks 3 / 4a / 4b / 4c — PRs 6–9 | §10.2 / §10.3 / §10.4 / §10.6 |
| `cap init`, `cap sync`, `cap check`, `cap validate`, `cap render` CLI subcommands | Track 5 / PR 10 | §12 |
| `EvalTask` dataclass + loader + validator + `cap eval --list/--show` | Track 5b / PR 11 | §6.5, §15.2 |
| Concrete pre-commit hook definitions in `.pre-commit-hooks.yaml` (the consumer-facing hooks) | Track 6 / PR 12 | §13.1 |
| `resources/` tree (rules, prompts, skills, eval_tasks, precommit template) | Track 7 / PR 13 | §5.1 |
| `docs/` markdown content | Track 14 | §5.1 (docs folder) |
| Adapter `cleanup_stale()` default-implementation helper logic (referenced by SPEC §10.1 as `_default_cleanup`); body is `raise NotImplementedError("PR 6+")` in PR 1 | PR 6 onward | §10.1 |

PR 1 deliberately ships no overlay logic, no `Config`, no `Lockfile`, no `OVERLAY` discovery, no `cap` subcommands beyond `--version`.

---

## 4. Module specifications

### 4.1 Type-import strategy for ABCs

The ABCs in `adapters/base.py` and `sources/base.py` reference `Rule`, `Prompt`, `Skill`, `Config`, `Lockfile`, and `EvalTask` in their method signatures. None of those types exist until PR 2 (canonical types), PR 3 (detector — not strictly needed but related), PR 4 (renderer), or PR 5 (where `Config` and `Lockfile` settle). PR 1 must therefore make a choice:

**Decision: ship a thin `_typing.py` module that exports placeholder symbols, imported under `TYPE_CHECKING` only.**

Rationale:
- `from __future__ import annotations` is mandatory in every PR 1 source file. With future-annotations on, all annotations are strings, so the symbols only need to exist at type-check time, not at runtime.
- A `TYPE_CHECKING` block imports the real classes once they land in PR 2 / PR 5 (real `Rule` in `coding_agent_playbook.types`, real `Config` in `coding_agent_playbook.config`, etc.) with **zero code change in `_typing.py`** — PR 2 simply replaces `_typing.py`'s placeholder exports with re-exports from the real modules, and PR 5 does the same for `Config` / `Lockfile`. The ABC files themselves never need to change again.
- Using `typing.Protocol` placeholders would be valid but creates two competing definitions of `Rule` (the Protocol in PR 1, the dataclass in PR 2). The `TYPE_CHECKING` route keeps a single source of truth: in PR 1 the placeholders are inert string literals; in PR 2 onward they are the real dataclasses.
- Pydantic-style runtime checks are not in scope for v1.

The file `_typing.py` is private (leading underscore) and not part of the public API. PR 2 may delete it once `types.py` exists and the ABCs import from `coding_agent_playbook.types` directly — but PR 1 ships it so the ABC files can be authored exactly as in §10.1 and §20.2 without touching SPEC's verbatim signatures.

**`src/coding_agent_playbook/_typing.py` contents:**

```python
"""Private forward-reference shims used by ABCs declared before their concrete
types land. Replaced in PR 2 (Rule/Prompt/Skill), PR 5 (Config/Lockfile), and
PR 11 (EvalTask) by re-exports from the real modules.

DO NOT import this module from non-ABC code. It is private to the engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # These names are referenced in ABC signatures. They are intentionally
    # absent at runtime in PR 1; ``from __future__ import annotations`` keeps
    # all annotations as strings, so runtime resolution never happens.
    Rule = "Rule"  # noqa: F841 (placeholder for PR 2)
    Prompt = "Prompt"  # noqa: F841
    Skill = "Skill"  # noqa: F841
    Config = "Config"  # noqa: F841
    Lockfile = "Lockfile"  # noqa: F841
    EvalTask = "EvalTask"  # noqa: F841

__all__ = ["Rule", "Prompt", "Skill", "Config", "Lockfile", "EvalTask"]
```

**Note for reviewers:** since annotations are strings under `from __future__ import annotations`, the ABC modules can simply do:

```python
from __future__ import annotations
from coding_agent_playbook._typing import Rule, Prompt, Skill
```

inside a `TYPE_CHECKING` block. The runtime imports never fail because they never run.

### 4.2 `src/coding_agent_playbook/__init__.py`

Status: **functional** (minimal).

```python
"""coding-agent-playbook engine — see SPEC.md for design."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("coding-agent-playbook")
except PackageNotFoundError:  # pragma: no cover — only when running from source without install
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
```

### 4.3 `src/coding_agent_playbook/cli.py`

Status: **stub** — only `--version` is wired. All other subcommands print a deferred-implementation message and exit 0 (mirroring the `cap eval` stub pattern in §12.8).

```python
"""``cap`` / ``coding-agent-playbook`` entry point.

PR 1 ships only ``--version``. Subcommands (``init``, ``sync``, ``check``,
``validate``, ``render``, ``eval``) print a deferred-implementation message and
exit 0. They are wired up by later PRs (10, 11).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from coding_agent_playbook import __version__

_DEFERRED_MSG = (
    "{name!r} is not implemented yet. PR 1 ships the scaffolding only. See "
    "SPEC.md Section 12 for the planned CLI surface."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cap",
        description="coding-agent-playbook — multi-harness playbook engine.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")
    for name in ("init", "sync", "check", "validate", "render", "eval"):
        sub.add_parser(name, help=f"(deferred — see SPEC §12) {name}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    print(_DEFERRED_MSG.format(name=args.command), file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

### 4.4 `src/coding_agent_playbook/adapters/base.py`

Status: **functional ABC** — signatures verbatim from SPEC §10.1.

```python
"""Adapter ABC. See SPEC.md §10.1.

Concrete adapters (Continue, Claude Code, OpenCode, AGENTS.md) land in
PRs 6–9. Third-party adapters register via the
``coding_agent_playbook.adapters`` entry point declared in pyproject.toml.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook._typing import Prompt, Rule, Skill


class Adapter(ABC):
    """Translate canonical artifacts into a harness's native format."""

    name: str  # e.g. "continue"

    @abstractmethod
    def write_rule(self, rule: "Rule", repo_root: Path) -> list[Path]:
        """Write a rendered rule to the harness-specific location(s).

        Return the paths actually written. Adapters that route rules
        through another adapter (e.g. OpenCode -> AGENTS.md) return [].
        """

    @abstractmethod
    def write_prompt(self, prompt: "Prompt", repo_root: Path) -> list[Path]:
        """Write a rendered prompt."""

    def write_skill(self, skill: "Skill", repo_root: Path) -> list[Path]:
        """Default: degrade to prompt. Subclasses override if native skill
        support (or if a sibling adapter already covers the harness — e.g.
        OpenCode reads .claude/skills/ natively, so its adapter overrides
        this to return [])."""
        prompt = skill.to_prompt()  # type: ignore[attr-defined]  # PR 2 adds Skill.to_prompt
        return self.write_prompt(prompt, repo_root)

    def finalize(self, repo_root: Path) -> list[Path]:
        """Optional lifecycle hook called after all write_* calls for this
        adapter. Used by adapters that buffer artifacts and emit a composite
        file at the end (e.g. Claude Code concatenates rules into a single
        CLAUDE.md). Default: no-op.
        """
        return []

    def cleanup_stale(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Delete generated files no longer corresponding to a current
        artifact. Default: scan the adapter's known output directories and
        remove files under sentinel headers that are not in written_paths.
        Subclasses override only if they need custom cleanup semantics.
        """
        return self._default_cleanup(written_paths, repo_root)

    def _default_cleanup(
        self, written_paths: set[Path], repo_root: Path
    ) -> list[Path]:
        # PR 1 ships only the interface. The default scan/remove
        # implementation lands with the first concrete adapter (PR 6).
        raise NotImplementedError(
            "Default cleanup logic lands with PR 6 (Continue adapter). "
            "Override cleanup_stale() in your subclass to opt out."
        )
```

### 4.5 `src/coding_agent_playbook/sources/base.py`

Status: **functional ABC** — signatures verbatim from SPEC §20.2.

```python
"""ArtifactSource + StateSource ABCs. See SPEC.md §20.2.

The v1 filesystem implementations land in PR 5. Third-party sources register
via the ``coding_agent_playbook.artifact_sources`` and
``coding_agent_playbook.state_sources`` entry points declared in
pyproject.toml.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook._typing import (
        Config,
        EvalTask,
        Lockfile,
        Prompt,
        Rule,
        Skill,
    )


class ArtifactSource(ABC):
    """Where rules, prompts, skills, and eval tasks come from."""

    name: str

    @abstractmethod
    def list_rules(self) -> list["Rule"]: ...

    @abstractmethod
    def list_prompts(self) -> list["Prompt"]: ...

    @abstractmethod
    def list_skills(self) -> list["Skill"]: ...

    @abstractmethod
    def list_eval_tasks(self) -> list["EvalTask"]: ...


class StateSource(ABC):
    """Where config and lockfile are read from and written to."""

    name: str

    @abstractmethod
    def load_config(self) -> "Config": ...

    @abstractmethod
    def save_config(self, config: "Config") -> None: ...

    @abstractmethod
    def load_lockfile(self) -> "Lockfile | None": ...

    @abstractmethod
    def save_lockfile(self, lockfile: "Lockfile") -> None: ...
```

---

## 5. `pyproject.toml`

### 5.1 Build backend

**Decision: `hatchling`.** One-line justification: ships in `uv`'s ecosystem out of the box, supports the `src/` layout via `[tool.hatch.build.targets.wheel] packages = ["src/coding_agent_playbook"]` without plugins, and unlike `setuptools` does not require a `MANIFEST.in` for `py.typed`. PEP 621 metadata is fully covered.

### 5.2 Full file contents

```toml
# pyproject.toml — coding-agent-playbook engine, PR 1 (scaffolding)
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "coding-agent-playbook"
version = "0.1.0a0"
description = "Multi-harness playbook engine — one canonical source, every coding assistant."
readme = "README.md"
license = { text = "Apache-2.0" }
authors = [{ name = "Max Pereira" }]
requires-python = ">=3.12"
keywords = ["llm", "coding-assistant", "continue", "claude-code", "opencode", "agents-md"]
classifiers = [
    "Development Status :: 2 - Pre-Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Code Generators",
    "Typing :: Typed",
]
dependencies = [
    "jinja2>=3.1.4",
    "packaging>=24.0",
]

[project.optional-dependencies]
dev = [
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "pytest>=8.3.0",
    "pytest-cov>=5.0.0",
]

[project.scripts]
cap = "coding_agent_playbook.cli:main"
coding-agent-playbook = "coding_agent_playbook.cli:main"

# --- Extension-point tables. PR 1 declares them empty; future PRs populate. ---

[project.entry-points."coding_agent_playbook.adapters"]
# Populated by PR 6–9: continue, claude_code, opencode, agents_md.

[project.entry-points."coding_agent_playbook.overlays"]
# Populated by overlay packages (e.g. playbook-rules-bnp). Engine ships none.

[project.entry-points."coding_agent_playbook.artifact_sources"]
# Populated by PR 5 (filesystem) and future third-party sources.

[project.entry-points."coding_agent_playbook.state_sources"]
# Populated by PR 5 (filesystem) and future third-party sources.

[project.entry-points."coding_agent_playbook.runners"]
# Populated in v2 — see SPEC §15.4.

[project.entry-points."coding_agent_playbook.judges"]
# Populated in v2 — see SPEC §15.4.

# ----------------------------------------------------------------------------

[tool.hatch.build.targets.wheel]
packages = ["src/coding_agent_playbook"]

[tool.hatch.build.targets.wheel.force-include]
"src/coding_agent_playbook/py.typed" = "coding_agent_playbook/py.typed"

# --- Ruff (lint + format) ---

[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E", "W",   # pycodestyle
    "F",        # pyflakes
    "I",        # isort
    "B",        # bugbear
    "UP",       # pyupgrade
    "SIM",      # simplify
    "TCH",      # flake8-type-checking
    "RUF",      # ruff-specific
]
ignore = [
    "E501",  # line length handled by formatter
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["B011"]  # allow assert False in tests

# --- mypy (strict) ---

[tool.mypy]
python_version = "3.12"
strict = true
warn_unused_ignores = true
warn_redundant_casts = true
warn_return_any = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
namespace_packages = true
explicit_package_bases = true
mypy_path = "src"
files = ["src", "tests"]

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false

# --- pytest ---

[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "--cov=coding_agent_playbook",
    "--cov-report=term-missing",
    "--cov-fail-under=80",
]
xfail_strict = true
filterwarnings = ["error"]
```

Notes:
- `requires-python = ">=3.12"` per SPEC §13.2 (`default_language_version` python3.12) and the spec's stated baseline.
- Runtime deps held to `jinja2` and `packaging` per §20.3. No `tomli` (Python 3.11+ has `tomllib`). No `pyyaml` (PR 2 will choose).
- Dev deps: ruff, mypy, pytest, pytest-cov.
- Entry-point tables declared but empty so `importlib.metadata.entry_points(group=...)` returns an empty iterable without crashing — the discovery smoke test in §7.4 below relies on this.
- `py.typed` is force-included into the wheel.

---

## 6. Tooling & CI

### 6.1 `.pre-commit-config.yaml` (engine's own dev loop)

This is the engine maintainer's local hook config — separate from the **consumer-facing** template described in SPEC §13.2 (which lands with PR 13). PR 12 adds the consumer-facing `.pre-commit-hooks.yaml` entries; PR 1 only sets up the engine's own dev loop.

```yaml
# .pre-commit-config.yaml — engine dev loop (PR 1).
# Consumer-facing hooks are in .pre-commit-hooks.yaml (populated by PR 12).
default_language_version:
  python: python3.12
fail_fast: false
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        additional_dependencies: ["jinja2>=3.1.4", "packaging>=24.0"]
        args: ["--config-file=pyproject.toml"]
        files: ^(src|tests)/
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
        args: [--maxkb=500]
      - id: check-merge-conflict
      - id: detect-private-key
```

`gitleaks` is intentionally not added in PR 1 because it requires a network-installable binary on first run, which conflicts with the air-gapped goal (§17.1). It can land later as part of the consumer template (§13.2), which is downstream of the engine's own CI.

### 6.2 `.github/workflows/ci.yml`

Adapted from SPEC §16.4 to the surface that actually exists in PR 1 (no `cap validate`, no `cap render` — replaced with `cap --version` smoke test).

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "latest"
          enable-cache: true

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - name: Sync dev dependencies
        run: uv sync --extra dev

      - name: Install pre-commit
        run: uv pip install pre-commit

      - name: pre-commit run --all-files
        run: uv run pre-commit run --all-files

      - name: pytest
        run: uv run pytest -q

      - name: cap --version smoke test
        run: uv run cap --version

      - name: coding-agent-playbook --version smoke test
        run: uv run coding-agent-playbook --version
```

The intent is (1) checkout, (2) install uv, (3) install Python, (4) `uv sync --extra dev`, (5) `uv pip install pre-commit` (kept outside `[project.optional-dependencies]` to avoid running it as a runtime dep), (6) `uv run pre-commit run --all-files`, (7) `uv run pytest -q`, (8) `uv run cap --version`, (9) `uv run coding-agent-playbook --version`. Steps 8–9 replace the `cap validate` / `cap render` smoke tests called for in SPEC §16.4 — those land in PR 10.

### 6.3 `.pre-commit-hooks.yaml` (placeholder)

```yaml
# .pre-commit-hooks.yaml — consumer-facing hooks. Populated by PR 12 with
# `cap-sync-check` and `cap-validate` per SPEC §13.1. Present in PR 1 as an
# empty list so consumers cloning early can attach an empty repo without error.
[]
```

A YAML empty list (`[]`) is valid; pre-commit treats it as "this repo defines no hooks", which is the correct semantic for PR 1.

---

## 7. Test plan

All tests live under `tests/unit/` per SPEC §5.1 (existing `tests/unit/` siblings — `test_detector.py`, `test_renderer.py`, etc. — land in later PRs). Coverage target ≥ 80% via `--cov-fail-under=80` in pyproject.

### 7.1 `tests/unit/test_cli.py`

- `test_version_flag_exits_zero_and_prints_version()` — invoke `main(["--version"])` via `pytest`'s `capsys`; assert `SystemExit(0)` and that the printed string contains `coding-agent-playbook` and the value of `__version__`.
- `test_no_args_prints_help_and_exits_zero()` — assert `main([])` returns 0 and prints something containing `"usage"`.
- `test_unimplemented_subcommand_prints_deferred_message()` — invoke `main(["sync"])`; assert exit code 0 and that stderr contains the substring `not implemented yet`.

### 7.2 `tests/unit/test_adapter_base.py`

- `test_adapter_abc_cannot_instantiate()` — `pytest.raises(TypeError)` calling `Adapter()` directly.
- `test_concrete_subclass_can_instantiate()` — define an in-test `class _DummyAdapter(Adapter)` overriding `name = "dummy"`, `write_rule`, `write_prompt`; instantiate; assert `isinstance(_, Adapter)`.
- `test_finalize_default_returns_empty_list()` — instantiate dummy; call `finalize(Path("."))`; assert `== []`.
- `test_default_cleanup_raises_not_implemented_in_pr1()` — instantiate dummy; call `cleanup_stale(set(), Path("."))`; expect `NotImplementedError` referencing PR 6.

### 7.3 `tests/unit/test_sources_base.py`

- `test_artifact_source_abc_cannot_instantiate()` — `pytest.raises(TypeError)`.
- `test_state_source_abc_cannot_instantiate()` — `pytest.raises(TypeError)`.
- `test_artifact_source_subclass_can_instantiate()` — define dummy subclass; instantiate; assert subclass-of.
- `test_state_source_subclass_can_instantiate()` — same shape.

### 7.4 `tests/unit/test_entry_points.py`

- `test_adapters_entry_point_table_loads_without_crashing()` — call `importlib.metadata.entry_points(group="coding_agent_playbook.adapters")`; assert it returns something iterable (will be empty in PR 1; the assertion is structural, not on contents).
- Same shape for `coding_agent_playbook.overlays`, `coding_agent_playbook.artifact_sources`, `coding_agent_playbook.state_sources`, `coding_agent_playbook.runners`, `coding_agent_playbook.judges`.
- `test_engine_package_metadata_resolves()` — `importlib.metadata.metadata("coding-agent-playbook")` returns a metadata object whose `["Name"]` equals `"coding-agent-playbook"`. Confirms the project is installed (CI runs after `uv sync`).

All tests use stdlib + pytest only. No fixture trees needed in PR 1.

---

## 8. Review gates

PR 1 is decomposed into **4 ordered gates**. Each gate is a discrete commit (or 1–2 closely related commits) that compiles, lints, type-checks, and tests green on its own. A reviewer can sign off on each gate without depending on subsequent gates.

### Gate 1 — Scaffolding & CI green

**Contributor pushes:**
- `pyproject.toml` (full file per §5.2 above).
- `src/coding_agent_playbook/__init__.py` (`__version__` only).
- `src/coding_agent_playbook/py.typed` (empty).
- `src/coding_agent_playbook/cli.py` (stub: `--version` + deferred-impl message).
- `tests/__init__.py`, `tests/unit/__init__.py`, `tests/conftest.py` (empty).
- `tests/unit/test_cli.py`.
- `.pre-commit-config.yaml` (engine dev loop).
- `.github/workflows/ci.yml`.
- Append "status: PR 1 scaffolding" paragraph to `README.md`.

**Reviewer checks:**
- [ ] `pyproject.toml` declares `requires-python = ">=3.12"`, runtime deps = `jinja2`, `packaging` only.
- [ ] Both `cap` and `coding-agent-playbook` console-script entries are present.
- [ ] All six entry-point tables (`adapters`, `overlays`, `artifact_sources`, `state_sources`, `runners`, `judges`) are declared, all empty.
- [ ] `[tool.ruff]`, `[tool.mypy]` strict, `[tool.pytest.ini_options]` blocks present and consistent.
- [ ] CI workflow runs `uv sync --extra dev`, `pre-commit run --all-files`, `pytest`, and the two `--version` smoke tests on Python 3.12 and 3.13.
- [ ] `uv sync --extra dev && uv run cap --version` prints a non-empty version string locally.
- [ ] `uv run pytest` is green with only the CLI tests.

### Gate 2 — Adapter ABC + tests

**Contributor pushes (on top of Gate 1):**
- `src/coding_agent_playbook/_typing.py`.
- `src/coding_agent_playbook/adapters/__init__.py` (empty).
- `src/coding_agent_playbook/adapters/base.py` (`Adapter` ABC).
- `tests/unit/test_adapter_base.py`.

**Reviewer checks:**
- [ ] Method signatures in `Adapter` match SPEC §10.1 verbatim (`write_rule`, `write_prompt`, `write_skill`, `finalize`, `cleanup_stale`).
- [ ] `write_rule` and `write_prompt` are `@abstractmethod`; `write_skill`, `finalize`, `cleanup_stale` are not.
- [ ] `finalize` default is `return []`.
- [ ] `_default_cleanup` raises `NotImplementedError` referencing PR 6 (so the inherited `cleanup_stale` is honest about what works in PR 1).
- [ ] `_typing.py` is documented as private (leading underscore + docstring) and uses `TYPE_CHECKING`.
- [ ] Tests assert: ABC cannot instantiate, concrete subclass can, `finalize` returns `[]`, `cleanup_stale` raises `NotImplementedError`.

### Gate 3 — ArtifactSource + StateSource ABCs + tests

**Contributor pushes (on top of Gate 2):**
- `src/coding_agent_playbook/sources/__init__.py` (empty).
- `src/coding_agent_playbook/sources/base.py` (`ArtifactSource` + `StateSource`).
- `tests/unit/test_sources_base.py`.

**Reviewer checks:**
- [ ] Both ABC signatures match SPEC §20.2 verbatim.
- [ ] `ArtifactSource` exposes `list_rules`, `list_prompts`, `list_skills`, `list_eval_tasks` — all `@abstractmethod`, all return `list[...]`.
- [ ] `StateSource` exposes `load_config`, `save_config`, `load_lockfile` (returns `Lockfile | None` per spec), `save_lockfile` — all `@abstractmethod`.
- [ ] `load_lockfile` return annotation is `"Lockfile | None"`, not `"Lockfile"`, matching §20.2.
- [ ] Tests cover instantiation refusal + subclass success for both ABCs.

### Gate 4 — Entry-point discovery smoke test + `.pre-commit-hooks.yaml` placeholder

**Contributor pushes (on top of Gate 3):**
- `.pre-commit-hooks.yaml` (empty-list placeholder).
- `tests/unit/test_entry_points.py`.

**Reviewer checks:**
- [ ] All six entry-point groups (`coding_agent_playbook.adapters`, `coding_agent_playbook.overlays`, `coding_agent_playbook.artifact_sources`, `coding_agent_playbook.state_sources`, `coding_agent_playbook.runners`, `coding_agent_playbook.judges`) load without exception.
- [ ] `importlib.metadata.metadata("coding-agent-playbook")` resolves after `uv sync --extra dev`.
- [ ] `.pre-commit-hooks.yaml` is valid YAML (the engine's own `check-yaml` hook passes).
- [ ] `cap --version` and `coding-agent-playbook --version` both succeed.
- [ ] Final `uv run pytest --cov=coding_agent_playbook` ≥ 80%.

After Gate 4 passes review, PR 1 is ready to merge.

---

## 9. Risks & open decisions

| # | Decision point | Recommendation |
| --- | --- | --- |
| 1 | Build backend: `hatchling` vs `setuptools` vs `flit_core` | `hatchling`. Best `uv` integration, supports `src/` layout and `py.typed` force-include without plugins. |
| 2 | Ship `py.typed` marker? | Yes. Engine is strict-typed by §16 / §17 stance and consumer overlays will rely on its types. PEP 561. |
| 3 | How to reference `Rule`/`Prompt`/`Skill`/`Config`/`Lockfile`/`EvalTask` before they exist | Private `_typing.py` shim, imported under `TYPE_CHECKING`. Runtime symbols are string placeholders. PR 2/5/11 replace shim contents with re-exports from real modules; no ABC file changes. |
| 4 | Are `cap` and `coding-agent-playbook` two distinct entry points or one alias? | Two entry points pointing at the same `coding_agent_playbook.cli:main`. Matches SPEC §12. The function reads `sys.argv[0]` only for `prog=` in argparse, which we hardcode to `"cap"` for consistency — open question flagged below. |
| 5 | `argparse` vs `click` vs `typer` | `argparse` (stdlib). Keeps the runtime dependency budget at `jinja2` + `packaging` per §20.3. CLI surface in PR 10 is modest enough that `argparse` suffices. Open to revisit in PR 10 if subcommand ergonomics suffer. |
| 6 | Should `cap --help` say `prog="cap"` or `prog="coding-agent-playbook"` when invoked as the long name? | Hardcode `prog="cap"` in PR 1 (cosmetic only; `--version` works under either entry point). PR 10 can detect `sys.argv[0]` and switch if needed. **Recommend revisiting in PR 10.** |
| 7 | Empty `.pre-commit-hooks.yaml` (`[]`) vs not shipping the file at all in PR 1 | Ship empty `[]`. Forward-compatible: consumers can attach the repo immediately and it gains hooks once PR 12 lands without re-attaching. |
| 8 | Should PR 1 ship a minimal `docs/` or leave that to PR 14? | Leave to PR 14. README pointer to `SPEC.md` is sufficient. |
| 9 | `gitleaks` in engine pre-commit | Defer to consumer template (§13.2). Network-install on first run conflicts with air-gapped goal §17.1. |
| 10 | Coverage gate (`--cov-fail-under`) | Set to 80% in PR 1. ABCs + tiny CLI stub are easily 100% covered; the floor leaves headroom for future PRs. |
| 11 | Should `_default_cleanup` raise or no-op in PR 1? | Raise `NotImplementedError` with PR 6 pointer. Silent no-op would give concrete adapters a misleading default until PR 6 lands. |
| 12 | Python version matrix in CI (3.12 only or 3.12 + 3.13) | 3.12 + 3.13. Project targets 3.12+; testing both catches future-syntax regressions early. |
| 13 | Does `_typing.py` survive past PR 2, or is it deleted? | Recommend: PR 2 *empties* `_typing.py` to re-export from `coding_agent_playbook.types`. PR 5 adds `Config`/`Lockfile` re-exports. The file can be deleted in PR 11 once `EvalTask` lands, by switching ABC imports to direct package paths. Keeps PR 1's ABC files churn-free across the rest of the implementation. |

**Decisions confirmed by user on 2026-05-22:**
- **#4 / #6**: ship both `cap` and `coding-agent-playbook` entry points pointing at the same handler (`coding_agent_playbook.cli:main`). `prog="cap"` is hardcoded in PR 1; PR 10 may detect `sys.argv[0]` and switch the displayed name if needed.
- **#9**: drop `gitleaks` from the engine's own pre-commit. The hook stays available in the consumer template (§13.2) for repos that want it. The engine relies on `detect-private-key` for in-repo secret scanning during the engine's own dev loop.
- **#13**: private `_typing.py` shim strategy confirmed. PR 2 / PR 5 / PR 11 will swap shim contents to re-export real dataclasses from `coding_agent_playbook.types`, `.config`, `.lockfile`, and `.evals.task`; the ABC files in `adapters/base.py` and `sources/base.py` never need to change.

The remaining items in the table above are recommendations carried into PR 1. Subsequent PRs can revisit any of them, but PR 1 implementation should assume the current row values as binding.

---

## 10. Acceptance criteria for merging PR 1

A reviewer should be able to run the following on a fresh clone and observe each result. All commands assume the repo root as cwd.

```bash
# Environment setup
uv sync --extra dev

# Linting + formatting + static checks
uv run pre-commit run --all-files

# Test suite green, coverage >= 80%
uv run pytest -q

# CLI entry points both work
uv run cap --version
uv run coding-agent-playbook --version

# Subcommand stub prints deferred message (exit 0)
uv run cap sync
echo "exit code: $?"   # expect 0
```

Checklist:
- [ ] `pyproject.toml` parses; `uv sync --extra dev` succeeds without network access beyond PyPI mirrors.
- [ ] `pre-commit run --all-files` is green.
- [ ] `pytest -q` is green; ≥ 80% coverage on `coding_agent_playbook` package.
- [ ] `cap --version` and `coding-agent-playbook --version` both print a non-empty version line.
- [ ] `cap sync` exits 0 with the deferred-implementation message on stderr.
- [ ] `python -c "from coding_agent_playbook.adapters.base import Adapter; from coding_agent_playbook.sources.base import ArtifactSource, StateSource"` runs without error.
- [ ] All six `[project.entry-points.*]` tables are declared in `pyproject.toml` and load via `importlib.metadata.entry_points(group=...)` returning an iterable (empty is fine).
- [ ] `py.typed` marker is included in the installed wheel (`python -c "import importlib.resources, coding_agent_playbook; print((importlib.resources.files(coding_agent_playbook) / 'py.typed').is_file())"` prints `True`).
- [ ] CI workflow on `main` is green on Python 3.12 and 3.13.
- [ ] No new runtime dependency beyond `jinja2` and `packaging`.
- [ ] No network call at import or `--version` time.

Once all checks pass and gates 1–4 are individually approved, PR 1 is ready to merge to `main`. PR 2 (canonical types) can then start by deleting/rewriting `_typing.py` and adding `src/coding_agent_playbook/types.py`.
