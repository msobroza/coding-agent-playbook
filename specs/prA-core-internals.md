# PR A — core engine internals (detector + renderer + filesystem sources)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three core internal modules that unblock every adapter (PRs 6–9) — `detector.py` (facts inventory), `renderer.py` (Jinja env + `rule()` helper), and `sources/filesystem.py` (the v1 `FileSystemArtifactSource` + `FileSystemStateSource`). Adds `config.py` + `lockfile.py` as data types alongside the filesystem source.

**Architecture:** Three independent tracks that touch zero overlapping files — dispatchable in parallel as separate subagents in separate worktrees. After all three implement-and-self-verify cleanly, the dispatcher merges them into a single integration branch (`prA-core-internals`), runs the full CI gate locally (matching `.github/workflows/ci.yml` exactly), then pushes and opens the PR for the user gate.

| Track | Files | Subagent worktree | LoC |
| --- | --- | --- | --- |
| A — Detector | `src/coding_agent_playbook/detector.py`, `tests/unit/test_detector.py` | `.claude/worktrees/prA-detector` | ~450 |
| B — Renderer | `src/coding_agent_playbook/renderer.py`, `tests/unit/test_renderer.py` | `.claude/worktrees/prA-renderer` | ~300 |
| C — Filesystem sources | `src/coding_agent_playbook/config.py`, `src/coding_agent_playbook/lockfile.py`, `src/coding_agent_playbook/sources/filesystem.py`, `tests/unit/test_config.py`, `tests/unit/test_lockfile.py`, `tests/unit/test_sources_filesystem.py`, plus `pyproject.toml` entry-point updates | `.claude/worktrees/prA-sources` | ~550 |
| Integration | merge + final CI gates + PR | `.claude/worktrees/prA-integration` | — |

**Tech Stack:** Python 3.12+, `jinja2>=3.1.4`, `packaging>=24.0`, `pyyaml>=6.0`, stdlib (`tomllib`, `pathlib`, `dataclasses`, `hashlib`, `importlib.resources`, `importlib.metadata`). No new runtime deps.

---

## Context for fresh subagents

You are working on `coding-agent-playbook`, a Python-first engine that takes one canonical source of organizational coding context (rules, prompts, skills in markdown + YAML frontmatter) and renders it into each AI coding assistant's expected shape. The design lives in `SPEC.md`.

Repo conventions:
- Python 3.12+, `uv` for env management. Always use `uv run <tool>` locally.
- `ruff` for lint+format, `mypy --strict`, `pytest` for tests. CI runs `mypy` (no args) and `pytest -q` (no args) — these honor `pyproject.toml` config and check both `src/` and `tests/`. **Local verification must match CI exactly.**
- **Commit authorship:** all commits authored solely by the user (`msobroza`). **Never add `Co-Authored-By:` trailers. Never pass `--author`. Never modify `git config`.** See `CLAUDE.md` "Commit policy" for the full rule.
- **Adapters, sources, and overlays register via `[project.entry-points]`** — never instantiate them directly.

What already exists (merged on `main`):
- `src/coding_agent_playbook/types.py` — `Rule`, `Prompt`, `Skill` dataclasses with markdown ↔ dict round-trip
- `src/coding_agent_playbook/adapters/base.py` — `Adapter` ABC (waiting for PRs 6–9)
- `src/coding_agent_playbook/sources/base.py` — `ArtifactSource` and `StateSource` ABCs
- `src/coding_agent_playbook/cli.py` — CLI subcommands stubbed, just print deferred messages
- `src/coding_agent_playbook/_typing.py` — `TYPE_CHECKING`-only forward refs for `Rule`, `Prompt`, `Skill`, `EvalTask`, `Config`, `Lockfile`

What this PR adds (three new modules + two data-type modules):
- `detector.py` (Track A)
- `renderer.py` (Track B)
- `config.py`, `lockfile.py`, `sources/filesystem.py` (Track C)

---

## File structure

### Track A — detector

| File | Responsibility |
| --- | --- |
| `src/coding_agent_playbook/detector.py` | `Facts` TypedDict, `detect(repo_root) -> Facts`, `evaluate_predicate(predicate, facts) -> bool`. Inspects `pyproject.toml`, lockfiles, and the filesystem to produce the rendering context. No I/O outside `repo_root`. |
| `tests/unit/test_detector.py` | Synthetic repo fixtures (FastAPI app, ML research, notebook-only, library, empty) → assert correct `Facts`. Parametrized predicate-evaluation tests covering every operator. |

### Track B — renderer

| File | Responsibility |
| --- | --- |
| `src/coding_agent_playbook/renderer.py` | Jinja2 `Environment` with `StrictUndefined`, `render_artifact_body(template_path, context)` dispatching on `.md` vs `.md.j2`, `render_for(template_path, context, fmt)` applying per-format post-processing, and the `rule()` Jinja helper plumbing (the rule registry itself is supplied by the caller — `cap sync` in PR 10). |
| `tests/unit/test_renderer.py` | Plain `.md` returns body verbatim; `.md.j2` substitutes vars; `StrictUndefined` raises on typos; `rule()` helper available in prompts but not rules; per-format transforms produce expected output for `continue_rule`, `claude_md_section`, `prompt_claude_command`, etc. |

### Track C — filesystem sources (+ data types)

| File | Responsibility |
| --- | --- |
| `src/coding_agent_playbook/config.py` | `Config` dataclass mirroring `.coding-agent-playbook.toml` schema (SPEC §7.1). Pure data + `from_dict` / `to_dict`. No I/O. |
| `src/coding_agent_playbook/lockfile.py` | `Lockfile` dataclass + helpers to compute a content hash for a rendered file and assemble lockfile entries (SPEC §14.4). Pure data + `from_dict` / `to_dict`. No I/O. |
| `src/coding_agent_playbook/sources/filesystem.py` | `FileSystemArtifactSource` (walks `importlib.resources` for engine + overlay packages, plus `<repo>/playbook/` for repo-local artifacts) and `FileSystemStateSource` (reads/writes the three TOML files: `.coding-agent-playbook.toml`, `.coding-agent-playbook.local.toml`, `.coding-agent-playbook.lock`). |
| `pyproject.toml` | Register the filesystem implementations under `coding_agent_playbook.artifact_sources` and `coding_agent_playbook.state_sources` entry-point groups. |
| `tests/unit/test_config.py`, `tests/unit/test_lockfile.py`, `tests/unit/test_sources_filesystem.py` | Dataclass round-trips; filesystem source walks a synthetic repo correctly; missing optional files (no `playbook/`, no `.local.toml`) handled gracefully; entry-point discovery loads the filesystem source. |

---

## Track A — Detector

Implements SPEC §8. Single subagent owns this track in its own worktree.

### A.1 Public API (`src/coding_agent_playbook/detector.py`)

```python
"""Detector subsystem: inspect a consumer repo and produce a Facts dict.

See SPEC.md §8. The Facts dict feeds the renderer's context (SPEC §9.4) and the
`applies_if` predicate evaluator (SPEC §6.4). Detector runs at cap init, is
cached in `.coding-agent-playbook.toml`, and refreshes on `pyproject.toml`
mtime change or `cap check --refresh`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict

# All entries are optional — the detector only sets keys it can determine.
class Facts(TypedDict, total=False):
    python_version: str
    package_manager: Literal["uv", "poetry", "pip-tools", "pip"]
    project_kind: Literal[
        "python-application",
        "python-library",
        "ml-research",
        "notebook",
        "python-unknown",
    ]
    dependencies: dict[str, str]
    dev_dependencies: dict[str, str]
    frameworks: dict[str, str]
    ml_stack: dict[str, str]
    has_notebooks: bool
    has_dockerfile: bool
    has_ci: bool
    dev_tools: set[str]


# Frameworks the detector recognises (subset of dependencies treated as frameworks).
KNOWN_FRAMEWORKS: frozenset[str] = frozenset({
    "fastapi", "flask", "django", "starlette",
    "pydantic", "sqlalchemy", "alembic",
    "pytest", "pytest-asyncio", "pytest-mock", "unittest",
    "httpx", "requests", "aiohttp",
    "click", "typer",
})

KNOWN_ML_STACK: frozenset[str] = frozenset({
    "torch", "tensorflow", "jax", "transformers",
    "scikit-learn", "xgboost", "lightgbm", "numpy", "pandas",
    "matplotlib", "seaborn", "polars", "duckdb",
})

KNOWN_DEV_TOOLS: frozenset[str] = frozenset({
    "ruff", "black", "flake8", "isort", "mypy", "pyright", "pylint",
})


def detect(repo_root: Path) -> Facts:
    """Run all detector passes against ``repo_root`` and return Facts.

    Reads ``pyproject.toml`` if present, walks for lockfiles and config files,
    and only sets dict keys it can determine. Never raises — a repo with no
    ``pyproject.toml`` returns ``Facts(project_kind="python-unknown")``.
    """
    ...


def evaluate_predicate(predicate: dict[str, Any], facts: Facts) -> bool:
    """Evaluate an ``applies_if`` predicate against facts (SPEC §6.4).

    Supported keys:
      - ``python_version: ">=3.11"`` — semver-style comparison
      - ``has_framework: ["fastapi"]`` — ALL must be present in facts["frameworks"]
      - ``any_framework: ["pytest", "unittest"]`` — at least one present
      - ``has_file: ["Dockerfile"]`` — file exists in repo root (relative paths)
      - ``banking_mode: true`` — boolean facts compared by equality

    Multiple keys are AND-ed together. Unknown keys raise ``ValueError``
    so typos fail loudly at validate time.
    """
    ...
```

### A.2 Implementation notes

- **`python_version` precedence:** parsed from `pyproject.toml [project] requires-python` (minimum bound), falling back to running `python --version`. Always returned as `"3.12"`-shaped string (major.minor).
- **`package_manager` detection:** check in this order — `uv.lock` → `uv`, `poetry.lock` → `poetry`, `pyproject.toml [tool.poetry]` → `poetry`, `requirements.in` → `pip-tools`, `requirements.txt` → `pip`, otherwise `pip`.
- **`dependencies` / `dev_dependencies`:** parsed from `pyproject.toml [project] dependencies` and `[project.optional-dependencies]`/`[dependency-groups]` per PEP 621/735. Versions resolved from the lockfile when present (read the lockfile in TOML or text mode and grep the line); otherwise use the version spec verbatim.
- **`frameworks` and `ml_stack`:** filter `dependencies` (NOT `dev_dependencies` for ml_stack; pytest is dev) by the `KNOWN_*` sets. `frameworks` INCLUDES dev-deps that are testing frameworks (pytest, pytest-asyncio).
- **`has_notebooks`:** use `repo_root.rglob("*.ipynb")` — stop at first hit, ignore `.venv`, `node_modules`, `.git`, `__pycache__`.
- **`has_dockerfile`:** `(repo_root / "Dockerfile").exists()` OR `(repo_root / "docker").is_dir()`.
- **`has_ci`:** `(repo_root / ".github" / "workflows").is_dir()` OR any of `Jenkinsfile`, `.gitlab-ci.yml`, `.circleci/`.
- **`dev_tools`:** subset of `dev_dependencies` keys matching `KNOWN_DEV_TOOLS`, PLUS keys derived from config presence: `ruff` if `[tool.ruff]` in pyproject, `black` if `[tool.black]`, `mypy` if `[tool.mypy]`, etc.
- **`project_kind`:** per SPEC §8.3 algorithm:

```python
def _infer_kind(facts: Facts, repo_root: Path) -> str:
    has_src = (repo_root / "src").is_dir()
    notebooks = facts.get("has_notebooks", False)
    frameworks = set(facts.get("frameworks", {}).keys())

    if notebooks and not has_src:
        return "notebook"
    if notebooks and has_src:
        return "ml-research"
    if has_src and "fastapi" in frameworks:
        return "python-application"
    if has_src:
        return "python-library"
    return "python-unknown"
```

- **`evaluate_predicate` semver comparison:** use `packaging.version.Version` (already in deps) for `python_version` comparisons. Operator parsing: a leading `>=`, `>`, `==`, `<=`, `<`, `~=` is the operator; rest is the version. Reject anything else with `ValueError`.

### A.3 Tests (`tests/unit/test_detector.py`)

Required test coverage (each is one bite-sized test function):

- `test_detect_fastapi_app` — synthetic repo with `pyproject.toml` declaring fastapi + pydantic + pytest, `src/` layout, `Dockerfile`, `.github/workflows/ci.yml`. Assert `project_kind == "python-application"`, frameworks present, `has_dockerfile is True`, `has_ci is True`.
- `test_detect_ml_research` — synthetic repo with `src/`, notebooks, and torch in deps. Assert `project_kind == "ml-research"`, `ml_stack` populated.
- `test_detect_notebook_only` — no `src/`, just `*.ipynb`. Assert `project_kind == "notebook"`.
- `test_detect_python_library` — `src/`, no fastapi, no notebooks. Assert `project_kind == "python-library"`.
- `test_detect_empty_repo` — no `pyproject.toml`. Assert `project_kind == "python-unknown"`, other keys absent.
- `test_detect_package_manager_uv` / `test_detect_package_manager_poetry` / `test_detect_package_manager_pip` — by lockfile presence.
- `test_detect_dev_tools_from_config_section` — `[tool.ruff]` in pyproject (no dep) still detected.
- `test_detect_python_version_from_requires_python` — `>=3.12` → `"3.12"`.
- `test_evaluate_predicate_python_version` — `python_version: ">=3.11"` against facts with `"3.12"` → True; against `"3.10"` → False.
- `test_evaluate_predicate_has_framework_all_present` — list of frameworks all in facts → True; one missing → False.
- `test_evaluate_predicate_any_framework_one_present` — at least one in facts → True; none → False.
- `test_evaluate_predicate_has_file` — file exists → True; missing → False. (Test uses `tmp_path` to set up files.)
- `test_evaluate_predicate_boolean` — `banking_mode: true` matches; explicit False vs absent both fail.
- `test_evaluate_predicate_multiple_keys_anded` — two keys both true → True; one false → False.
- `test_evaluate_predicate_unknown_key_raises` — `wat: 1` raises `ValueError` matching `unknown predicate`.

Fixture pattern: each test builds a `tmp_path / "synthetic-repo"` with `pyproject.toml` and other files as needed, calls `detect(synthetic_repo_root)`, asserts on the returned `Facts`. No mocks.

### A.4 Track A tasks (TDD steps)

- [ ] **Task A.1 — Detector module skeleton with TypedDict and constants**

Create `src/coding_agent_playbook/detector.py` with:
- Module docstring referencing SPEC §8
- `from __future__ import annotations`
- `Facts` TypedDict
- `KNOWN_FRAMEWORKS`, `KNOWN_ML_STACK`, `KNOWN_DEV_TOOLS` frozensets (lists in A.1 above)
- `detect(repo_root: Path) -> Facts` and `evaluate_predicate(predicate, facts) -> bool` stubs that `raise NotImplementedError("...")`.

Run `uv run mypy` — must pass.

Commit: `feat(detector): scaffold detector module (Facts TypedDict + constants + stubs)`

- [ ] **Task A.2 — TDD: detect FastAPI app fixture**

Write `tests/unit/test_detector.py` with the FastAPI-app fixture test (full code in A.3). Run pytest: must FAIL on `NotImplementedError`.

Implement just enough of `detect()` to pass:
- Read `pyproject.toml` via `tomllib`
- Pull `requires-python` → `python_version`
- Pull `dependencies` → `dependencies` dict (use first version constraint as-is for now; lockfile resolution comes later)
- Filter `dependencies` by `KNOWN_FRAMEWORKS` → `frameworks`
- Detect `has_dockerfile`, `has_ci` (file/dir checks)
- Detect `has_notebooks` (rglob, ignore `.venv` etc.)
- Implement `_infer_kind` and call it

Run pytest: must PASS. Commit: `feat(detector): detect python-application kind + frameworks + has_dockerfile/has_ci`.

- [ ] **Task A.3 — TDD: each remaining kind in one cycle**

For each of `ml-research`, `notebook-only`, `python-library`, `python-unknown`: write the fixture test, run, watch fail, extend detect, run, watch pass. Single commit at the end: `feat(detector): infer ml-research, notebook, python-library, python-unknown`.

- [ ] **Task A.4 — TDD: package_manager detection by lockfile**

Add the three package-manager tests (uv, poetry, pip — others optional). Implement the lockfile-presence cascade. Commit: `feat(detector): identify package manager from lockfile`.

- [ ] **Task A.5 — TDD: dev_tools from config sections**

Add `test_detect_dev_tools_from_config_section` (no dep declared, just `[tool.ruff]` in pyproject). Implement the merge of dev-dep names + config-section names. Commit: `feat(detector): include dev tools from pyproject config sections`.

- [ ] **Task A.6 — TDD: evaluate_predicate, one operator per commit**

For each predicate operator (`python_version`, `has_framework`, `any_framework`, `has_file`, boolean equality, multi-key AND, unknown-key error): write the test, run, watch fail, implement, run, watch pass. **Commit per operator** so reviewers can read the diff one operator at a time. Final commit: `feat(detector): evaluate_predicate handles AND across multi-key dicts and unknown-key error`.

- [ ] **Task A.7 — Final track-A verification**

Run from worktree root:

```bash
uv run pytest tests/unit/test_detector.py -v          # all detector tests pass
uv run pytest                                          # full suite still passes
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy                                            # no args; matches CI
```

All must be clean. If any noise, fix in this track before reporting DONE.

---

## Track B — Renderer

Implements SPEC §9. Single subagent owns this track in its own worktree.

### B.1 Public API (`src/coding_agent_playbook/renderer.py`)

```python
"""Renderer subsystem: Jinja2 environment + format post-processing.

See SPEC.md §9. Frontmatter is parsed by the engine before this module runs
and is always treated as static YAML — only the body is rendered through Jinja.
File-extension dispatch: ``.md`` body is returned verbatim; ``.md.j2`` body is
rendered through Jinja2 with ``StrictUndefined`` so typos fail loudly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Literal, Protocol

from jinja2 import Environment, FileSystemLoader, StrictUndefined


# Aliases the CLI accepts as a short-form for --format. Resolved to the full
# internal name before render_for() dispatches.
FORMAT_ALIASES: dict[str, str] = {
    "continue": "continue_rule",
    "claude": "claude_md_section",
    "agents": "agents_md_section",
    "opencode": "prompt_opencode_command",
}

# All built-in formats. Adapters may register more via the renderer registry
# (future work — v1 just has the built-ins inline here).
BUILTIN_FORMATS: frozenset[str] = frozenset({
    "continue_rule",
    "claude_md_section",
    "agents_md_section",
    "prompt_continue",
    "prompt_claude_command",
    "prompt_opencode_command",
})


class RuleRegistry(Protocol):
    """Minimal interface used by the ``rule()`` Jinja helper.

    The full registry lives in PR 10 (the CLI / sync orchestrator); this
    protocol is the contract the renderer depends on. Tests can pass an
    in-memory implementation; production passes the merged-overlay registry.
    """

    def render_for_inclusion(self, rule_id: str, context: dict[str, Any]) -> str:
        """Return the rendered body of ``rule_id`` for inline placement in a
        prompt, with a ``### {rule.name}`` header prepended. Returns ``""``
        if the rule's ``applies_if`` evaluates to false for the current facts.
        """


def build_environment(
    template_search_paths: list[Path],
    *,
    is_prompt_context: bool = False,
    rule_registry: RuleRegistry | None = None,
) -> Environment:
    """Build a Jinja Environment configured per SPEC §9.3.

    ``is_prompt_context=True`` registers the ``rule()`` helper (and requires
    ``rule_registry`` to be passed). For rules, ``rule()`` is not registered
    so calling it raises ``UndefinedError`` — that enforces the "rules cannot
    include other rules" invariant at the renderer level.
    """
    ...


def render_artifact_body(
    template_path: Path,
    context: dict[str, Any],
    *,
    env: Environment,
) -> str:
    """Dispatch on extension. ``.md`` returns the file verbatim; ``.md.j2``
    is rendered through ``env``. The body is the only part rendered;
    frontmatter must be split off by the caller first.
    """
    ...


def render_for(
    template_path: Path,
    body: str,
    fmt: str,
    *,
    frontmatter: dict[str, Any],
) -> str:
    """Apply per-format post-processing to a Jinja-rendered body.

    ``fmt`` is one of the formats in ``BUILTIN_FORMATS`` (or a short alias in
    ``FORMAT_ALIASES``). Behaviour per format is documented in SPEC §9.7.
    """
    ...
```

### B.2 Implementation notes

- **`build_environment`:** straight Jinja2 config:
  ```python
  env = Environment(
      loader=FileSystemLoader([str(p) for p in template_search_paths]),
      autoescape=False,
      keep_trailing_newline=True,
      trim_blocks=True,
      lstrip_blocks=True,
      undefined=StrictUndefined,
  )
  if is_prompt_context:
      if rule_registry is None:
          raise ValueError("rule_registry required when is_prompt_context=True")
      env.globals["rule"] = lambda rule_id: rule_registry.render_for_inclusion(
          rule_id, env.globals.get("_facts", {})
      )
  # has_framework helper (SPEC §9.4)
  def _has_framework(name: str) -> bool:
      facts = env.globals.get("_facts", {})
      return name in facts.get("frameworks", {})
  env.globals["has_framework"] = _has_framework
  return env
  ```
  Pattern: callers stash facts into `env.globals["_facts"]` before each render. Simpler than passing facts through every helper.

- **`render_artifact_body`:** dispatch:
  ```python
  if template_path.suffix == ".j2":
      template = env.get_template(template_path.name)
      return template.render(**context)
  return template_path.read_text(encoding="utf-8")
  ```
  Note: `env.get_template(template_path.name)` resolves the template via the loader's search paths — make sure callers pass the *relative* template name when looking up via the env, or use `env.from_string(template_path.read_text())` if they have the body in hand already. Two-variant API: `render_artifact_body(template_path, ..., env=env)` uses the loader; `render_string(body, context, *, env=env)` renders a literal string.

  Add `render_string(body: str, context: dict, *, env: Environment) -> str` as a helper — used by the rule-inclusion path and by tests.

- **`render_for` transforms** (one branch per format):
  - `continue_rule`: emit `<!-- AUTOGENERATED ... -->\n---\n{frontmatter as Continue-shaped YAML}\n---\n{body}`. Drop `id`, `version`, `scope`, `priority`, `tags`, `applies_if` from the emitted frontmatter (Continue uses `name`, `description`, `globs`, `alwaysApply`). Map `scope == "always"` → `alwaysApply: true`, else `false`. Map `globs` list as-is.
  - `claude_md_section`: emit `## {frontmatter.name}\n\n*Applies to: \`{globs}\`*\n\n{body}\n\n---\n` when `scope == "scoped"` and globs are set; otherwise just `## {name}\n\n{body}\n\n---\n`.
  - `agents_md_section`: identical to `claude_md_section`.
  - `prompt_continue`: emit `<!-- AUTOGENERATED ... -->\n---\nname: ...\ndescription: ...\ninvokable: true\n---\n{body}`. If body has no `{{ rule() }}` calls AND `includes_rules:` is set, append a `## Reference rules\n\n### {rule.name}\n\n{rule body}\n\n...` section per SPEC §6.2.5.
  - `prompt_claude_command`: emit `{body}` (Claude Code commands are pure markdown). If no leading title, prepend `# {frontmatter.name}\n\n`. Same `includes_rules:` appendix logic.
  - `prompt_opencode_command`: emit `---\ndescription: {description}\n---\n{body}`. Map `input_variables` to `$ARGUMENTS` / `$1` / `$2` in the body via a simple `str.replace` on `{{ target }}` → `$ARGUMENTS` (only if exactly one input variable; otherwise `$1`, `$2`, ...). Same `includes_rules:` appendix logic.

  For the `includes_rules:` appendix, the renderer needs access to the rule registry. Pass it as an optional arg to `render_for`:

  ```python
  def render_for(
      template_path: Path,
      body: str,
      fmt: str,
      *,
      frontmatter: dict[str, Any],
      rule_registry: RuleRegistry | None = None,
  ) -> str: ...
  ```

  When `frontmatter.get("includes_rules")` is set AND `"{{ rule(" not in body` AND `rule_registry is not None`, append the section.

- **Sentinel header constant:**
  ```python
  SENTINEL = "AUTOGENERATED by coding-agent-playbook — edit in source, run 'cap sync'"
  ```
  Used in the `continue_rule` and `prompt_continue` HTML-comment header and in CLAUDE.md's first line (when ClaudeCodeAdapter composes it in PR 7).

### B.3 Tests (`tests/unit/test_renderer.py`)

- `test_plain_md_body_returned_verbatim` — write `body.md`, render, assert body matches input byte-for-byte (no Jinja).
- `test_md_j2_body_substitutes_variables` — template `Hello {{ name }}`, context `{"name": "World"}`, expect `Hello World`.
- `test_strict_undefined_raises_on_typo` — template `{{ python_versoin }}` against `{"python_version": "3.12"}` → expect `UndefinedError`.
- `test_has_framework_helper_true_when_present` — context with `frameworks: {fastapi: ...}`, template `{% if has_framework("fastapi") %}yes{% endif %}` → "yes".
- `test_has_framework_helper_false_when_absent` — same template, no framework → "".
- `test_rule_helper_registered_in_prompt_env` — build env with `is_prompt_context=True` + stub registry → `{{ rule("foo") }}` returns the stub's output.
- `test_rule_helper_not_registered_in_rule_env` — `is_prompt_context=False` → `{{ rule("foo") }}` raises `UndefinedError`.
- `test_rule_helper_requires_registry_in_prompt_env` — `is_prompt_context=True` without `rule_registry` → `ValueError` at env-build time.
- `test_render_for_continue_rule` — frontmatter `{id, name, description, scope=always, globs=[...]}` → expect `alwaysApply: true`, emitted frontmatter has only Continue's keys, sentinel HTML comment present.
- `test_render_for_continue_rule_scoped` — `scope=scoped` → `alwaysApply: false`, globs preserved.
- `test_render_for_claude_md_section_scoped` — emits `## {name}` and the italic `*Applies to: ...*` line.
- `test_render_for_claude_md_section_always` — emits `## {name}` with no scope line.
- `test_render_for_agents_md_section_identical_to_claude` — same input, both formats produce byte-identical output.
- `test_render_for_prompt_continue_with_includes_rules_appendix` — body has no `{{ rule(...) }}`, `includes_rules: ["x"]`, stub registry returns `### X\n\nrule body\n`. Expect appendix appended.
- `test_render_for_prompt_continue_no_appendix_when_inline_rule_call` — body contains `{{ rule("x") }}`, even with `includes_rules` set, no appendix appended (author placed it inline).
- `test_render_for_prompt_opencode_command_single_arg_substitution` — body `{{ target }}`, one input variable → `$ARGUMENTS`.
- `test_render_for_prompt_opencode_command_multi_arg_substitution` — body `{{ a }} {{ b }}`, two input variables → `$1 $2`.
- `test_format_alias_resolution` — `render_for(..., fmt="continue")` and `fmt="continue_rule"` produce identical output.
- `test_unknown_format_raises_value_error` — `fmt="bogus"` raises `ValueError` listing valid formats.

Helper: a `StubRuleRegistry` in the test file:

```python
class StubRuleRegistry:
    def __init__(self, fragments: dict[str, str]) -> None:
        self._fragments = fragments

    def render_for_inclusion(self, rule_id: str, context: dict[str, Any]) -> str:
        return self._fragments.get(rule_id, "")
```

### B.4 Track B tasks

- [ ] **Task B.1 — Module skeleton + constants + signatures**

Create `src/coding_agent_playbook/renderer.py` with:
- Module docstring referencing SPEC §9
- `from __future__ import annotations`
- `FORMAT_ALIASES`, `BUILTIN_FORMATS`, `SENTINEL` constants
- `RuleRegistry` Protocol
- `build_environment`, `render_artifact_body`, `render_string`, `render_for` stubs that raise `NotImplementedError`

Run `uv run mypy` — must pass.

Commit: `feat(renderer): scaffold renderer module (Jinja env + format dispatch signatures)`.

- [ ] **Task B.2 — TDD: build_environment + plain .md passthrough**

Tests: `test_plain_md_body_returned_verbatim`, `test_md_j2_body_substitutes_variables`, `test_strict_undefined_raises_on_typo`. Run, watch fail. Implement `build_environment` + `render_artifact_body` + `render_string`. Run, watch pass.

Commit: `feat(renderer): build_environment + extension-dispatch body rendering`.

- [ ] **Task B.3 — TDD: helpers (has_framework, rule)**

Tests: `test_has_framework_helper_true_when_present`, `..._false_when_absent`, `test_rule_helper_registered_in_prompt_env`, `..._not_registered_in_rule_env`, `..._requires_registry_in_prompt_env`. Run, watch fail. Implement helpers in `build_environment`. Run, watch pass.

Commit: `feat(renderer): has_framework + rule Jinja helpers with prompt-only registration`.

- [ ] **Task B.4 — TDD: render_for transforms (one commit per format pair)**

Format work in three commits:

1. `feat(renderer): render_for continue_rule + alias resolution + unknown-format error`
2. `feat(renderer): render_for claude_md_section + agents_md_section (identical output)`
3. `feat(renderer): render_for prompt_continue / prompt_claude_command / prompt_opencode_command + includes_rules appendix`

For each commit: write the tests for that format pair, watch them fail, implement the transform, watch them pass.

- [ ] **Task B.5 — Final track-B verification**

Same gates as Track A:

```bash
uv run pytest tests/unit/test_renderer.py -v
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
```

All clean. Report DONE.

---

## Track C — Filesystem sources (+ config + lockfile data types)

Implements SPEC §7 (config), §14.4 (lockfile content), and §20.3 (filesystem sources). Single subagent owns this track in its own worktree.

### C.1 `src/coding_agent_playbook/config.py`

```python
"""Config dataclass mirroring .coding-agent-playbook.toml (SPEC §7.1).

Pure data type. The FileSystemStateSource (sources/filesystem.py) is
responsible for loading and writing TOML files; this module only defines
the in-memory shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectMeta:
    name: str
    kind: str
    description: str = ""


@dataclass
class StorageConfig:
    artifact_source: str = "filesystem"
    state_source: str = "filesystem"


@dataclass
class Config:
    schema_version: int
    project: ProjectMeta
    engine_version: str
    overlays_enabled: list[str] = field(default_factory=list)
    adapters_enabled: list[str] = field(default_factory=list)
    storage: StorageConfig = field(default_factory=StorageConfig)
    detector_cache: dict[str, Any] = field(default_factory=dict)
    user_choices: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config: ...
    def to_dict(self) -> dict[str, Any]: ...
```

`from_dict`/`to_dict` mirror the TOML schema in SPEC §7.1. Keys absent in TOML default to dataclass defaults (e.g. `[storage]` absent → both filesystem).

### C.2 `src/coding_agent_playbook/lockfile.py`

```python
"""Lockfile dataclass + hash helpers (SPEC §14.4).

The lockfile records ``sha256`` content hashes of every generated file plus
the engine version that produced them. ``cap sync --check`` uses this to
detect drift between canonical source and rendered output.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def compute_hash(content: bytes) -> str:
    """sha256 hex digest of ``content``. Stable across platforms (binary mode)."""
    return hashlib.sha256(content).hexdigest()


@dataclass
class LockEntry:
    path: str               # relative to repo root, posix forward slashes
    sha256: str
    bytes: int


@dataclass
class Lockfile:
    schema_version: int
    engine_version: str
    rendered_at: str        # ISO-8601 UTC timestamp from when sync ran
    entries: list[LockEntry] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Lockfile: ...
    def to_dict(self) -> dict[str, Any]: ...

    def find(self, repo_relative_path: str) -> LockEntry | None: ...
```

### C.3 `src/coding_agent_playbook/sources/filesystem.py`

```python
"""Filesystem-backed ArtifactSource and StateSource (SPEC §20.3).

These are the v1 implementations. They depend only on stdlib (tomllib,
pathlib, importlib.resources, importlib.metadata) plus pyyaml for the
frontmatter helpers already in types.py.
"""

from __future__ import annotations

import tomllib
from importlib import metadata, resources
from pathlib import Path
from typing import Any

from coding_agent_playbook.config import Config
from coding_agent_playbook.lockfile import Lockfile
from coding_agent_playbook.sources.base import ArtifactSource, StateSource
from coding_agent_playbook.types import Prompt, Rule, Skill


# Placeholder for eval tasks until PR 11 defines the type. Listed by ID only
# for now so that list_eval_tasks() can return an empty list without raising.
EvalTask = Any  # type: ignore[assignment]


class FileSystemArtifactSource(ArtifactSource):
    """Walks importlib.resources for the engine + overlay packages, plus
    <repo>/playbook/ for repo-local artifacts (SPEC §20.3, §11)."""

    name = "filesystem"

    def __init__(
        self,
        *,
        repo_root: Path,
        engine_package: str = "coding_agent_playbook",
        overlay_packages: list[str] | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._engine_package = engine_package
        self._overlay_packages = overlay_packages or []

    def list_rules(self) -> list[Rule]: ...
    def list_prompts(self) -> list[Prompt]: ...
    def list_skills(self) -> list[Skill]: ...
    def list_eval_tasks(self) -> list[EvalTask]:
        # PR 11 populates this with real EvalTask objects.
        return []


class FileSystemStateSource(StateSource):
    """Reads + writes the three TOML files in the consumer repo:
    .coding-agent-playbook.toml, .coding-agent-playbook.local.toml,
    .coding-agent-playbook.lock (SPEC §7, §14.4, §20.3)."""

    name = "filesystem"

    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root = repo_root

    def load_config(self) -> Config: ...
    def save_config(self, config: Config) -> None: ...
    def load_lockfile(self) -> Lockfile | None: ...
    def save_lockfile(self, lockfile: Lockfile) -> None: ...
```

### C.4 Implementation notes for Track C

**`FileSystemArtifactSource.list_rules`:**

```python
def list_rules(self) -> list[Rule]:
    rules: list[Rule] = []
    # Engine package
    rules.extend(self._walk_rules(self._engine_package))
    # Overlay packages (later overrides earlier on ID collision — collision
    # handling is the orchestrator's job in PR 10, not the source's)
    for pkg in self._overlay_packages:
        rules.extend(self._walk_rules(pkg))
    # Repo-local playbook/
    playbook_rules = self._repo_root / "playbook" / "rules"
    if playbook_rules.is_dir():
        for md in self._iter_md_files(playbook_rules):
            rules.append(Rule.from_markdown(md, "<repo-local>"))
    return rules

def _walk_rules(self, package: str) -> list[Rule]:
    rules: list[Rule] = []
    try:
        resources_root = resources.files(package).joinpath("resources", "rules")
    except (ModuleNotFoundError, FileNotFoundError):
        return []
    if not resources_root.is_dir():
        return []
    for md in self._iter_md_files(Path(str(resources_root))):
        rules.append(Rule.from_markdown(md, package))
    return rules

def _iter_md_files(self, root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.md*")):
        if path.suffix in (".md", ".j2") and path.name.endswith(("md", "md.j2")):
            yield path
```

(Same shape for `list_prompts` walking `resources/prompts/` and `list_skills` walking `resources/skills/`. The skills loader builds `Skill` directly from the `SKILL.md.j2` file in each subdirectory plus the optional `scripts/` and `references/` sibling dirs — see SPEC §6.3.1.)

**`FileSystemStateSource.load_config`:**

```python
def load_config(self) -> Config:
    primary = self._repo_root / ".coding-agent-playbook.toml"
    if not primary.is_file():
        raise FileNotFoundError(f"missing {primary.name}; run `cap init`")
    with primary.open("rb") as f:
        data = tomllib.load(f)
    # Merge .local.toml on top if present
    local = self._repo_root / ".coding-agent-playbook.local.toml"
    if local.is_file():
        with local.open("rb") as f:
            local_data = tomllib.load(f)
        data = _deep_merge(data, local_data)
    return Config.from_dict(data)
```

`_deep_merge(base, override)` is a small recursive merge that lets `[user_choices]` keys in `.local.toml` override the committed `[user_choices]` block.

**`save_config`:** write `.coding-agent-playbook.toml` via standard library — Python 3.12 doesn't have a built-in TOML writer (only reader). Use a simple custom serializer or add `tomli-w` as a dep. **Decision: use a small custom serializer** to avoid a new dep — config is a fixed-shape dataclass, serialization is straightforward (`[section]` headers + key=value pairs).

Provide `_dump_toml(config_dict: dict[str, Any]) -> str` as a module-private helper. It only needs to handle the shapes Config produces (strings, ints, bools, lists of strings, nested mappings one level deep). Reject anything else with a `TypeError` so future Config-shape changes fail loudly.

**`load_lockfile` / `save_lockfile`:** TOML again, with the same custom serializer + `tomllib` reader. Returns `None` if the lockfile doesn't exist (= first sync).

### C.5 Tests (`tests/unit/test_config.py`, `test_lockfile.py`, `test_sources_filesystem.py`)

`test_config.py`:
- `test_config_from_dict_minimal` — config with just `schema_version`, `project`, `engine` sections → all dataclass defaults applied.
- `test_config_roundtrip_full` — full config dict (all sections) → `from_dict` → `to_dict` → equal to input.
- `test_storage_section_absent_defaults_to_filesystem` — missing `[storage]` → both fields default to `"filesystem"`.

`test_lockfile.py`:
- `test_compute_hash_stable` — `compute_hash(b"hello")` returns a specific known sha256.
- `test_lockfile_roundtrip` — `Lockfile` → `to_dict` → `from_dict` → equal.
- `test_find_returns_entry` — populate entries, `find("path/x.md")` returns the matching `LockEntry`; `find("missing")` returns `None`.

`test_sources_filesystem.py`:
- `test_load_config_reads_primary_toml` — write a synthetic `.coding-agent-playbook.toml` in `tmp_path`, instantiate `FileSystemStateSource(repo_root=tmp_path)`, call `load_config()`, assert fields.
- `test_load_config_merges_local_overrides` — write primary + `.local.toml` with a `[user_choices]` override → merged config has the override applied.
- `test_load_config_missing_raises_fnf` — no toml file → `FileNotFoundError`.
- `test_save_config_emits_valid_toml` — call `save_config(Config(...))`, then `tomllib.load` the file and assert key contents.
- `test_save_then_load_roundtrip` — `save_config(c)` then `load_config()` returns an equal `Config`.
- `test_load_lockfile_missing_returns_none` — no file → `None`.
- `test_save_then_load_lockfile_roundtrip` — write, read, assert equal.
- `test_list_rules_walks_engine_package_resources` — install the package editable in the test env (already done by `uv sync`), call `list_rules()`, assert it returns the resources/rules/*.md files we ship. **Caveat:** v1 of the engine ships zero rules (PR 13 adds them). Until then, test via overlay-package injection (see next).
- `test_list_rules_includes_overlay_packages` — create a temp Python package under `tmp_path` with `resources/rules/foo.md`, add it to `sys.path`, instantiate `FileSystemArtifactSource(overlay_packages=["temp_overlay"])`, assert `foo` is in the returned list with `source_package="temp_overlay"`.
- `test_list_rules_includes_repo_local_playbook` — create `<repo_root>/playbook/rules/bar.md`, assert it's in the list with `source_package="<repo-local>"`.
- `test_list_prompts_walks_same_layout` — same as rules but `resources/prompts/`.
- `test_list_skills_constructs_from_directory` — synthesize `resources/skills/my-skill/SKILL.md.j2` + `scripts/` dir, assert `Skill` is built with the right paths.
- `test_list_eval_tasks_returns_empty_until_pr11` — placeholder behaviour.
- `test_entry_point_registers_filesystem_artifact_source` — `importlib.metadata.entry_points(group="coding_agent_playbook.artifact_sources")` includes `filesystem`, and loading it gives `FileSystemArtifactSource`.
- `test_entry_point_registers_filesystem_state_source` — same for `StateSource`.

### C.6 Track C tasks

Granular order so each commit is reviewable:

- [ ] **Task C.1 — `config.py` dataclass + tests**

Write `tests/unit/test_config.py` first (the three tests above). Run, watch fail (module missing). Write `src/coding_agent_playbook/config.py` with the dataclasses + `from_dict` / `to_dict`. Run pytest + mypy. Commit: `feat(config): Config dataclass mirroring .coding-agent-playbook.toml schema`.

- [ ] **Task C.2 — `lockfile.py` dataclass + tests**

Same pattern. Tests, fail, impl, pass, commit: `feat(lockfile): Lockfile + LockEntry dataclasses with sha256 hash helper`.

- [ ] **Task C.3 — `sources/filesystem.py` skeleton with stub methods**

Write skeleton with class definitions + method signatures raising `NotImplementedError`. Run mypy — must pass. Commit: `feat(sources): filesystem source skeleton (signatures only)`.

- [ ] **Task C.4 — TDD: load_config + save_config + roundtrip**

Tests (the four config-related test_sources_filesystem tests). Run, fail. Implement `load_config`, `save_config`, the `_deep_merge` helper, and the `_dump_toml` helper. Run pytest + mypy. Commit: `feat(sources): load and save config via TOML with .local.toml merge`.

- [ ] **Task C.5 — TDD: load_lockfile + save_lockfile**

Tests (the three lockfile-related test_sources_filesystem tests). Run, fail. Implement. Run pytest + mypy. Commit: `feat(sources): load and save lockfile via TOML`.

- [ ] **Task C.6 — TDD: list_rules across engine package + overlay + repo-local**

Three tests for rule discovery. Implement `list_rules` + the `_walk_rules` and `_iter_md_files` helpers. Run pytest + mypy. Commit: `feat(sources): list_rules walks engine + overlay packages + repo-local playbook`.

- [ ] **Task C.7 — TDD: list_prompts + list_skills**

Two tests (one per artifact type). Implement the methods (mostly factoring shared logic with list_rules into a generic `_walk_artifacts` helper). Commit: `feat(sources): list_prompts and list_skills walk same overlay layout`.

- [ ] **Task C.8 — Stub list_eval_tasks + corresponding test**

Empty-list test. Implement returning `[]`. Commit: `feat(sources): list_eval_tasks returns [] until PR 11 defines EvalTask`.

- [ ] **Task C.9 — Entry-point registration + tests**

Update `pyproject.toml`:

```toml
[project.entry-points."coding_agent_playbook.artifact_sources"]
filesystem = "coding_agent_playbook.sources.filesystem:FileSystemArtifactSource"

[project.entry-points."coding_agent_playbook.state_sources"]
filesystem = "coding_agent_playbook.sources.filesystem:FileSystemStateSource"
```

Re-install with `uv sync --all-extras` so entry points are re-discovered. Write the two entry-point tests. Run pytest + mypy. Commit: `feat(sources): register FileSystemArtifactSource and FileSystemStateSource via entry points`.

- [ ] **Task C.10 — Final track-C verification**

```bash
uv run pytest -v
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
```

All clean. Report DONE.

---

## Integration task — Dispatcher-owned

After all three subagents report DONE (and each track's spec-compliance + code-quality reviews pass), the dispatcher (the controller session, not a subagent) does the integration:

- [ ] **Step 1 — Create integration worktree**

```bash
# From the main checkout
git -C /Users/msobroza/Projects/coding-agent-playbook/coding-agent-playbook worktree add \
    .claude/worktrees/prA-integration prA-core-internals
cd /Users/msobroza/Projects/coding-agent-playbook/coding-agent-playbook/.claude/worktrees/prA-integration
```

The new branch `prA-core-internals` starts off origin/main.

- [ ] **Step 2 — Copy plan file into integration worktree**

```bash
cp /Users/msobroza/Projects/coding-agent-playbook/coding-agent-playbook/specs/prA-core-internals.md \
   specs/prA-core-internals.md
git add specs/prA-core-internals.md
git commit -m "docs: add PR A implementation plan"
```

- [ ] **Step 3 — Merge each subagent's branch in turn**

```bash
git merge --no-ff prA-detector \
    -m "Merge track A — detector module"
git merge --no-ff prA-renderer \
    -m "Merge track B — renderer module"
git merge --no-ff prA-sources \
    -m "Merge track C — filesystem sources + config + lockfile data types"
```

Three subagents touched zero overlapping files, so the merges should be clean. If a conflict surfaces, **STOP** and surface to the user — don't auto-resolve.

- [ ] **Step 4 — Re-sync venv (entry points changed in track C)**

```bash
rm -rf .venv
uv sync --all-extras
```

- [ ] **Step 5 — Final CI gate (matches `.github/workflows/ci.yml` exactly)**

```bash
uv run ruff check .                # must pass
uv run ruff format --check .       # must pass
uv run mypy                        # must pass (no args)
uv run pytest -q                   # must pass (no args)
uv run cap --version               # must echo "coding-agent-playbook <version>"
uv run coding-agent-playbook --version  # same
```

If anything fails, fix in the integration worktree (a single fix commit) — do NOT go back to a subagent.

- [ ] **Step 6 — User gate**

Surface the merged diff (`git diff origin/main..HEAD`), the test counts, the LoC totals, and any open Minor findings from the per-subagent code-quality reviews. Wait for explicit "go" before pushing.

- [ ] **Step 7 — Push + open PR (on user "go")**

```bash
git push -u origin prA-core-internals
gh pr create \
    --title "PR A — core engine internals (detector + renderer + filesystem sources)" \
    --base main \
    --body "<see template below>"
```

PR body template:

```markdown
Implements the three core internal modules that unblock every adapter (PRs 6–9):

- **Detector** (`src/coding_agent_playbook/detector.py`) — Facts inventory per SPEC §8: python version, package manager, frameworks, ml stack, dev tools, project kind. Plus `evaluate_predicate` for `applies_if` frontmatter (SPEC §6.4).
- **Renderer** (`src/coding_agent_playbook/renderer.py`) — Jinja2 environment with `StrictUndefined`, `.md` vs `.md.j2` extension dispatch, `rule()` helper plumbing, per-format post-processing for the six built-in formats (SPEC §9).
- **Filesystem sources** (`src/coding_agent_playbook/sources/filesystem.py` + `config.py` + `lockfile.py`) — `FileSystemArtifactSource` walking engine + overlay packages + repo-local `playbook/` directory; `FileSystemStateSource` reading + writing the three TOML files; `Config` and `Lockfile` dataclasses with TOML round-trip (SPEC §7, §14.4, §20.3).

## Coverage

- N new tests (M+N in `test_detector.py`, P in `test_renderer.py`, Q across `test_config.py`/`test_lockfile.py`/`test_sources_filesystem.py`)
- Full suite green: `pytest -q` + `ruff check .` + `ruff format --check .` + `mypy`
- 100% coverage on the three new modules; entry-point registration verified via `importlib.metadata`

## What still does NOT work after this PR

- `cap sync` still prints the deferred-implementation message — orchestration lands in PR 10 (the CLI).
- No adapters yet — PRs 6–9 will start consuming `detector.detect()` + `renderer.render_for()` + `FileSystemArtifactSource.list_rules()` to actually write `.continue/`, `.claude/`, `.opencode/`, and `AGENTS.md`.
```

---

## Self-review (filled in by the plan author)

**1. Spec coverage.**
- SPEC §8 (detector): Track A ✓
- SPEC §9 (renderer): Track B ✓
- SPEC §7 (config): Track C C.1 ✓
- SPEC §14.4 (lockfile): Track C C.2 ✓
- SPEC §20.3 (filesystem sources): Track C C.3–C.9 ✓

**2. Placeholder scan.** Every step has either exact code, exact test names, or exact commands. No TBD / TODO / "implement later".

**3. Type consistency.**
- `Facts` TypedDict (A.1) ↔ `Config.detector_cache` (C.1, `dict[str, Any]`) — consistent (cache is the dict shape Facts serializes to).
- `Rule.from_markdown(path, source_package)` signature matches what `FileSystemArtifactSource._walk_rules` calls in C.4.
- `RuleRegistry` Protocol (B.1) is what `render_for` accepts (B.1) and what PR 10 will implement when orchestrating sync.
- `Config.storage` → `StorageConfig.artifact_source` (str) — matches the entry-point discovery key in C.9.

**4. Parallel-safety.**
- Track A touches `detector.py` + `test_detector.py` only.
- Track B touches `renderer.py` + `test_renderer.py` only.
- Track C touches `config.py`, `lockfile.py`, `sources/filesystem.py`, `pyproject.toml` + three test files only.
- Zero overlap. Parallel-safe.

**5. What's deferred to later PRs.**
- The actual rule registry (used by `rule()` Jinja helper) — PR 10.
- Cleanup-stale default implementation in adapters — PR 6.
- `EvalTask` type and `cap eval --list` runner — PR 11.
- Adapter implementations consuming this code — PRs 6–9.
