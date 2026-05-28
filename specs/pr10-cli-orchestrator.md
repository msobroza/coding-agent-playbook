# PR 10 — CLI orchestrator

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Wire the engine together. After this PR, `cap sync` produces real output: detector → renderer → 4 adapters → lockfile. Plus `cap init`, `cap check`, `cap validate`, `cap render`, and a stub for `cap eval` (PR 11 finishes the eval surface).

**Architecture:** Single-track work — all changes are in the CLI layer plus a thin orchestrator module that composes the existing pieces (detector, renderer, sources, adapters from PRs A and B). No parallel tracks; one opus implementer with TDD per subcommand. The CLI surface is split into `cli.py` (argparse + dispatch) plus a `commands/` package with one module per subcommand for readability.

**Tech Stack:** Python 3.12+, stdlib `argparse` for command-line parsing, no new runtime deps.

---

## Context for the fresh subagent

Engine state after PR B (which just merged):
- **`detector.py`** (PR A) — `detect(repo_root) -> Facts` + `evaluate_predicate(predicate, facts, *, repo_root=None) -> bool`
- **`renderer.py`** (PR A) — `build_environment(...)`, `render_artifact_body(...)`, `render_for(template_path, body, fmt, *, frontmatter, rule_registry=None) -> str`, `RuleRegistry` Protocol
- **`sources/filesystem.py`** (PR A) — `FileSystemArtifactSource.list_rules/list_prompts/list_skills`, `FileSystemStateSource.load_config/save_config/load_lockfile/save_lockfile`
- **`config.py`** (PR A) — `Config`, `ProjectMeta`, `StorageConfig` dataclasses
- **`lockfile.py`** (PR A) — `Lockfile`, `LockEntry`, `compute_hash`
- **`adapters/base.py`** (PR B) — `Adapter` ABC with `_default_cleanup` + `_output_directories` hook
- **`adapters/continue_adapter.py`** (PR B) — `ContinueAdapter(*, rule_registry=None)`
- **`adapters/claude_code_adapter.py`** (PR B) — `ClaudeCodeAdapter(*, rule_registry=None)` with rule buffer + native skill support
- **`adapters/agents_md_adapter.py`** (PR B) — `AgentsMdAdapter` with rule buffer + custom single-file cleanup
- **`adapters/opencode_adapter.py`** (PR B) — `OpenCodeAdapter(*, rule_registry=None)`
- **`types.py`** (PR 2 + PR 0-fix + PR B) — `Rule`, `Prompt`, `Skill` dataclasses + `Skill.to_prompt`

The CLI today (`cli.py` ~54 lines) only ships `--version` and prints "deferred" messages for all subcommands. This PR replaces the stubs with the real orchestrator.

## Required reading

1. `SPEC.md` §12 (CLI contract, including example output for every subcommand) — the contract.
2. `SPEC.md` §4.2 (`cap sync` data flow) — the orchestration sequence.
3. `SPEC.md` §11 (three-layer overlay merge semantics) — how to resolve overlay overrides.
4. `SPEC.md` §6.2.5 (rule inclusion in prompts) — for the rule registry's `render_for_inclusion`.
5. `SPEC.md` §13.2 (pre-commit integration) — for `cap sync --check` semantics.
6. `CLAUDE.md` "Commit policy" and "Subagent / dispatcher policy" — non-negotiable rules.

## Repo conventions

- Python 3.12+, `uv run <tool>` locally. CI runs `mypy` and `pytest -q` with no args.
- All commits authored solely by `msobroza <max.raphael@gmail.com>` via the env-var pattern from PR B (set `GIT_AUTHOR_*` / `GIT_COMMITTER_*` once at session start).
- NEVER `Co-Authored-By:`, NEVER `--author`, NEVER `git config`, NEVER `git push`, NEVER `gh pr create` (dispatcher handles push/PR after the user gate).
- Stay on `pr10-cli` branch.

---

## File structure

| File | Responsibility |
| --- | --- |
| `src/coding_agent_playbook/cli.py` | argparse setup + subcommand dispatch. Slim — each subcommand is a separate module. |
| `src/coding_agent_playbook/orchestrator.py` | `SyncContext` (the data structure passed around the pipeline) + `build_rule_registry` (the live `RuleRegistry` implementation backed by the filtered, overlay-merged rule list) + `OverlayResolver` (computes the per-ID winner across engine + overlays + repo-local). |
| `src/coding_agent_playbook/commands/__init__.py` | empty package marker. |
| `src/coding_agent_playbook/commands/sync.py` | `cap sync` (write mode) and `cap sync --check` (verify-only). The workhorse. |
| `src/coding_agent_playbook/commands/init.py` | `cap init` interactive bootstrap. Supports `--non-interactive` with flag-based answers for CI. |
| `src/coding_agent_playbook/commands/check.py` | `cap check` diagnostic dump + `cap check --refresh`. |
| `src/coding_agent_playbook/commands/validate.py` | `cap validate` — all cross-reference checks (includes_rules, eval_tasks back-refs, Jinja syntax, applies_if facts). |
| `src/coding_agent_playbook/commands/render.py` | `cap render <id> --format X` + `--show-source` + `--show-rules`. |
| `src/coding_agent_playbook/commands/eval.py` | Stub: `cap eval --list/--show/<id>` prints a "PR 11 ships this" message. |
| `tests/cli/__init__.py` | empty marker. |
| `tests/cli/test_sync.py` | round-trip a synthetic repo through sync + verify lockfile content + check drift detection. |
| `tests/cli/test_init.py` | non-interactive mode with all flags → writes correct `.coding-agent-playbook.toml` + `.gitignore` + `.pre-commit-config.yaml`. |
| `tests/cli/test_check.py` | facts dump + `--refresh` writes updated detector cache. |
| `tests/cli/test_validate.py` | passes on a good repo; surfaces each documented error class. |
| `tests/cli/test_render.py` | render one rule to stdout in each format; `--show-source` shows path + overrides. |
| `tests/cli/test_eval_stub.py` | exit code 0 on all three subcommand variants; message references PR 11. |
| `tests/unit/test_orchestrator.py` | unit tests for `OverlayResolver` (engine + overlay + repo-local merge) + `RuleRegistryImpl` (filtered by facts). |
| `tests/conftest.py` | shared `make_synthetic_repo(tmp_path, **kwargs)` fixture for sync / check / validate tests. |

Total estimated LoC: **~800** (engine ~500 + tests ~300).

---

## Shared concepts the orchestrator implements

### `SyncContext`

Passed to every command that needs to load config + resolve artifacts + render:

```python
@dataclass
class SyncContext:
    repo_root: Path
    config: Config
    facts: Facts
    artifact_source: ArtifactSource
    state_source: StateSource
    adapters: dict[str, Adapter]      # name → instance, only the enabled ones
    rules_resolved: list[Rule]         # post-overlay-merge, NOT filtered by applies_if yet
    prompts_resolved: list[Prompt]
    skills_resolved: list[Skill]
```

Helper `SyncContext.from_repo(repo_root) -> SyncContext` walks the discovery: load config → instantiate the configured `ArtifactSource` + `StateSource` via entry points → resolve overlays → return the populated context. **No filtering** at this stage — filtering happens at sync time (when adapters consume artifacts).

### `OverlayResolver`

Three-layer merge per SPEC §11:

```python
class OverlayResolver:
    """Merge engine + overlay + repo-local artifact lists by ID.

    Resolution order (later wins on ID collision):
      1. Engine package artifacts (coding_agent_playbook.resources.rules/*)
      2. Each overlay package in config.overlays_enabled, in declared order
      3. Repo-local artifacts under <repo>/playbook/

    For each (kind, id) pair, the winning artifact is kept; the loser's source
    is recorded for `cap check`'s overlay-overrides display.
    """

    def resolve_rules(
        self,
        engine: list[Rule],
        overlays: list[list[Rule]],
        repo_local: list[Rule],
    ) -> list[Rule]: ...

    def resolve_prompts(self, ...) -> list[Prompt]: ...
    def resolve_skills(self, ...) -> list[Skill]: ...
    def collisions(self) -> list[Collision]: ...  # for `cap check` output
```

### `RuleRegistryImpl(RuleRegistry)`

The concrete `RuleRegistry` from the renderer Protocol. Built once per sync from the merged, applies_if-filtered rule list. `render_for_inclusion(rule_id, context)` returns the inlined rule body (with `### {rule.name}` header) or `""` if the rule is filtered out.

```python
class RuleRegistryImpl:
    def __init__(self, rules: list[Rule], facts: Facts, env: Environment) -> None:
        # rules is the post-overlay, post-filter list — only rules that pass applies_if
        self._by_id = {r.frontmatter.id: r for r in rules}
        self._facts = facts
        self._env = env

    def render_for_inclusion(self, rule_id: str, context: dict) -> str:
        rule = self._by_id.get(rule_id)
        if rule is None:
            return ""
        # Re-render the rule body if it's templated; prepend ### {name} header
        body = (
            render_string(rule.template_body, context, env=self._env)
            if rule.is_templated
            else rule.body
        )
        return f"### {rule.frontmatter.name}\n\n{body}"
```

### Adapter discovery via entry points

Don't instantiate adapters directly. Use `importlib.metadata.entry_points(group="coding_agent_playbook.adapters")` to discover available adapters, then filter by `config.adapters_enabled`. Always include `agents_md` regardless of config (SPEC §4.3 — "AGENTS.md is always generated").

```python
def discover_adapters(config: Config, *, rule_registry: RuleRegistry) -> dict[str, Adapter]:
    eps = metadata.entry_points(group="coding_agent_playbook.adapters")
    discovered: dict[str, Adapter] = {}
    for ep in eps:
        cls = ep.load()
        # Adapters that accept rule_registry get it; others (AGENTS.md) don't
        try:
            discovered[ep.name] = cls(rule_registry=rule_registry)
        except TypeError:
            discovered[ep.name] = cls()
    enabled = set(config.adapters_enabled) | {"agents_md"}
    return {name: adapter for name, adapter in discovered.items() if name in enabled}
```

---

## Tasks

### Task 1 — orchestrator scaffolding + tests

- [ ] **Step 1**: Set CWD + env vars + baseline:

```bash
cd /Users/msobroza/Projects/coding-agent-playbook/coding-agent-playbook/.claude/worktrees/pr10-cli && \
export GIT_AUTHOR_NAME="msobroza" GIT_AUTHOR_EMAIL="max.raphael@gmail.com" \
       GIT_COMMITTER_NAME="msobroza" GIT_COMMITTER_EMAIL="max.raphael@gmail.com" && \
pwd && git branch --show-current && git log --oneline -2 && \
uv sync --all-extras && uv run pytest -q 2>&1 | tail -3
```

Must show: branch = `pr10-cli`, HEAD = `c736b25 Merge pull request #6 from msobroza/prB-adapters`, baseline 245 tests passing. Otherwise STOP and report BLOCKED.

- [ ] **Step 2**: Create `src/coding_agent_playbook/orchestrator.py` with `SyncContext` dataclass, `OverlayResolver` class, `RuleRegistryImpl` class, `discover_adapters` function. Each gets a stub raising `NotImplementedError`.

- [ ] **Step 3**: Create `src/coding_agent_playbook/commands/__init__.py` (empty marker) and stub modules for `sync.py`, `init.py`, `check.py`, `validate.py`, `render.py`, `eval.py` — each exports a `run(args: argparse.Namespace) -> int` function that raises `NotImplementedError`.

- [ ] **Step 4**: Write `tests/unit/test_orchestrator.py` with TDD-style tests for `OverlayResolver` covering: only engine rules → returned as-is; overlay overrides an engine rule by ID → overlay wins; repo-local overrides everything; `collisions()` reports the losers. Run pytest, watch fail.

- [ ] **Step 5**: Implement `OverlayResolver` to pass the tests. Each pass-iterate as needed. Run pytest after each iteration.

- [ ] **Step 6**: Add tests for `RuleRegistryImpl`: present rule → returns formatted body; absent rule → returns `""`; templated rule re-renders against the context. Implement.

- [ ] **Step 7**: Add a single integration test for `SyncContext.from_repo` against a synthetic repo (using `tests/conftest.py`'s `make_synthetic_repo` fixture which you also create). Implement.

Commit when each chunk is green: `feat(orchestrator): OverlayResolver` / `feat(orchestrator): RuleRegistryImpl` / `feat(orchestrator): SyncContext + discover_adapters`.

### Task 2 — `cap sync` write mode

- [ ] **Step 1**: Write `tests/cli/test_sync.py` with the round-trip test (build synthetic repo with one rule + one prompt → run `sync` programmatically → assert `.continue/rules/...` exists, `AGENTS.md` exists, `.coding-agent-playbook.lock` exists with the right entries).

- [ ] **Step 2**: Implement `commands/sync.py::run(args)`:

```python
def run(args) -> int:
    repo_root = Path(args.repo_root or Path.cwd())
    ctx = SyncContext.from_repo(repo_root)

    # Filter applies_if
    rules = [r for r in ctx.rules_resolved if evaluate_predicate(r.frontmatter.applies_if, ctx.facts, repo_root=repo_root)]
    prompts = [p for p in ctx.prompts_resolved if evaluate_predicate(p.frontmatter.applies_if, ctx.facts, repo_root=repo_root)]
    skills = list(ctx.skills_resolved)  # skills are unconditional in v1

    # Build the renderer env + rule registry
    env = build_environment([], is_prompt_context=False)  # for rule re-render
    prompt_env = build_environment([], is_prompt_context=True, rule_registry=RuleRegistryImpl(rules, ctx.facts, env))

    # Render each artifact's body
    for rule in rules:
        if rule.is_templated:
            rule = dataclasses.replace(rule, body=render_string(rule.template_body, _build_context(ctx, env), env=env))
    # ... same for prompts and skills ...

    # Write via each enabled adapter
    written: set[Path] = set()
    for name, adapter in ctx.adapters.items():
        for rule in rules:
            written.update(p.resolve() for p in adapter.write_rule(rule, repo_root))
        for prompt in prompts:
            written.update(p.resolve() for p in adapter.write_prompt(prompt, repo_root))
        for skill in skills:
            written.update(p.resolve() for p in adapter.write_skill(skill, repo_root))
        written.update(p.resolve() for p in adapter.finalize(repo_root))

    # Cleanup stale
    removed: list[Path] = []
    for adapter in ctx.adapters.values():
        removed.extend(adapter.cleanup_stale(written, repo_root))

    # Lockfile
    lock = _build_lockfile(written, ctx.config.engine_version)
    ctx.state_source.save_lockfile(lock)

    # Summary
    print(f"Summary: {len(written)} files written, {len(removed)} removed")
    return 0
```

`_build_context(ctx, env)` produces the Jinja context per SPEC §9.4 (facts + project metadata + `has_framework` helper). `_build_lockfile(paths, engine_version)` reads each file, computes sha256, returns a `Lockfile`.

- [ ] **Step 3**: Make sync the default command (if user runs `cap` with no subcommand and isn't asking for `--help`, run `cap sync`). Actually — skip this; the existing CLI prints help on no-subcommand. Don't change that.

- [ ] **Step 4**: Run the test; iterate until green.

Commit: `feat(cli): cap sync writes artifacts via adapters and stamps lockfile`.

### Task 3 — `cap sync --check` (drift detection)

- [ ] **Step 1**: Add `--check` flag to the sync argparser. Test: run sync, then run `sync --check` → exit 0 (no drift). Then modify a file on disk → `sync --check` → exit 1, prints which file drifted.

- [ ] **Step 2**: Implement: in check mode, run sync to a temp dir (or render in memory) then compare each output's content against the on-disk file. If any differs OR is missing OR if a stale sentinel-tagged file would be removed, report drift and exit 1.

  Simpler implementation: run the normal sync to a temp tree (using a clone of the consumer repo), then `diff` against the consumer repo. Cleaner — no risk of mutating the consumer repo.

  Or: compute the lockfile that sync WOULD produce, compare entries against the existing on-disk lockfile + verify on-disk file hashes match the lockfile.

  Pick whichever is cleaner. Document the choice in the function's docstring.

Commit: `feat(cli): cap sync --check detects drift without writing`.

### Task 4 — `cap init`

- [ ] **Step 1**: Tests in `test_init.py`:
  - Non-interactive mode: `cap init --name X --kind python-application --description "..." --non-interactive` → creates `.coding-agent-playbook.toml` with the right fields, creates `.coding-agent-playbook.local.toml` (empty `[user_choices]`), appends to `.gitignore`, writes `.pre-commit-config.yaml`.
  - Interactive mode: simulate via `monkeypatch.setattr("builtins.input", ...)` providing canned answers in order. Verify the same files are created.
  - Idempotent: running init twice doesn't clobber a user-edited config (it preserves existing fields while merging in any new defaults).

- [ ] **Step 2**: Implement `commands/init.py::run(args)`:
  - If `--non-interactive`: read all answers from flags (name, kind, description, adapters, overlays, docstring_style, test_layout). Required flags are `--name` and `--kind`.
  - If interactive: prompt one question at a time via `input()`. Multi-select questions show numbered list, accept comma-separated indices.
  - Always: run the detector before writing so the cache section is populated.
  - Always: end with `cap sync` invocation to generate the first set of files.

  Pre-commit config template: use a heredoc string in code, with the engine binary and the project's pre-commit hook ID:

  ```yaml
  repos:
    - repo: local
      hooks:
        - id: coding-agent-playbook-sync
          name: coding-agent-playbook sync
          entry: cap sync --check
          language: system
          pass_filenames: false
          always_run: true
  ```

  If `.pre-commit-config.yaml` already exists, merge: append the new `repo` block if not present; otherwise no-op.

Commit: `feat(cli): cap init interactive bootstrap + non-interactive flags`.

### Task 5 — `cap check` + `cap check --refresh`

- [ ] **Step 1**: Test that `cap check` against the synthetic repo produces output containing:
  - `=== Environment ===` with python version + package manager + engine version
  - `=== Detected ===` with project_kind + frameworks + has_notebooks etc.
  - `=== Artifacts ===` with rules (applicable / total) + prompts (applicable / total)
  - `=== Drift ===` with "All on-disk files match" if no drift, or the drifted paths

- [ ] **Step 2**: Implement using `SyncContext.from_repo` + the same applies_if filter as sync, but without writing. Print formatted output to stdout. Use a hand-rolled formatter — no tabulate, no rich.

- [ ] **Step 3**: `--refresh` re-runs the detector and writes the new facts back to `.coding-agent-playbook.toml`'s `[detector.cache]` section. Test that the cache is updated.

Commit: `feat(cli): cap check diagnostic dump + --refresh writes updated facts`.

### Task 6 — `cap validate`

- [ ] **Step 1**: Tests for each documented error class in SPEC §12.6:
  - `applies_if` references unknown fact name → error
  - Prompt body calls `{{ rule("X") }}` but X not in `includes_rules:` → error
  - Rule template calls `{{ rule(...) }}` → error (rules can't include rules)
  - Orphan eval task (prompt_id points to non-existent prompt) → error
  - Prompt declares `eval_tasks: [foo]` but `eval_tasks/foo/` doesn't exist → error
  - Jinja template fails to compile → error
  - All frontmatter schema-valid → success

- [ ] **Step 2**: Implement `commands/validate.py`. Each check is a function returning a list of `ValidationError(path, message)`. Aggregate all errors before returning exit code.

  The eval-task checks reference `EvalTask`-shaped data that PR 11 will introduce. For PR 10, the eval checks can be partial: read the `eval_tasks/<id>/task.toml` files via `tomllib` and validate the `prompt_id` field manually, without instantiating a full `EvalTask` dataclass. PR 11 will refactor this to use the canonical type.

Commit: `feat(cli): cap validate runs all cross-reference checks`.

### Task 7 — `cap render`

- [ ] **Step 1**: Tests:
  - `cap render python-typing --format continue` → prints the Continue-shape file content to stdout
  - `cap render generate-tests --format prompt_continue` → prints the prompt rendering
  - `cap render python-typing --show-source` → prints template path + overrides
  - `cap render generate-tests --show-rules` → prints the resolved rule inclusion list
  - Unknown id → exit 1 with "no artifact matching id"
  - Unknown format → exit 1 with the valid format list

- [ ] **Step 2**: Implement. Find artifact by id across rules/prompts/skills; call `render_for(...)` with the chosen format; print to stdout.

  `--show-source` traces back through the OverlayResolver to report which sources contributed and which won.

  `--show-rules` walks the prompt's `includes_rules:` list and reports each as INLINED / OMITTED based on `applies_if` filtering.

Commit: `feat(cli): cap render with --format / --show-source / --show-rules`.

### Task 8 — `cap eval` stub (PR 11 finishes it)

- [ ] **Step 1**: Tests:
  - `cap eval --list` → exit 0, prints "PR 11 ships the read-only eval enumeration"
  - `cap eval --show foo` → same
  - `cap eval foo` → same, exit 0 (not 1 — eval task itself is fine, runner is just absent)

- [ ] **Step 2**: Implement as a trivial stub. Reference SPEC §6.5.6's "what runs in v1" table in the deferred message.

Commit: `feat(cli): cap eval stub printing PR-11 deferral message`.

### Task 9 — wire it all up + dispatch

- [ ] **Step 1**: Rewrite `cli.py` to:
  - Replace the `_DEFERRED_SUBCOMMANDS` loop with explicit subparsers per command, each importing its module and registering `subparser.set_defaults(func=module.run)`.
  - Each subcommand gets its own argparse flags (e.g. `sync` gets `--check` and `--repo-root`; `init` gets `--name` / `--kind` / `--non-interactive` etc.; `render` gets `--format`, `--show-source`, `--show-rules`).
  - `main(argv)` parses args, calls `args.func(args)` if present, else `parser.print_help()`.

- [ ] **Step 2**: Update existing `tests/unit/test_cli.py`:
  - The "unimplemented subcommand prints deferred message" test → replace with one test per command verifying its argparser accepts the expected flags.
  - Keep `--version` test.
  - Keep no-args / help-prints test.

Commit: `feat(cli): wire all subcommands into argparse dispatcher`.

### Task 10 — Final verification + manual smoke test

- [ ] **Step 1**: Full CI gates locally (matches `.github/workflows/ci.yml`):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q
uv run cap --version
uv run coding-agent-playbook --version
```

All clean.

- [ ] **Step 2**: Manual smoke test — create a synthetic consumer repo in a tmp dir:

```bash
TMPREPO=$(mktemp -d)
cd $TMPREPO
cat > pyproject.toml <<EOF
[project]
name = "smoke-test-repo"
requires-python = ">=3.12"
dependencies = ["fastapi", "pydantic"]
EOF
cap init --name smoke-test --kind python-application --non-interactive
ls -la .continue/ .claude/ .opencode/ AGENTS.md .coding-agent-playbook.toml
cap sync
cap check
cap validate
```

Verify no exceptions, all subcommands produce reasonable output. The engine ships zero rules in v1 (PR 13 adds them), so the generated `.continue/rules/` etc. will be empty — that's fine; the smoke test confirms the pipeline runs end-to-end without errors.

Document any rough edges (e.g. "init prints `Wrote 0 files via continue adapter` since engine has no rules — that's expected pre-PR-13") in the final report.

Commit: nothing for Step 2 (manual test only).

---

## Self-review

**Spec coverage:**
- SPEC §12.1 `cap init` → Task 4 ✓
- SPEC §12.2 `cap sync` → Task 2 ✓
- SPEC §12.3 `cap sync --check` → Task 3 ✓
- SPEC §12.4 `cap check` → Task 5 ✓
- SPEC §12.5 `cap check --refresh` → Task 5 ✓
- SPEC §12.6 `cap validate` → Task 6 ✓
- SPEC §12.7 `cap render` → Task 7 ✓
- SPEC §12.8 `cap eval` (stub) → Task 8 (full impl is PR 11)
- SPEC §4.2 sync data flow → Task 2 implements steps 1-8 of the flow
- SPEC §11 three-layer overlay → Task 1's `OverlayResolver`

**Type consistency:**
- `SyncContext` fields all use already-existing types (`Config`, `Facts`, `ArtifactSource`, `StateSource`, `Adapter`, `Rule`, `Prompt`, `Skill`).
- `RuleRegistryImpl` implements the `RuleRegistry` Protocol from `renderer.py`.
- `discover_adapters` returns `dict[str, Adapter]` — same shape adapters were typed with throughout PR B.

**Single-track justification:**
PR 10 is sequential because each subcommand depends on the shared `SyncContext` infrastructure built in Task 1. Subcommands also conceptually layer (init calls sync at the end; check is sync-but-read-only; sync --check is sync-but-read-only-with-drift-detection; validate is config validation only). Splitting across tracks would create coordination overhead that exceeds the parallelism benefit for a ~500-LoC engine module.

**What's deferred to PR 11:**
- Real `EvalTask` dataclass (currently `cap validate` reads task.toml files manually).
- `cap eval --list/--show/<id>` (currently a stub).
