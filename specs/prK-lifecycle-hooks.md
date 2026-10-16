# PR K — Lifecycle hooks (part 1): canonical Hook artifact, playbook-hook runtime, adapters

> **Resolves SPEC §19 Q8** (OpenCode plugin generation): the engine ships one generated OpenCode plugin shim that delegates to the same dispatcher as Claude Code, not hook *patterns* in docs. **Amends** §2.2 (the "no OpenCode plugins" non-goal narrows to *user-authored* plugins — the engine owns exactly one generated plugin file), §2.3 (the "OpenCode plugin generation from canonical hook descriptions" aspiration is delivered), §3 (**Hook** becomes the 4th emitted canonical kind; the "supported by … Continue CLI" claim is corrected — see P5), §10.6.2 (the hook gap is closed for the OpenCode V1 plugin API) and §17.1 (HTTP hook handlers are *rejected by `playbook validate`*, not merely "not shipped"). **Partially answers** §19 Q1 for executable overlay content (`allow_code_from` + trust-on-first-use, §B.4). The `Metric`/`Check`/`Rubric` engine (§21, `specs/prR6-check-rubric.md`) is reused unchanged by the new tools; no evaluator abstraction changes.
>
> **Layout note (SPEC v0.19, PR C; `content/` renamed `catalog/` in v0.20).** This design predates the move of the engine's content out of the Python package. The engine's `src/coding_agent_playbook/resources/{rules,prompts,eval_tasks,hooks}/` now live in `catalog/core/{rules,prompts,eval_tasks,hooks}/`, the hook shim templates (`resources/hook_shims/`) in the package's `src/coding_agent_playbook/templates/hook_shims/`, and the bundled packs (`coding_agent_playbook.packs.<name>`) are bundled plugins under `catalog/plugins/<name>/` (`coding_agent_playbook.plugins.<name>`). Overlay packages keep `<pkg>/resources/…`. Older paths in the track file lists below read through this mapping; SPEC.md is authoritative.
>
> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development; checkbox steps.
>
> **Commit policy (overrides any tooling default):** commits authored **solely by `msobroza`** — no `Co-Authored-By`, no `--author`, no signing, no `git config` edits. Subagents `cd <worktree>` as their first tool call, default `opus`, **no `git push` / `gh pr create` until the user gate approves the diff**. Run the **full cache-free, no-optional-extras CI-parity gate** (`uv pip uninstall radon -y; rm -rf .mypy_cache; ruff check . && ruff format --check . && mypy && pytest -q`, no path args; invoke as `uv run python -m mypy` / `uv run python -m pytest -q` per CLAUDE.md) before claiming green — see [[ci-parity-gate-pitfalls]].

Section letters are shared across the two parts: §P, §A–§D, §G–§K live in [part 1](prK-lifecycle-hooks.md); §E, §F, Tracks K5–K10 and Appendix R live in [part 2](prK-hook-pack.md).

## Contents

1. [Goal](#goal)
2. [Context for fresh subagents](#context-for-fresh-subagents)
3. [§P — Prerequisites (Track P, lands first)](#p--prerequisites-track-p-lands-first) — [P1](#p1--sandboxed-jinja-environment) · [P2](#p2--sync---check-reports-orphans-hygienic-scratch-copy) · [P3](#p3--one-sentinel-string-importable-without-jinja) · [P4](#p4--lockfile-schema-v2-provenance-on-every-entry) · [P5](#p5--correct-the-specs-continue-hook-claims) · [P6](#p6--config-preserves-extension-tables-saves-never-persist-localtoml) · [P7](#p7--one-secret_path_globs-wired-into-the-detector) · [P8](#p8--config-less-playbook-validate-validate-gated-playbook-sync) · [P9](#p9--keep-ruff-away-from-eval-fixtures)
4. [§A — The canonical Hook artifact](#a--the-canonical-hook-artifact) — [A.1](#a1-authoring-layout-decision-directory-form-only) · [A.2](#a2-frontmatter-schema) · [A.3](#a3-dataclasses-typespy-new-additions) · [A.4](#a4-markdown-round-trip-contract-spec-663) · [A.5](#a5-discovery--artifactsourcelist_hooks) · [A.6](#a6-overlay-merge--overlayresolverresolve_hooks-and-the-additive-policy) · [A.7](#a7-applies_if-linked_rule-and-the-effective-view) · [A.8](#a8-degrade-path--body--advisory-text-l1) · [A.9](#a9-worked-example-1--engine-builtin-guard-generated-outputs) · [A.10](#a10-worked-example-2--overlay-external-command-bnp-sql-pii-columns) · [A.11](#a11-engine-touch-points-owned-by-this-section)
5. [§B — Configuration, trust and validation](#b--configuration-trust-and-validation) — [B.1](#b1-the-hooks-table-coding-agent-playbooktoml) · [B.2](#b2-kill-switches-and-escape-hatches) · [B.3](#b3-the-guardrails-table--policy-shared-with-off-workstation-twins) · [B.4](#b4-trust-model) · [B.5](#b5-the-hook-trust-contract--playbook-validate-rules-l6) · [B.6](#b6-lockfile-v2) · [B.7](#b7-open-questions-raised-by-a-and-b)
6. [§C — Rendering hooks per harness (adapter contract)](#c--rendering-hooks-per-harness-adapter-contract) — [C.0](#c0-output-inventory-who-writes-what-and-how-ownership-is-proven) · [C.1](#c1-adapter-abc-change-and-sync-dispatch) · [C.2](#c2-claude-code-l4) · [C.3](#c3-opencode-v1-l5) · [C.4](#c4-advisory-degrade-agentsmd-continue-agent_harness) · [C.5](#c5-harness-support-matrix-and-incidental-reach) · [C.6](#c6-import-harness--validate-harness--manifest-round-trip) · [C.7](#c7-tests-for-this-section) · [C.8](#c8-open-questions-raised-by-c) · [C.9](#c9-spec-sections-amended-by-this-section)
7. [§D — The playbook-hook runtime](#d--the-playbook-hook-runtime) — [D.0](#d0-contract-with-c-launcher-pin-shim) · [D.1](#d1-packaging-and-launch) · [D.2](#d2-payload-normalization) · [D.3](#d3-decision-model) · [D.4](#d4-failure-policy) · [D.5](#d5-the-stop-coordinator) · [D.6](#d6-state-and-logs) · [D.7](#d7-escape-hatches-kill-switches-pragmas) · [D.8](#d8-guard_configjson) · [D.9](#d9-testability) · [D.10](#d10-locked-decisions-d) · [D.11](#d11-prerequisites-surfaced-by-d-add-to-the-prerequisite-track) · [D.12](#d12-open-questions-d)
8. [§G — Locked decisions](#g--locked-decisions) — [G.1](#g1-user-locks-as-resolved) · [G.2](#g2-spec-level-locks)
9. [§H — Tracks](#h--tracks) — [P](#track-p--prerequisites) · [K1](#track-k1--canonical-hook-artifact-sources-overlay-merge-config-validate) · [K2](#track-k2--hook_runtime-core) · [K3](#track-k3--adapter-contract-claude-code-rendering-advisory-degrade) · [K4](#track-k4--opencode-v1-shim) · [K11](#track-k11--docs-and-rollout); in part 2: [K5](prK-hook-pack.md#track-k5--pack-protect) · [K6](prK-hook-pack.md#track-k6--pack-verify-stop-coordinator-playbook-ci) · [K7](prK-hook-pack.md#track-k7--pack-feedback-and-the-shared-ruff-call) · [K8](prK-hook-pack.md#track-k8--pack-secrets-and-risky-actions) · [K9](prK-hook-pack.md#track-k9--pack-audit-and-overlay-mechanisms) · [K10](prK-hook-pack.md#track-k10--new-tools-coverage-quality-metrics-docstrings-commit-names)
10. [§I — Invariants this PR must honor](#i--invariants-this-pr-must-honor)
11. [§J — SPEC amendment table](#j--spec-amendment-table)
12. [§K — Open questions for the user (all resolved)](#k--open-questions-for-the-user-all-resolved)

In [part 2](prK-hook-pack.md): [§E — The standard hook pack](prK-hook-pack.md#e--the-standard-hook-pack) · [§F — New tools: coverage, quality metrics, docstrings, commit names](prK-hook-pack.md#f--new-tools-from-the-users-notes-coverage-deterministic-quality-metrics-docstrings-commit-names) · [§H (pack tracks): K5–K10](prK-hook-pack.md#h-pack-tracks) · [Appendix R — Rejected hooks](prK-hook-pack.md#appendix-r--rejected-hooks)

## Goal

Turn the playbook's practices from advice into enforcement where the harness allows it. Add a fourth emitted canonical kind, **`Hook`** — markdown + static YAML frontmatter, merged by id across engine → overlays → repo-local like every other kind — that binds lifecycle events to an in-engine **builtin** handler (or a trust-gated external command). Every hook executes through **one import-light dispatcher** (`playbook-hook`, module `coding_agent_playbook.hook_runtime`), registered once per harness event: a managed merge into `.claude/settings.json` for Claude Code and one generated plugin shim under `.opencode/plugins/` for OpenCode. Hookless outputs (AGENTS.md, Continue) receive each hook's body as labelled advisory text. Engine defects that hooks would inherit or amplify are fixed **first** (Track P).

Deliverables:

- **Track P — prerequisites** (§P): sandboxed Jinja, orphan-aware `sync --check`, one sentinel string, lockfile schema v2 with provenance, the SPEC §3 Continue correction, plus four verified enabling fixes (config-table preservation, one `SECRET_PATH_GLOBS`, validate-without-config + validate-gated sync, ruff exclusion of eval fixtures).
- **Canonical `Hook` kind** (§A): `Hook`/`HookFrontmatter`/`HookMatcher`/`HookHandler` in `types.py`, `HOOK.md` directory authoring, `ArtifactSource.list_hooks`, `OverlayResolver.resolve_hooks` with the additive overlay policy, `linked_rule` inheritance, the advisory degrade.
- **Configuration, trust and validation** (§B): the `[hooks]` table (+ `[guardrails]` policy domains), kill switches, the user-local trust store, the numbered hook trust contract enforced by `playbook validate`, and lockfile v2 ownership semantics.
- **Rendering** (§C): Claude Code managed merge into `.claude/settings.json` (ownership tracked in the lockfile, interpreter-pin design per L4); OpenCode V1 plugin shim (`.opencode/plugins/`, sentinel on line 1, throws on deny); the sync-level `guard_config.json`.
- **Runtime** (§D): `playbook-hook dispatch|simulate|doctor`, the `@register_hook_handler` registry + `coding_agent_playbook.hook_handlers` entry-point group, the single Stop coordinator, state and logs.
- **The standard hook pack** (§E, in [part 2](prK-hook-pack.md)): the 38 catalog hooks (27 `default`, 8 `opt-in`, 3 `overlay`); the 9 rejected entries are in Appendix R.
- **Four new tools** (§F, in [part 2](prK-hook-pack.md)), each usable from a hook **and** from an off-workstation twin (pre-commit stage and/or CI): test coverage, deterministic code-quality metrics, docstrings, commit-message naming. They add 3 tool hooks (`coverage-diff-gate`, `docstring-nonregression`, `commit-message-convention`), so the pack totals 38 catalog hooks + 3 tool hooks. Built on the existing `evaluators/` (`Metric` + `@register_metric` + `Normalizer`, `ThresholdCheck`/`NonRegressionCheck`, `playbook metrics --baseline git:HEAD [--run-tests]`, the `coverage`/`test_pass_rate` execution metrics) and on consumer-toolchain binaries (ruff, commitizen `cz`) per addendum D-Q1/D-Q2.
- **End matter** (§G–§K here; Appendix R in part 2): locked decisions, tracks with files and tests (the Track K5–K10 subsections are in part 2), invariants, the SPEC amendment table, and the single deduplicated open-question list.
- **Docs**: SPEC v0.15 (changelog + every section in the §J amendment table), README ("Pre-commit hooks" vs "Assistant lifecycle hooks"), and the CLAUDE.md invariants — subject to the harness-files policy question (§B.7 Q5). Bumping the SPEC header breaks `tests/unit/test_docs_check_rubric_refactor.py:114-115` (it asserts `| Version | 0.14 (draft) |` and `### v0.14`); the Docs track updates that test to assert `| Version | 0.15 (draft) |` and `### v0.15` while keeping the v0.14/v0.13/v0.12 changelog assertions, and runs the docs tests in the CI-parity gate. The same file scans the §21 body for deleted R6 symbols, so §21 amendments must not mention them bare.

## Context for fresh subagents

**What the engine is.** `coding-agent-playbook` renders one canonical source (rules, prompts, skills; eval tasks are authoring-only) into each assistant's native files. `playbook sync` = load config (`.coding-agent-playbook.toml` deep-merged with the gitignored `.local.toml`) → detect facts → list artifacts across three layers (engine `resources/`, overlay packages' `resources/`, repo-local `playbook/`) → resolve by id (later layer wins, full replace) → filter by `applies_if` → render bodies (Jinja only for `.md.j2`, frontmatter always static YAML) → dispatch to adapters (`write_*`, then `finalize`) → `cleanup_stale` → write `.coding-agent-playbook.lock`. Drift between source and committed output fails `playbook sync --check` (pre-commit + CI). Extension points are entry-point groups, never direct instantiation.

**Where to read** (in this order): CLAUDE.md (invariants; commit policy); SPEC §4.2 (data flow), §6.0–§6.6 (artifact model, `applies_if`, canonical types and round-trip), §7 (config), §10 (adapter ABC + adapters), §11 (overlays), §12.2–§12.7 (sync/check/validate/render), §14.4 (lockfile — stale, see P4), §17 (security), §20.2–§20.3 (sources), §21 (evaluators, reused by the tools). Source files this section touches: `types.py`, `_typing.py`, `config.py`, `lockfile.py`, `renderer.py`, `detector.py`, `orchestrator.py`, `sources/base.py`, `sources/filesystem.py`, `commands/{sync,validate,check,init,render}.py`, `adapters/base.py`. House style: `specs/prH-agent-harness.md`, `specs/prR6-check-rubric.md`.

**Harness facts this spec relies on** (verified against vendor docs/source on 2026-10-14; §C and §D carry the full tables):

| Harness | Hook surface | Facts that constrain the design |
| --- | --- | --- |
| Claude Code (CLI 2.1.296) | GA declarative hooks in `.claude/settings.json` (committed, shared with `permissions`/`env`/`model`) | Strict JSON — no comment channel, so no sentinel; command hooks get JSON on stdin; **only exit 2 / an explicit decision blocks** — crash, timeout or missing interpreter fail open (with a non-blocking "hook error" notice); `PreToolUse` decisions allow/deny/ask/defer (`defer` honoured only in `-p`) + `updatedInput` — the playbook emits only deny/ask; settings `env` keys reach hook processes; settings-file hook edits apply to the running session (no startup snapshot); Stop continuation cap 8; timeouts in seconds; `MultiEdit` is legacy, `NotebookEdit` is the notebook editor; `Glob`/`Grep` are absent by default on macOS/Linux (searches arrive as `Bash`); hook arrays merge across user/project/local/managed sources. |
| OpenCode V1 (`opencode-ai` 1.19.0) | In-process JS/TS plugins auto-discovered from `.opencode/plugins/*.{js,ts}` (also `.opencode/plugin/`) | No declarative hooks; a plugin blocks by throwing in `tool.execute.before`; **no ask primitive**; no hook timeout (the shim must enforce its own); tools `bash`/`edit`/`write`/`read`/`glob`/`grep`/`webfetch`/`websearch`, `apply_patch` replaces edit/write for GPT models, MCP tools are `<server>_<tool>`; PR #52765 (open, unmerged) is the reference Claude-shaped payload mapping. |
| Continue (IDE + `cn` CLI 1.5.47) | **None in practice** | CLI hook infrastructure merged (PR #11029) but never wired (PR #11043 closed unmerged); `fireHook.ts` is tree-shaken out of every published bundle; `config.yaml` has no hooks key; the repo is in maintenance-ended state. Continue gets the advisory degrade only. |

**Terminology (grep discipline).** "Hook" is overloaded in this repo: git **pre-commit hooks** (`.pre-commit-hooks.yaml`, `resources/precommit/`, README "Hooks"), the adapter "lifecycle hook" `finalize()`, and `HarnessRunner._invoke_agent` (the "per-assistant hook"). In this spec **Hook** means only an *assistant lifecycle hook*. The distinctive, grep-able names are: `Hook`, `HookFrontmatter`, `HookMatcher`, `HookHandler`, `HOOK.md`, `list_hooks`, `resolve_hooks`, `write_hook`, `hook_policy`, `hook_runtime`, `playbook-hook`, `guard_config.json`, `[hooks]`, `[guardrails]`.

---

## §P — Prerequisites (Track P, lands first)

Track P is pure engine hardening: no hook ships in it, every item is independently mergeable, and each also fixes a defect humans hit today (pre-commit, CI, `playbook check`). Items P1–P5 are locked decision L7; P6–P9 are **additional verified defects this spec adds to Track P** because a hook in the selected pack depends on them (flagged in §B.7 Q4 in case the user prefers to move them into the consuming track). The track lands as two PRs, Pa (P1–P5, P7) then Pb (P6, P8, P9, P-D1–P-D5); see §H Track P.

| # | Defect (verified) | Fix | Hooks that depend on it |
| --- | --- | --- | --- |
| P1 | Unsandboxed Jinja (`renderer.py:78`) | `SandboxedEnvironment` | validate-then-sync-on-canonical-edit, resync-on-detector-input-change, stop-drift-and-orphan-gate, guard-generated-outputs |
| P2 | `sync --check` discards orphans (`commands/sync.py:246`); scratch copy copies `.git`/`.venv`/secrets and dereferences symlinks (`:239`) | Report orphans; hygienic scratch copy | stop-drift-and-orphan-gate, stop-ci-parity-gate (T0), guard-generated-outputs |
| P3 | Sentinel wording mismatch (`renderer.py:43` vs SPEC §4.3 / CLAUDE.md:73) | Code string is canonical; import-light `_sentinel.py` | guard-generated-outputs, control-plane-guard, stop-drift-and-orphan-gate, the OpenCode shim |
| P4 | `LockEntry` has no provenance; whole-file ownership only (`lockfile.py:20-24`) | Lockfile schema v2 | guard-generated-outputs, control-plane-guard, stop-drift-and-orphan-gate, Claude Code managed merge |
| P5 | SPEC §3 / §17.1 claim Continue CLI hook support | Correct the SPEC | none (prevents a false-premise Continue track) |
| P6 | `Config` drops `[hooks]`/`[links]`/`[metrics]`; `init`/`check --refresh` persist `.local.toml` values (`config.py:42-94`, `commands/init.py:160-196`, `commands/check.py:158-169`) | Preserve extension tables; primary-only save | every hook configured via `[hooks]`/`[guardrails]`; the four tools via `[metrics]` |
| P7 | SPEC §17.3 "detector skips secret paths" is false (`detector.py:20-22`) | One `SECRET_PATH_GLOBS` in `security/patterns.py` | secrets-path-guard, secret-content-guard, stop-diff-sweep, exfil-channel-guard, sensitive-data-read-guard, P2 |
| P8 | `playbook validate` needs a consumer config (`commands/validate.py:377`); `sync` never validates (`commands/sync.py:194-211`) | Config-less validate; validate-gated sync | eval-task-authoring-lint, validate-then-sync-on-canonical-edit, the §B.5 trust contract |
| P9 | `ruff check .` / `ruff format` reach eval fixture `setup/` trees (no `[tool.ruff]` exclude; mypy excludes them at `pyproject.toml:150`) | `extend-exclude` + `force-exclude` | post-edit-ruff-format, stop-ci-parity-gate (T1), guard-eval-fixtures |

### P1 — Sandboxed Jinja environment

- **Defect.** `build_environment` (`renderer.py:62-115`) constructs a plain `jinja2.Environment` at `renderer.py:78`. Templates are author-controlled *and* agent-writable (`playbook/**/*.md.j2`, overlay `resources/`), and rendering runs inside `playbook sync`, `playbook render`, `playbook init`, the eval runner (`evals/runner.py:328`) and — once hooks exist — inside hooks with no permission prompt. Verified in the worktree venv (jinja2 3.1.6): `{{ lipsum.__globals__["os"].__name__ }}` renders `os` under the plain environment; `SandboxedEnvironment` raises `SecurityError`. `commands/validate.py:137` builds a second plain `Environment` (parse-only, so no execution, but two construction sites).
- **Fix.** `build_environment` returns `jinja2.sandbox.SandboxedEnvironment` with the same kwargs (`loader`, `autoescape=False`, `keep_trailing_newline`, `trim_blocks`, `lstrip_blocks`, `undefined=StrictUndefined`); the return annotation stays `Environment` (subclass). `_check_jinja_compiles` (`validate.py:135-163`) uses `SandboxedEnvironment` too. Not `ImmutableSandboxedEnvironment` (it additionally rejects in-template list/dict mutation, which the escape-to-`os` threat does not require and which could break authored templates). The sandbox does not bound CPU beyond Jinja's `MAX_RANGE`; hooks never render templates on the hot path (the dispatcher imports no Jinja, L3).
- **Tests.** `tests/unit/test_renderer.py::test_build_environment_is_sandboxed`; `::test_sandbox_blocks_globals_escape` (parametrized: `lipsum.__globals__`, `cycler.__init__.__globals__`, `''.__class__.__mro__`) → `jinja2.exceptions.SecurityError`; `tests/adapters/*` golden files unchanged (every shipped `.md.j2` renders byte-identical under the sandbox); `tests/cli/test_sync.py::test_sync_fails_loudly_on_sandbox_violation` (a repo-local rule body with the escape makes `playbook sync` exit non-zero naming the file, writes nothing).

### P2 — `sync --check` reports orphans; hygienic scratch copy

- **Defect.** `_run_check` (`commands/sync.py:219-276`) runs the full sync in a scratch copy, but `commands/sync.py:246` is `written, _ = _run_sync(scratch_ctx)`: the `removed` list (generated files that a real sync would delete as stale) is discarded, so an orphan — e.g. `.continue/rules/50-x.md` whose rule was deleted — passes `--check`; the comment at `:241-245` claims the opposite. The byte-compare loop (`:249-266`) only iterates `written`. Separately, `:239` `shutil.copytree(ctx.repo_root, scratch, symlinks=False)` copies `.git`, `.venv`, `node_modules` and caches (seconds on real repos — the Stop gate's default tiers must total ≤ 3 s), **dereferences** symlinks (an in-repo symlink to `~/.ssh` is copied into `/tmp`), and copies secret files (`.env`) into the temp tree.
- **Fix.** (a) `_run_check` reports every scratch-`removed` path as `"  <rel>\n    Orphaned generated file; run 'playbook sync' to remove."` and every **lockfile orphan** — a prior `LockEntry` (P4) not regenerated by the scratch sync whose file still exists — with the same wording; either makes the exit code 1. (The lockfile-orphan half needs P4's provenance-bearing entries; land P4 first or ship it in the same PR.) (b) The copy uses `ignore=` built from `detector._IGNORE_DIRS` ∪ `{".ruff_cache", ".pytest_cache", "dist", "build"}` ∪ `SECRET_PATH_GLOBS` (P7), and a symlink policy: a symlink whose real path is inside the repo is copied as its target content (current behaviour, so adapters never write *through* a link into the real tree); a symlink resolving outside the repo is skipped. Because the extra exclusions are detector inputs (`_has_notebooks`, `detector.py:243-249`, skips only `_IGNORE_DIRS`; `has_file` checks arbitrary paths), facts are computed **once on the real repo** and injected into the scratch context — `SyncContext.from_repo(scratch, facts=ctx.facts)` (NEW keyword) — so the scratch run can never select a different rule set. In-memory rendering (no scratch copy) is the long-term fix and out of scope (§K).
- **Tests.** `tests/cli/test_sync.py::test_check_reports_orphaned_generated_file` (sync, delete the repo-local rule, `--check` exits 1 naming `.continue/rules/…`); `::test_check_reports_lockfile_orphan_without_sentinel` (a skill script listed in the lockfile, skill removed); `::test_check_scratch_excludes_ignored_and_secret_paths` (spy the `ignore` callable: `.venv`, `.git`, `.env` excluded); `::test_check_skips_symlink_outside_repo` (POSIX-only, `pytest.mark.skipif(sys.platform == "win32")`); `::test_check_facts_not_flipped_by_scratch_exclusions` (a notebook under `build/` keeps `has_notebooks` true in the scratch run).
- **As landed (merge 6adc792 and its review fixes).** (b) is superseded: there is no copy. The merged-in main renders into an *empty* scratch dir and reads every input (config, facts, artifacts, `applies_if` file checks) from the real repo in place (`commands/sync.py::_rendered_scratch`), which meets the hygiene goal without `ignore=`, a symlink policy or `SyncContext.from_repo(scratch, facts=...)`. The only source bytes a render copies are skills' `scripts/`/`references/`, and those refuse secret paths and links leaving the skill (`adapters/_skill_sources.py`, SPEC §10.8/§17.3). (a) reports only the orphans write mode deletes — adapter `stale_outputs` (the read-only twin of `cleanup_stale`) plus the leftover policy's `plan.delete` — so a kept leftover (edited, tracked, adapter missing) is owned, not drift, and the hint stays true; not every lockfile orphan sets exit 1. The orphan scan never opens a symlink or a secret path and reads a bounded head. Replacement tests in `tests/cli/test_sync_check.py`: `test_check_never_copies_the_working_tree`, `test_check_survives_symlink_cycles_and_sockets`, `test_check_facts_come_from_the_real_repo` (plus `test_check_never_opens_a_secret_path`, `test_skill_secrets_and_escaping_links_are_never_copied`).

### P3 — One sentinel string, importable without Jinja

- **Defect.** `renderer.py:43` defines `SENTINEL = "AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync'"`, emitted as `<!-- {SENTINEL} -->` (`renderer.py:206`, `:276`, `:299`, `:338`; `adapters/claude_code_adapter.py:145`; `adapters/agents_md_adapter.py:90`; `harness/emitter.py:52`). SPEC §4.3 (`SPEC.md:142`) and CLAUDE.md:73 document `# AUTOGENERATED — edit in coding-agent-playbook, run 'playbook sync'`; the SPEC examples at `SPEC.md:418`, `:522`, `:1201`, `:1262` show a third form carrying `v0.4.0`. A guard anchored on the documented string never matches real output. Also, the hot-path dispatcher may not import `renderer.py` (it imports `yaml` and `jinja2` at module top, `renderer.py:13-14`).
- **Fix.** The **code string is canonical** (changing it would make every consumer's generated files drift on upgrade). (a) NEW `src/coding_agent_playbook/_sentinel.py` (zero imports) holds `SENTINEL`, `sentinel_line(style: Literal["html", "hash", "slash"]) -> str` (`<!-- … -->` for markdown; `# …` for engine-*generated* shell/YAML/TOML files such as the launcher; `// …` for the JS plugin shim) and `has_sentinel(text: str) -> bool`. **Engine-generated files never start with a shebang**: executables are invoked through an explicit interpreter (`sh launch.sh`, §C.2.7), so the sentinel is always on line 1, except the one documented second position — the first body line after a leading YAML frontmatter block (agent_harness output, §10.7.3, and Claude commands that carry frontmatter, §E.3). `has_sentinel` accepts exactly those two positions, and `adapters/base.py:94-97` `_default_cleanup`, `claude_code_adapter.py:206-209`, `opencode_adapter.py:125-128` and `agents_md_adapter.py:112-113` switch from their first-line check to it. Byte-copied hook scripts never receive a sentinel. `renderer.py` re-exports it (`from coding_agent_playbook._sentinel import SENTINEL`), so every existing import keeps working. JSON gets no sentinel — ownership is the lockfile's (§B.6). (b) SPEC §4.3, the four SPEC examples and CLAUDE.md:73 quote `renderer.SENTINEL` verbatim; §4.3 gains the explicit exception list (strict-JSON files, byte-copied scripts, `SKILL.md`) whose ownership is lockfile-tracked.
- **Tests.** `tests/unit/test_sentinel.py::test_renderer_reexports_sentinel` (identity); `::test_sentinel_module_is_import_light` (fresh interpreter via `subprocess.run([sys.executable, "-c", "import coding_agent_playbook._sentinel, sys; print('jinja2' in sys.modules, 'yaml' in sys.modules)"])` prints `False False`); `::test_sentinel_line_styles`; `::test_has_sentinel_positions` (line 1, or the first body line after frontmatter; never a substring elsewhere); `tests/adapters/test_cleanup.py::test_frontmatter_sentinel_file_is_cleaned` (NEW); `tests/unit/test_docs_sentinel.py::test_spec_quotes_code_sentinel` (SPEC.md contains `SENTINEL` verbatim and none of the two stale forms).
- **As landed.** `SKILL.md` is not an exception: native skill `SKILL.md` files carry the sentinel at the first-body-line position (SPEC §4.3, §10.8), like `agent_harness` output. The exceptions are byte-copied skill `scripts/`/`references/` and strict JSON. The scanners call `has_sentinel` through `Adapter._carries_sentinel`, which reads only the head that decides it.

### P4 — Lockfile schema v2: provenance on every entry

- **Defect.** `LockEntry` (`lockfile.py:20-24`) is `(path, sha256, bytes)`; `_LOCKFILE_SCHEMA = 1` (`commands/sync.py:35`); `_build_lockfile` (`commands/sync.py:93-118`) receives only paths. Consequences: guard-generated-outputs cannot name a generated file's canonical source without rendering (`playbook render --show-source` runs Jinja and costs ~0.5 s); files without a sentinel (`SKILL.md`, copied scripts) have no ownership record (the skill-cleanup gap in `adapters/claude_code_adapter.py:119-129`); whole-file hashing cannot represent the engine-owned subset of `.claude/settings.json`, so `playbook check`'s drift section (`commands/check.py:140-155`) would report every user edit to `permissions`/`env` as drift. SPEC §14.4 (`SPEC.md:1726-1739`) documents a `[file_hashes]` table and `[overlay_versions]` the code never writes.
- **Fix.** Schema 2, landed **once** in Track P with all fields defined (hook-only fields stay at defaults until tracks K3/K4 populate them) — full field table in §B.6. `Lockfile.from_dict` reads new keys with `.get(...)` defaults so v1 lockfiles load; an older engine reading v2 still loads (its `from_dict` picks only `path`/`sha256`/`bytes`). Provenance is recorded **without changing the adapter return type**: `_run_sync` wraps each `write_rule/write_prompt/write_skill/write_hook(artifact)` call and maps every returned path to `Provenance(kind, artifact_id, source, adapter)` (NEW dataclass in `lockfile.py`); a path returned by `finalize` or by two different artifacts is `kind="composite"`. `_run_sync` returns one NEW frozen `SyncResult(written, removed, provenance, managed)` (shared name — proposed) instead of today's `(written, removed)` tuple, and the single signature `_build_lockfile(written, repo_root, engine_version, provenance, managed)` writes whole-file entries plus the scoped `managed` entries of §C.1.4. The existing caller `_run_check` (`commands/sync.py:246`) is updated in the same track. SPEC §14.4 is rewritten to the real `[[entries]]` shape.
- **Tests.** `tests/unit/test_lockfile.py::test_v1_lockfile_loads_with_defaults`; `::test_v2_roundtrip_all_fields`; `::test_default_valued_fields_omitted_from_toml`; `tests/cli/test_sync.py::test_lockfile_records_rule_provenance` (`.continue/rules/…` → `kind="rule"`, `artifact_id`, `source="coding_agent_playbook"`, `adapter="continue"`); `::test_claude_md_is_composite`.
- **As landed.** The builder is `build_lockfile(written, repo_root, engine_version, *, provenance, managed=(), carried=())` in `commands/_sync_lockfile.py` (keyword-only provenance; `carried` holds the leftovers the policy keeps owning), not the 5-positional `_build_lockfile` above.

### P5 — Correct the SPEC's Continue hook claims

- **Defect.** SPEC §3 (`SPEC.md:66`): lifecycle hooks are "supported by Claude Code and Continue CLI". SPEC §17.1 (`SPEC.md:1911`): "The Claude Code / Continue CLI HTTP hook type is supported by the adapter API". Refuted: Continue's CLI hook code is dormant in every published bundle (1.5.45–1.5.47; wiring PR #11043 closed unmerged; no docs page ever existed), the IDE `config.yaml` has no hooks key, and the project is maintenance-ended. The "adapter API" clause is also false — `adapters/base.py` has no hook method today.
- **Fix.** §3 Hook entry: "supported natively by Claude Code, by OpenCode through JS plugins; Continue ships no wired hook mechanism (the CLI's hook code is unreachable), so Continue receives the advisory degrade only (§A.8)." §17.1: "HTTP hook handlers are not expressible in the canonical `Hook` schema and are rejected by `playbook validate` (§B.5 H8)." §10.2 gains "Hooks: none — advisory degrade only."
- **Tests.** Doc-only in Track P. The Continue adapter track adds `tests/adapters/test_continue.py::test_hooks_never_write_continue_hook_config` (no `.continue/settings.json`, no `hooks` key anywhere under `.continue/`).

### P6 — Config preserves extension tables; saves never persist `.local.toml`

- **Defect.** `Config.from_dict`/`to_dict` (`config.py:42-94`) model only known keys, so `[hooks]`, `[guardrails]`, `[links]` and `[metrics]` are silently deleted whenever `playbook init` re-runs on an existing config (`commands/init.py:160-196`, whose comment at `:161-163` claims unknown fields are preserved) or `playbook check --refresh` saves (`commands/check.py:158-169`). Both writers start from `FileSystemStateSource.load_config()`, which deep-merges `.local.toml` (`sources/filesystem.py:351-355`), so they also bake personal overrides into the committed file. `_dump_toml` raises on nesting deeper than two levels (`sources/filesystem.py:129-133`) and on lists of tables below the top level.
- **Fix.** `Config` gains `extra_tables: dict[str, Any]` (every top-level key it does not model, verbatim) round-tripped by `from_dict`/`to_dict`. `_dump_toml` renders values nested deeper than two levels, and lists of tables below the top level, as inline tables via `_toml.format_scalar(allow_inline_table=True)` instead of raising. `_toml.format_scalar` (`_toml.py:59-104`) supports only `bool`/`int`/`str`/`list`/`dict` today, so preserving `[metrics]` verbatim would turn every float (`max_worsening = 0.5`, `[metrics.weights] x = 1.0`, the 0–1 thresholds) into a `TypeError` on the next `init` re-run or `check --refresh`; P6 therefore also adds a `float` branch (`repr`, rejecting `inf`/`nan` with a `TypeError` naming the value) and `datetime.date`/`datetime.datetime` branches (TOML local date / offset datetime), used by both `_format_toml_scalar` and the inline-table path. NEW `FileSystemStateSource.load_primary_config()` (no local merge) is what `init` and `check --refresh` load before `save_config`. `parse_hooks_config` / `parse_guardrails_config` (NEW, `config.py`, modelled on `parse_links_config` at `config.py:167-185`) read the *merged* data with the `.local.toml` exclusion rule of §B.1.
- **Tests.** `tests/unit/test_config.py::test_extra_tables_roundtrip`; `::test_metrics_table_roundtrip` (a realistic `[metrics]` with thresholds, regression and weights through `Config.to_dict` → `_dump_toml` → `tomllib`); `tests/unit/test_toml.py::test_format_scalar_float`, `::test_format_scalar_rejects_nan_inf`, `::test_format_scalar_date`; `tests/unit/test_sources_filesystem.py::test_dump_toml_inline_tables_beyond_depth_two`; `tests/cli/test_init.py::test_init_rerun_preserves_hooks_guardrails_links_metrics`; `tests/cli/test_check.py::test_refresh_preserves_tables_and_never_persists_local_overrides`.

### P7 — One `SECRET_PATH_GLOBS`, wired into the detector

- **Defect.** SPEC §17.3 (`SPEC.md:1915-1917`) says the engine never reads `.env*`, `*.pem`, `*.key`, `*credentials*` and that the detector skips them. `detector.py:20-22` `_IGNORE_DIRS` holds only directory names; no secret glob exists anywhere in `src/`.
- **Fix.** NEW `src/coding_agent_playbook/security/patterns.py` (stdlib-only, import-light; the `security` package is on the dispatcher's import allow-list, §D.1, and is the **only** home of these constants — §D.8.2 and §E.4 reference it, nothing duplicates it): `SECRET_PATH_GLOBS: Final[tuple[str, ...]]` (the catalog list: SPEC §17.3's `.env*`, `*.pem`, `*.key`, `*credentials*` — the last restricted to non-code extensions so `credentials.py` passes; `*.p12`, `*.pfx`, `*.jks`, `*.keystore`, `id_rsa*`/`id_ed25519*` (not `.pub`); `.netrc`, `.pypirc`, `.npmrc`, `pip.conf`, `uv.toml`, `.git-credentials`, `.vault-token`, `krb5cc_*`; `*.tfstate`, `*.tfvars`, `*.kdbx`; the user-home set `~/.aws/**`, `~/.ssh/**`, `~/.kube/config`, `~/.config/gcloud/**`, `~/.config/gh/hosts.yml`, `~/.docker/config.json`, `~/.m2/settings.xml`, `~/.claude/.credentials.json`; exempt `.env.example/.sample/.template/.dist`), plus `SECRET_PATH_EXEMPT`; the predicate `is_secret_path(path: str, *, home: Path) -> bool` lives beside `PathPolicy` in `security/paths.py` (§E.4). The detector's filesystem walks skip matches; P2's scratch copy ignores them; sync serializes the tuple into `guard_config.json` (§D.8.2); overlays and consumers may only **extend** it (`[guardrails.secrets] extra_globs`, §B.3).
- **Tests.** `tests/security/test_patterns.py` (parametrized match/no-match table, incl. `.env.example` not secret, case-folding on darwin/win32 via an injected `platform` parameter); `tests/unit/test_detector.py::test_detector_never_opens_secret_paths` (spy `Path.open`/`Path.read_text`).

### P8 — Config-less `playbook validate`; validate-gated `playbook sync`

- **Defect.** `validate.run` builds `SyncContext.from_repo(repo_root)` (`commands/validate.py:377`), whose `load_config` raises `FileNotFoundError("missing .coding-agent-playbook.toml; run playbook init")` (`sources/filesystem.py:347-348`) in an engine or overlay checkout — overlay authors cannot validate their hooks, and eval-task-authoring-lint cannot run in the engine repo. `execute` (`commands/sync.py:194-211`) never validates, so a hook violating the trust contract (§B.5) would be rendered.
- **Fix.** (a) With no consumer config, `validate` builds a default context that validates the engine package, the checkout's own `<root>/src/*/resources/` when present (an overlay checkout), and `<root>/playbook/` if present; consumer-only rules (H16, H21) are skipped and reported as skipped. Installed overlays are **not** discovered: the `coding_agent_playbook.overlays` group (`pyproject.toml:58`) is declared but never consumed in `src/` (overlays resolve by package name from `overlays_enabled`, `orchestrator.py:257-260`), and its entry-point value shape is undefined, so config-less validate does not invent one. (b) The validate rule set is factored into `collect_validation_errors(ctx) -> list[ValidationError]` (NEW, `commands/validate.py`); `sync` (write and `--check`) calls it first and exits 1 printing the errors, writing nothing. (c) **Malformed hooks never become a traceback.** `SyncContext.from_repo` gains `tolerate_hook_errors: bool = False`; `validate` passes `True`, and `list_hooks` then records each `HookSchemaError` in `ctx.hook_load_errors` (one per hook directory) instead of raising, so `_check_hooks` reports `FAIL <path>: <message>` lines and keeps aggregating. Sync and eval keep the fail-loudly default.
- **Tests.** `tests/cli/test_validate.py::test_validate_without_config_checks_engine_resources`; `::test_malformed_hook_reports_fail_line_not_traceback`; `tests/cli/test_sync.py::test_sync_aborts_on_validate_error_and_writes_nothing`; `::test_sync_check_aborts_on_validate_error`.

### P9 — Keep ruff away from eval fixtures

- **Defect.** mypy excludes `resources/eval_tasks/.*/setup/` (`pyproject.toml:150`) because those trees are deliberately unclean needle material, but `[tool.ruff]` (`pyproject.toml:111`) has no exclude: a post-edit `ruff format` or a Stop-tier `ruff check --fix` would rewrite fixtures (the `find-injected-vuln-*` needles included).
- **Fix.** `[tool.ruff] extend-exclude = ["src/coding_agent_playbook/resources/eval_tasks/*/setup"]` **and** `force-exclude = true` (engine repo only; consumers are unaffected). Verified with ruff 0.15.10: `extend-exclude` is not applied to an explicitly passed path unless `force-exclude` is set, and the post-edit hooks and Stop stages pass explicit paths. Every hook and stage ruff argv also carries `--force-exclude` (§E.3), so consumer excludes hold without their own `force-exclude`.
- **Tests.** `tests/integration/test_ruff_scope.py::test_ruff_excludes_eval_fixture_setup` (parse `pyproject.toml`, assert the glob and `force-exclude`; when `ruff` is on PATH, run `ruff check --force-exclude <a fixture file>` and assert "No Python files found", else skip).
- **Since v0.20.** Eval tasks are per layer, so the excludes are `catalog/core/eval_tasks/*/setup` and `catalog/plugins/*/eval_tasks/*/setup`: a bundled plugin may ship `eval_tasks/`, each task using its own layer's `prompts/`. mypy needs no exclude, because `catalog/` is outside its `files`. `test_ruff_scope.py` also runs ruff on a plugin fixture in a scratch project that carries the engine's ruff table.

---

## §A — The canonical Hook artifact

### A.1 Authoring layout (decision: directory form only)

A hook is a **directory containing `HOOK.md` or `HOOK.md.j2`** (shared name — proposed), with an optional `scripts/` subdirectory for the external-command form. The directory name **is** the hook id. Category folders above hook directories are allowed and carry no meaning:

```
catalog/core/hooks/                                   # engine (builtin handlers only)
├── protect/
│   ├── guard-generated-outputs/HOOK.md
│   └── control-plane-guard/HOOK.md
├── verify/stop-ci-parity-gate/HOOK.md
└── ...
<overlay_pkg>/resources/hooks/<category>/<id>/HOOK.md  # overlay layer
catalog/plugins/<name>/hooks/<category>/<id>/HOOK.md   # bundled-plugin layer (an overlay)
<repo>/playbook/hooks/<id>/                            # repo-local layer
├── HOOK.md
└── scripts/
    └── check_names.py
```

| Option | Verdict |
| --- | --- |
| Single file `hooks/<id>.md` | Rejected. Hooks discovered via `_walk_artifacts`/`_iter_md_files` (`sources/filesystem.py:162-173`, `rglob("*.md*")`) would parse any `scripts/README.md` as a hook and `split_frontmatter` would raise; and two layouts (file vs dir) double the discovery and validate surface. |
| Flat one-level directories (skills' `_iter_skills`, `sources/filesystem.py:176-197`) | Rejected for the engine: 38 shipped hooks need the five categories (protect / verify / feedback / safety / audit) to stay navigable. |
| **Directory with a `HOOK.md` marker, found at any depth** | **Chosen.** Mirrors skills (`SKILL.md` + `scripts/`), keeps scripts out of artifact parsing, allows categories, and the marker is grep-able. A `HOOK.md` beneath another hook directory is a validate error (H2). |

Scripts are **never templated** (bash `${#arr[@]}` contains `{#`, a Jinja comment opener) and never get a sentinel injected (byte copies, L8 copies-not-symlinks). Engine-shipped hooks are builtin-only and carry no `scripts/` (H13): engine Python lives in `src/`, under the CI-parity gate, not in `resources/`.

### A.2 Frontmatter schema

`HookFrontmatter` (static YAML, parsed before Jinja; unknown keys are an error, H1):

| Field | Type | Req. | Default | Semantics |
| --- | --- | --- | --- | --- |
| `id` | `str` | yes | — | `^[a-z0-9][a-z0-9-]{0,62}$`; equals the hook directory name; the overlay-merge key. |
| `name` | `str` | yes | — | Human-readable; heads the advisory text. |
| `description` | `str` | yes | — | One line; shown by `playbook check`, `playbook-hook doctor`. |
| `version` | `int` | no | `1` | Bump on a breaking behaviour change (§6.1.1 convention). |
| `tier` | `default` \| `opt-in` \| `overlay` | yes | — | Default posture (§B.1 on-formula). `overlay` is reserved for **engine-shipped** mechanisms an overlay activates (H12). |
| `enabled` | `bool` | no | `true` | Definition-level switch; `false` makes the definition inert regardless of config. |
| `mandatory` | `bool` | no | `false` | (shared name — proposed) Overlay-only: cannot be disabled by `[hooks] disable` or shadowed by a repo-local same-id override (H15). |
| `events` | `list[HookEvent]` | yes | — | Non-empty, unique, canonical names (table below). |
| `matcher` | `dict[HookEvent, HookMatcher]` | no | `{}` | Keys ⊆ `events`; an event without an entry matches every occurrence. Evaluated **in-process by the dispatcher**; the harness registration matcher is only a union pre-filter. |
| `priority` | `int` | no | `50` | (shared name — proposed; same meaning as `RuleFrontmatter.priority`) Fan-out order within an event: the dispatcher orders selected hooks by `(class rank, priority, id)` (§D.3.2). It does **not** order Stop stages — that is the engine constant `STOP_STAGE_ORDER` (§E.0.4). |
| `handler` | `HookHandler` | one of `handler`/`handlers` | — | The handler for every declared event: builtin or external command (table below). |
| `handlers` | `dict[HookEvent, HookHandler]` | one of `handler`/`handlers` | `{}` | (shared name — proposed) Per-event handlers for hooks with a companion on a second event (e.g. gate-weakening-guard: `stop` stage + `pre_tool_use` companion). Keys = `events` exactly; mutually exclusive with `handler` (H6). |
| `decisions` | `list[HookDecision]` | yes | — | (shared name — proposed) The **only** decisions this hook may emit, ⊆ `deny` \| `ask` \| `context` \| `none`; `allow` is never valid (L6). The dispatcher treats any other emitted decision as a `contract_violation` handled by the failure policy (§D.3.3). |
| `timeout` | `float` (seconds; P6 lands float support in `_toml.format_scalar`) | yes | — | Per-hook budget; `0 < t ≤ 600`, `≤ 30` on tool and prompt events (H9). Feeds the per-event deadline formula (§D.4); a value above its event's cap is clamped with a validate warning. |
| `on_error` | `ask` \| `deny` \| `open` | yes | — | What a crash, timeout, malformed output **or untrusted handler** becomes: `ask` (guard default; unattended → `[hooks] unattended_ask`), `deny` (fail-closed — overlay hooks only, H10), `open` (no decision + one note per session). **Clamped per firing event**: on events whose `on_error` column (below) allows only `open` (`stop`, `subagent_stop`, `post_*`, `session_*`, `pre_compact`), the effective value is `open` whatever is declared, so a `stop` + `pre_tool_use` hook may declare `ask` for its guard half. |
| `applies_if` | `dict` | no | `{}` | The §6.4 DSL, evaluated at sync; ANDed with the linked rule's (§A.7). |
| `linked_rule` | `str \| None` | no | `None` | A rule id; the hook inherits that rule's `applies_if` and `globs` and its `lint_codes` (§A.7). |
| `supports` | `list[str]` | yes | — | Adapters allowed to render native enforcement: ⊆ the hook-capable adapters (`claude_code`, `opencode`); at least one declared event must be reachable via `Adapter.hook_support` on each listed adapter; an event unreachable on a listed adapter warns and renders `degraded` (H11, §C.1.1, OQ-43). |
| `tags` | `list[str]` | no | `[]` | Filtering / reporting only. |

Canonical events (the snake_case names are the only spelling in canonical sources; harness names live in the adapters):

| `HookEvent` | Claude Code event | Allowed `decisions` | `on_error` allowed | `HookMatcher` fields |
| --- | --- | --- | --- | --- |
| `session_start` | `SessionStart` | `context`, `none` | `open` | `sources` (`startup`\|`resume`\|`clear`\|`compact`\|`fork`) |
| `user_prompt_submit` | `UserPromptSubmit` | `deny`, `context`, `none` | `deny`, `open` | — |
| `pre_tool_use` | `PreToolUse` | `deny`, `ask`, `context`, `none` | `ask`, `deny`, `open` | `tools`, `tool_names`, `paths`, `command` |
| `post_tool_use` | `PostToolUse` | `context`, `none` | `open` | `tools`, `tool_names`, `paths`, `command` |
| `post_tool_use_failure` | `PostToolUseFailure` | `context`, `none` | `open` | `tools`, `tool_names`, `paths`, `command` |
| `stop` | `Stop` | `deny`, `context`, `none` | `open` | — |
| `subagent_stop` | `SubagentStop` | `deny`, `context`, `none` | `open` | `agent_types` |
| `pre_compact` | `PreCompact` | `none` | `open` | `triggers` (`manual`\|`auto`) |
| `session_end` | `SessionEnd` | `none` | `open` | — |

`deny` means: refuse the tool call (`pre_tool_use`), block the prompt (`user_prompt_submit`), refuse to stop and continue with the reason (`stop`/`subagent_stop`). `ask` routes to the harness permission prompt; it degrades to `[hooks] unattended_ask` when no human can answer and to deny-with-reason on harnesses without an ask primitive (OpenCode). `pre_compact` is observe-only because blocking a recovery compaction fails the request; its only decision is `none` on every adapter, so OpenCode does not register it (§C.3.2). Per-adapter event support (OpenCode's mapping in particular) is owned by §C via `Adapter.hook_support` (H11).

`HookMatcher` — all present dimensions are ANDed; a dimension that does not apply to the call's tool class is vacuously true:

| Field | Type | Applies to | Semantics |
| --- | --- | --- | --- |
| `tools` | `list[ToolClass]` | tool events | Any-of canonical tool classes (table below); `[]` together with empty `tool_names` = every tool (rendered as Claude matcher `*`). |
| `tool_names` | `list[str]` (regex) | tool events | `re.fullmatch` over the **canonical Claude-shaped** tool name (e.g. `mcp__github__.*`, `Agent`); OR-ed with `tools`. |
| `paths` | `list[str]` (glob) | path-bearing calls (`edit`, `write`, `notebook_edit`, `read`, `search`) | Repo-relative POSIX path; `**` crosses directories, `*` does not; case-insensitive on darwin/win32. |
| `command` | `list[str]` (regex) | `shell` | `re.search` over each shell segment after the dispatcher strips wrapper prefixes (`env`, `sudo`, `timeout`, `nice`, `nohup`, plus `[hooks] wrapper_prefixes`). |
| `sources` / `triggers` / `agent_types` | `list[str]` | as per event table | Exact-match any-of. |

Canonical tool classes — **the single vocabulary** used by authored matchers, the §C registration union and the §D runtime classifier (`hook_runtime/event.py::ToolClass` is a `StrEnum` with exactly these values plus the runtime-only `other`; a unit test asserts `set(types.ToolClass.__args__) == {m.value for m in event.ToolClass} - {"other"}`):

| `ToolClass` | Claude Code tool names | OpenCode V1 tool names |
| --- | --- | --- |
| `shell` | `Bash`, `PowerShell` | `bash` |
| `edit` | `Edit`, `MultiEdit` (legacy, tolerated) | `edit`, `apply_patch` |
| `write` | `Write` | `write`, `apply_patch` |
| `notebook_edit` | `NotebookEdit` | — |
| `read` | `Read` | `read` |
| `search` | `Glob`, `Grep` | `glob`, `grep` |
| `web` | `WebFetch`, `WebSearch` | `webfetch`, `websearch` |
| `subagent` | `Agent` (also `Task`, older name) | `task` |
| `mcp` | `mcp__.*` (incl. `mcp__plugin_…`) | **unsupported**: `<server>_<tool>` names are indistinguishable from plugin tools; validate warns and `playbook check` reports the hook `degraded` on opencode |
| `other` (runtime only; not authorable, H4) | everything else (`Skill`, `TodoWrite`, `ExitPlanMode`, …) | everything else, incl. MCP and plugin tools |

Because `Glob`/`Grep` are absent by default on macOS/Linux, read-guards that care about secrets **must** match `read`, `search` **and** `shell` (reader commands). Post-edit hooks match `edit`, `write` and `notebook_edit`.

`HookHandler` — exactly one form:

| Field | Form | Type | Semantics |
| --- | --- | --- | --- |
| `builtin` | builtin | `str` | Registered name in the `@register_hook_handler` registry / `coding_agent_playbook.hook_handlers` group. **Naming rule (locked):** snake_case, shareable — several hooks may use one handler with different `config` (e.g. `error-handling-lint-feedback`, `typing-lint-feedback` and `pytest-conventions-feedback` share `ruff_lint_feedback`); a companion handler on a second event is `<name>:<role>` (e.g. `gate_weakening_guard:pre_edit`). The decision log records `hook_id` separately, so handler names need not equal hook ids. |
| `command` | external | `python` \| `bash` \| `sh` \| `node` | The **launcher**, never a shell string. `python` = the engine's pinned interpreter (§C.2.7) run with `-I`; `bash`/`sh`/`node` resolve through the per-worktree `machine.json` tool pins (§D.8.3). No `exec` form: interpreter-explicit commands survive `core.fileMode=false`, Windows and wheel installs. |
| `script` | external | `str` | POSIX path relative to the hook directory, under `scripts/`, contained in it (H7). Sync byte-copies the directory to `.coding-agent-playbook/hooks/scripts/<hook-id>/` (§C.0); `guard_config.json` holds the repo-relative copy path, never an absolute one. |
| `args` | external | `list[str]` | Static argv appended after the script; no templating, no shell, no `://`. |
| `config` | both | `dict[str, Any]` | TOML-scalar-safe (`bool`/`int`/`float`/`str`/date, lists, nested tables; P6). Builtin: validated against the handler's `CONFIG_SCHEMA` and merged across layers (§A.6) and with the consumer's `[hooks.<hook-id>]` table (§B.1). External: delivered verbatim in the stdin envelope (§D.3.1). |

### A.3 Dataclasses (`types.py`, NEW additions)

```python
HookEvent = Literal[
    "session_start",
    "user_prompt_submit",
    "pre_tool_use",
    "post_tool_use",
    "post_tool_use_failure",
    "stop",
    "subagent_stop",
    "pre_compact",
    "session_end",
]
HookDecision = Literal["deny", "ask", "context", "none"]
HookTier = Literal["default", "opt-in", "overlay"]
HookOnError = Literal["ask", "deny", "open"]
ToolClass = Literal[
    "shell",
    "edit",
    "write",
    "notebook_edit",
    "read",
    "search",
    "web",
    "subagent",
    "mcp",
]
HookLauncher = Literal["python", "bash", "sh", "node"]


class HookSchemaError(ValueError):
    """Field-precise frontmatter error: carries where/field/value/expected (SPEC §6.6.1)."""

    def __init__(self, where: str, field: str, value: object, expected: str) -> None: ...


@dataclass
class HookMatcher:
    tools: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    agent_types: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Same None-coercion idiom as RuleFrontmatter (types.py:67-82): YAML 'key:' is None.
        for name in (
            "tools",
            "tool_names",
            "paths",
            "command",
            "sources",
            "triggers",
            "agent_types",
        ):
            if getattr(self, name) is None:
                setattr(self, name, [])


@dataclass
class HookHandler:
    builtin: str | None = None
    command: HookLauncher | None = None
    script: str | None = None
    args: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:  # args/config None-coercion
        ...

    @property
    def is_external(self) -> bool:
        return self.builtin is None


@dataclass
class HookFrontmatter:
    id: str
    name: str
    description: str
    tier: HookTier
    events: list[HookEvent]
    decisions: list[HookDecision]
    timeout: float
    on_error: HookOnError
    supports: list[str]
    handler: HookHandler | None = None  # exactly one of handler / handlers (H6)
    handlers: dict[str, HookHandler] = field(default_factory=dict)
    version: int = 1
    enabled: bool = True
    mandatory: bool = False
    priority: int = 50
    matcher: dict[str, HookMatcher] = field(default_factory=dict)
    applies_if: dict[str, Any] = field(default_factory=dict)
    linked_rule: str | None = None
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # None-coercion for version/enabled/mandatory/priority/handlers/matcher/applies_if/tags,
        # and timeout -> float, so markdown round-trip stays lossless (SPEC §6.6.3).
        ...

    def handler_for(self, event: str) -> HookHandler:
        """The handler bound to ``event`` (``handlers[event]`` or the shared ``handler``)."""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, where: str) -> HookFrontmatter:
        """Build nested HookHandler/HookMatcher from parsed YAML.

        Raises HookSchemaError on an unknown key, a missing required key or a wrong type.
        Example: HookFrontmatter.from_mapping(yaml.safe_load(text), where="playbook/hooks/x/HOOK.md")
        """

    def to_mapping(self) -> dict[str, Any]:
        """Inverse of from_mapping: dataclasses.asdict with empty values dropped at every depth."""


@dataclass
class Hook:
    frontmatter: HookFrontmatter
    body: str  # post-Jinja advisory prose (== template_body for .md)
    template_body: str
    is_templated: bool  # HOOK.md.j2
    source_path: Path | None  # .../<id>/HOOK.md(.j2); None for non-filesystem sources
    source_package: str  # engine/overlay package name or "<repo-local>"
    scripts_dir: Path | None  # <hook dir>/scripts when present

    @property
    def hook_dir(self) -> Path | None: ...
    @classmethod
    def from_markdown(cls, path: Path, source_package: str) -> Hook: ...
    def to_markdown(self) -> str: ...
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Hook: ...
    def to_advisory_rule(self) -> Rule | None: ...  # §A.8
```

`Hook` keeps `source_path` (unlike `Skill`, `types.py:199-258`) because validate, `render --show-source` and script containment need it. `HookFrontmatter` is a typed dataclass (not `Skill`'s open dict) so `orchestrator.artifact_id_of` (`orchestrator.py:138-153`) works unchanged and validate errors are field-precise. `_typing.py:19-28` gains `from coding_agent_playbook.types import Hook as Hook` under `TYPE_CHECKING`. The dispatcher never imports `types.py` (it imports `yaml` at module top); it reads the rendered `guard_config.json`.

### A.4 Markdown round-trip contract (SPEC §6.6.3)

- `Hook.from_dict(h.to_dict()) == h` — identity. `to_dict` serializes `frontmatter` via `dataclasses.asdict` (full, lossless), `source_path` and `scripts_dir` as `str | None` (the `Skill.to_dict` convention, `types.py:239-246`).
- `Hook.from_markdown(p, pkg)` → `to_markdown()` → re-parse yields an equal `frontmatter` and `template_body`. `to_markdown` emits `format_frontmatter(to_mapping(), template_body)` (`types.py:39-42`); empty values are dropped **recursively** (a deep variant of `_without_empty`, `types.py:45-47`), so `handler: {builtin: x}` does not round-trip as `{builtin: x, command: null, script: null, args: [], config: {}}`.
- Byte identity of authored markdown is not promised (key order follows the dataclass, YAML whitespace is normalized) — the same contract rules and prompts have (§6.6.6).
- Scripts are not part of the canonical type: `scripts_dir` points at them; adapters byte-copy (`shutil.copy2`) and the lockfile records the exec bit (§B.6).

### A.5 Discovery — `ArtifactSource.list_hooks`

- `sources/base.py`: `ArtifactSource.list_hooks(self) -> list[Hook]` is a **concrete default returning `[]`** — not `@abstractmethod`, which would break third-party sources and `tests/unit/test_sources_base.py::_DummyArtifactSource` (`:10-23`).
- `sources/filesystem.py`: `_find_skill_md` (`:214-220`) generalizes to NEW `_find_primary_md(dir: Path, stem: str) -> Path | None`; NEW `_iter_hooks(hooks_root: Path, source_package: str) -> Iterator[Hook]` yields one `Hook` per directory holding `HOOK.md`/`HOOK.md.j2`, walking `sorted(hooks_root.rglob("HOOK.md*"))` filtered to exactly those two names, skipping any path with a dot-directory component (the `_iter_md_files` hygiene rule), setting `scripts_dir` when `<dir>/scripts` exists. `FileSystemArtifactSource.list_hooks()` walks `_resource_subdir(pkg, "hooks")` for the engine then each overlay in `overlays_enabled` order, then `<repo>/playbook/hooks` with `source_package="<repo-local>"` — the `list_skills` order (`:274-284`). No `pyproject.toml` change: the wheel already ships all of `src/coding_agent_playbook`.
- `list_hooks` raises `HookSchemaError` on the first malformed hook (fail loudly, like `Rule.from_markdown`) — except under `SyncContext.from_repo(..., tolerate_hook_errors=True)`, which `playbook validate` passes (P8 (c)): each malformed hook is then recorded in `ctx.hook_load_errors` and `_check_hooks` aggregates them as `FAIL <path>: <message>` lines, so validate never stops at a traceback before reporting.
- `SyncContext` (`orchestrator.py:219-297`) gains `hooks_resolved: list[Hook]` filled in `from_repo` next to `:268-282`. `playbook eval` builds `SyncContext` too, so a malformed hook also fails `eval` — intended (one canonical set).

### A.6 Overlay merge — `OverlayResolver.resolve_hooks` and the additive policy

`resolve_hooks(engine, overlays, repo_local) -> list[Hook]` records `Collision(kind="hook", …)` (the `Collision.kind` docstring at `orchestrator.py:53` gains `"hook"`). It does **not** reuse `_resolve` (`orchestrator.py:107-135`) as-is, because `_resolve` keeps only the winner object and the hook policy needs every layer's definition of an id. It groups definitions by id in layer order (engine → overlays in `overlays_enabled` order → repo-local; today the flattened `list_hooks` order already encodes this), picks the last as the winner, then applies NEW `hook_policy.merge_hook_layers(definitions) -> tuple[Hook, list[str]]` (shared name — proposed; module `coding_agent_playbook/hook_policy.py`, stdlib-only). `hook_policy` is a **sync-time** module: `hook_runtime` never imports it (the runtime reads only the compiled `guard_config.json`, §D.8), so it is not on the dispatcher allow-list. Violations are collected on `OverlayResolver.hook_violations` and surfaced by validate (H14, H15) — resolution itself never raises.

| Layer overriding an earlier definition | Frontmatter | `handler.config` (builtin) |
| --- | --- | --- |
| **Overlay** over engine/earlier overlay | Replace-by-id (L2), but may not: swap `handler.builtin`, set `enabled: false` on a `default`-tier hook, drop any event, tool class or `deny`/`ask` decision, weaken `on_error` (`open` < `ask` < `deny`), demote `tier` (`default` → `opt-in`/`overlay`). Promotion (`opt-in`/`overlay` → `default`) is how an overlay **activates** an engine mechanism. | Merged per the handler's `CONFIG_SCHEMA` key policy: `extend` (deny rows, patterns, protected paths — union, earlier first, deduped), `strictest` (ordered modes, e.g. `off < warn < block`), `relax` (allowlists/exemptions — union), `replace` (messages, caps). An overlay can never shrink an `extend` key or lower a `strictest` key: **overlays may only add**. |
| **Repo-local** over a non-mandatory hook | Replace-by-id, consumer's choice (equivalent in power to `[hooks] disable`). | `replace` for every key. |
| **Repo-local** over a `mandatory` hook | Forbidden (H15). The consumer customizes mandatory hooks only through `[hooks.<hook-id>]` and `[guardrails]` (§B.1, §B.3), where `relax` keys are ignored for mandatory hooks. | — |
| **Consumer config** `[hooks.<hook-id>]` (applied after repo-local) | — | Validated against the handler's `CONFIG_SCHEMA` and merged with the same key policies as an overlay (`extend`/`strictest`/`relax`/`replace`); `relax` keys are ignored (sync warns) for `mandatory` hooks. |

Data-only by default: an overlay may ship builtin-handler hooks, same-id overrides and handler `config` freely; an **external-command** hook from an overlay or from repo-local runs only when its `source_package` is in `[hooks] allow_code_from` **and** its command + script hash is approved in the user-local trust store (§B.4).

### A.7 `applies_if`, `linked_rule`, and the effective view

- **`applies_if`** uses the §6.4 DSL via `detector.evaluate_predicate`; unknown keys fail validate exactly as for rules (H17).
- **`linked_rule: <rule-id>`** binds a hook to the rule whose practice it enforces:
  1. effective `applies_if` = hook's AND the linked rule's; if the linked rule does not survive its own `applies_if` filter, the hook is off (reported as `skipped: linked rule <id> not applicable`);
  2. for every event whose matcher declares no `paths`, `paths` := the linked rule's `globs` when the rule is `scope: scoped` with non-empty `globs`; explicit hook `paths` win (no union);
  3. if the rule declares `lint_codes` (NEW optional `RuleFrontmatter` field — shared name — proposed; **one schema**, defined here and used verbatim by §E.3 and §F: `dict[str, Any]` with keys `warn: list[str]` and optional `when: list[{applies_if: dict, warn: list[str]}]`, the `when` predicates evaluated at sync by `detector.evaluate_predicate`; there is no `block` key — lint feedback is warn-only), the resolved code list is merged into the builtin handler's `config["lint_codes"]` at sync, so the rule text and the enforcing hook share one source. `RuleFrontmatter(**data)` (`types.py:97`) rejects unknown keys today, so this field is a schema + round-trip change landed with the first lint-feedback hook, **including the agent_harness sidecar**: `ManifestEntry` gains `lint_codes`, `_KIND_FIELDS["rule"]` (`harness/manifest.py:111-125`) lists it, `_entry_to_table` emits it as an inline table (as `applies_if` is) and `_entry_from_table` / `commands/import_harness.py::_rule_from_entry` read it back. The same applies to the new `PromptFrontmatter` fields `write_scope` (§E.3) and `output_contract` (§E.2) via `_prompt_from_entry`. Tests: `tests/harness/test_manifest_roundtrip.py` and `tests/harness/test_import_roundtrip.py` cover all three fields.
  The link is one-way: rules never reference hooks. A dangling `linked_rule` is a validate error (H18).
- **Effective view.** NEW `hook_policy.resolve_effective_hooks(hooks, rules, hooks_cfg, guardrails_cfg, facts, repo_root) -> tuple[list[ResolvedHook], list[SkippedHook]]` (shared names — proposed) is the single place that applies the §B.1 on-formula, `applies_if`, `linked_rule` inheritance, the `[guardrails]` domain merge and the `supports ∩ [hooks] adapters` intersection. `ResolvedHook` (frozen: `id`, `source_package`, `events`, `priority`, `matcher`, `handlers: dict[HookEvent, ResolvedHandler]` with merged config, `decisions`, `timeout`, `on_error` (per event, after the §A.2 clamp), `supports`, `mandatory`, `script_sha256`, `advisory: Rule | None`). **`ResolvedHook.to_json() -> dict[str, Any]` is the single `guard_config.json` hook-record schema** (§D.8.2 references it field by field): `{"id", "source_package", "events": [...], "priority": int, "matcher": {event: {tools, tool_names, paths, command, sources, triggers, agent_types}}, "handlers": {event: {"kind": "builtin"|"entry_point"|"external", "name"|"target"+"dist"|"argv", "config"}}, "decisions": [...], "timeout_ms": int, "on_error": {event: "ask"|"deny"|"open"}, "supports": [...], "mandatory": bool, "script_sha256": str|null}` — one name per field (`supports`, not `adapters`; `matcher`, not `match`; `timeout_ms`). `SkippedHook(id, reason)` feeds `playbook check` and the sync summary. `sync._filter_applies_if` (`commands/sync.py:121-134`) is not widened — hooks are gated only here, and §C.1.3 calls this function.

### A.8 Degrade path — body → advisory text (L1)

A hook's **body** is advisory prose that degrades into outputs whose harness cannot enforce it — analogous to `Skill.to_prompt` (`types.py:210-237`), but **never silent**:

- **The single advisory-rule contract (locked; §C.1.1 references it, does not redefine it).** `Hook.to_advisory_rule() -> Rule | None` returns `None` when the rendered body is blank (audit-class hooks have nothing to advise). Otherwise a `Rule` with `id = "guardrail-" + hook.id` (the `guardrail-` prefix is reserved for advisory rules, H20, which keeps them out of the canonical rule id space), `name = "Guardrail: " + hook.name`, `description = hook.description`, `priority = 30` (the "Compliance and security" band of SPEC §10.2.1, hence Continue's `30-guardrail-<id>.md`), `scope = "scoped"` with the effective `paths` as `globs` when present, else `"always"`, `applies_if = {}` (already gated), `source_path`/`source_package` copied from the hook, and as body the `hook_advisory` projection of §C.4.1 (the rendered body plus its one enforcement line — there is no second preface). Callers must handle `None` (§C.1.1 ABC default).
- `.md.j2` bodies render through the sandboxed base environment (`is_prompt_context=False`, so `rule()` is undefined — H19). Frontmatter and scripts are never rendered.
- Routing (implemented by §C, contract fixed here): the advisory rule of every **on** hook goes to `agents_md` (always — Codex/Cursor/others read AGENTS.md) and `continue`; it goes to `claude_code` (CLAUDE.md) only when the hook is not enforced there (`claude_code ∉ supports ∩ [hooks] adapters`). OpenCode reads AGENTS.md, so it sees the advisory next to its own enforcement — acceptable, the text describes the enforced practice.
- `[hooks] advisory = false` suppresses the degrade; an absent `[hooks]` table renders none (no upgrade drift, §B.1). Linked hooks should keep their body empty or one line — the linked rule already carries the practice.
- `playbook check` labels each on-hook per adapter with one label set (shared with §C.1.1): `enforced` (every declared event native), `degraded` (reachable but weaker, e.g. OpenCode Stop evidence-only, OpenCode `mcp`), `advisory` (advisory text only), or `—` (not rendered for that adapter).

### A.9 Worked example 1 — engine builtin: `guard-generated-outputs`

`src/coding_agent_playbook/resources/hooks/protect/guard-generated-outputs/HOOK.md`:

```markdown
---
id: guard-generated-outputs
name: Guard generated outputs
description: Deny hand-edits to files that playbook sync generates and point at the canonical source.
version: 1
tier: default
priority: 10
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [edit, write, notebook_edit, shell]
handler:
  builtin: guard_generated_outputs
  config:
    extra_protected: []
decisions: [deny, ask, none]
timeout: 2
on_error: ask
supports: [claude_code, opencode]
tags: [protect, drift]
---
Files that begin with the AUTOGENERATED sentinel, and every path listed in
`.coding-agent-playbook.lock`, are produced by `playbook sync`; a hand edit is overwritten
by the next sync. Edit the canonical source under `playbook/` instead (add a same-id
override there for engine or overlay content), then run `playbook validate && playbook sync`.
```

What each field buys: the protected set itself is **data rendered at sync** (lockfile entries with P4 provenance + every adapter's `_output_directories()`) into `guard_config.json`, so the hot path never renders or shells out; `shell` is in `tools` because the handler parses Bash *write targets* (redirect, `tee`, `sed -i`, `cp`/`mv` destination) — the matcher only pre-filters; `extra_protected` is an `extend` key, so an overlay can add protected globs but never remove one; `on_error: ask` follows the guard-class failure policy (unattended → `deny` by default); `ask` is in `decisions` for the missing-`guard_config.json` and hook-artifact cases ("ask the user"), `allow` is not expressible. `PLAYBOOK_ALLOW_GENERATED_EDIT=1` is honoured only from the hook process environment (§B.2), not configurable here. The body becomes the advisory paragraph for AGENTS.md / Continue.

### A.10 Worked example 2 — overlay external command: `bnp-sql-pii-columns`

`playbook_rules_bnp/resources/hooks/data/bnp-sql-pii-columns/` (an illustrative overlay):

```markdown
---
id: bnp-sql-pii-columns
name: Flag PII columns in edited SQL
description: After an edit to a .sql file, report selected columns the data dictionary classifies as PII.
version: 1
tier: default
events: [post_tool_use]
matcher:
  post_tool_use:
    tools: [edit, write]
    paths: ["**/*.sql"]
handler:
  command: python
  script: scripts/pii_columns.py
  args: ["--max-findings", "5"]
  config:
    masked_view_prefix: vw_masked_
decisions: [context, none]
timeout: 3
on_error: open
linked_rule: bnp-pii-handling
supports: [claude_code, opencode]
tags: [overlay, pii]
---
```

```
scripts/
├── pii_columns.py          # reads the stdin envelope, prints a context decision or nothing
└── pii_dictionary.json     # data; located by the script relative to its own __file__
```

The body is empty on purpose: `linked_rule: bnp-pii-handling` already renders the practice into every output, so no duplicate advisory. `tier: default` because this is the overlay's own hook (`overlay` tier is for engine mechanisms, H12). `post_tool_use` limits it to `context`/`none` and `on_error: open` (H5, H10). It inherits `bnp-pii-handling`'s `applies_if`; it declares its own `paths`, so the rule's globs are not inherited.

It runs only after two independent human acts. The consumer commits:

```toml
[hooks]
enabled = true
allow_code_from = ["playbook_rules_bnp"]
```

and a developer approves it once per machine, interactively (a non-TTY sync never prompts and never approves; until approval the dispatcher treats the handler as untrusted → `on_error: open` → skipped with one note per session):

```
$ playbook sync
...
! 1 hook handler needs approval (code from overlay playbook_rules_bnp):
    bnp-sql-pii-columns: python -I .coding-agent-playbook/hooks/scripts/bnp-sql-pii-columns/pii_columns.py --max-findings 5
    script sha256 3f9a51c2…  (new)
  Run this code on every matching tool call in this repo? [y/N] y
✓ Approval recorded in ~/.local/state/coding-agent-playbook/trust.json
```

A later overlay upgrade that changes `pii_columns.py` changes the hash, so the handler is skipped again until re-approved (shown as `(changed: 3f9a51c2… -> 8be07d11…)`).

### A.11 Engine touch points owned by this section

| File | Change |
| --- | --- |
| `types.py` | `Hook*` dataclasses, `HookSchemaError`, Literals (§A.3); `RuleFrontmatter.lint_codes` (§A.7, lands with the first lint hook) |
| `_typing.py` | `Hook` re-export |
| `sources/base.py`, `sources/filesystem.py` | `list_hooks` default + filesystem walk (§A.5) |
| `orchestrator.py` | `resolve_hooks`, `Collision(kind="hook")`, `hook_violations`, `SyncContext.hooks_resolved` |
| `hook_policy.py` (NEW, sync-time only) | `merge_hook_layers`, `resolve_effective_hooks`, `ResolvedHook`, `SkippedHook`, `classify_hook` (§B.5), and the **one** home of the event, tool-class and adapter-support tables (`HOOK_EVENTS`, `TOOL_CLASS_NAMES`, `HOOK_SUPPORT`) that §C's renderers and the adapters' `hook_support` ClassVars read |
| `config.py` | `HooksConfig`, `GuardrailsConfig`, `parse_hooks_config`, `parse_guardrails_config` (§B.1, §B.3) |
| `security/trust.py` (NEW, shared name — proposed) | `TrustStore` (reader **and** writer; the one trust module, on the dispatcher allow-list), `default_trust_store_path`, `repo_key` (§B.4) |
| `commands/validate.py` | `_check_hooks`, `"hooks"` in `_LINK_CHECKED_SUBDIRS` (`:241`), hooks in the OK count (`:394`; `:393` computes `artifact_count`) |
| `lockfile.py`, `commands/sync.py` | schema v2 + provenance + `SyncResult` (P4, §B.6) |

Adapter ABC additions (`hook_support`, `begin_sync`, `write_hook`, `managed_lock_entries` — §C.1.1), sync dispatch, `playbook render <hook-id>` and the `playbook check` Hooks block belong to §C; they consume `ResolvedHook`.

---

## §B — Configuration, trust and validation

### B.1 The `[hooks]` table (`.coding-agent-playbook.toml`)

Parsed by `config.parse_hooks_config(data) -> HooksConfig` (frozen dataclass; unknown keys and wrong types raise `ValueError` naming the offending value and the expected shape). Two nesting levels at most for the scalar keys; row lists use inline tables (writer support from P6).

| Key | Type | Default | Semantics |
| --- | --- | --- | --- |
| `enabled` | `bool` | `false` — both when the table is **absent** and when it is present without the key (the key is effectively required to opt in); `playbook init` writes `true` | Master switch for enforcement rendering. `false` ⇒ sync renders no registrations, no `guard_config.json`, no OpenCode shim, and strips previously managed entries. |
| `adapters` | `list[str]` | `adapters_enabled ∩ {claude_code, opencode}` | Adapters that receive native registrations. |
| `tiers` | `list[str]` ⊆ {`default`, `opt-in`} | `["default"]` | Tiers that are on by default; add `"opt-in"` to bulk-enable opt-in hooks. `overlay`-tier mechanisms are activated only by an overlay promoting the hook to `tier: default` (§A.6, §E.5), never from here. |
| `enable` | `list[id]` | `[]` | Turn on individual hooks regardless of tier. |
| `disable` | `list[id]` | `[]` | Turn off individual hooks; may not name a `mandatory` hook (H15). Wins over `enable`. |
| `advisory` | `bool` | `true` (table present) | Render on-hooks' bodies as advisory text (§A.8). |
| `unattended_ask` | `"deny"` \| `"warn"` | `"deny"` | What `ask` (decision or `on_error`) becomes when no human can answer (headless `claude -p`, SDK, CI, runner evals, OpenCode; detection in §D.3.6). `warn` = `context` + proceed + a user note. This is the only value set; §D.3.6 and `guard_config.unattended_ask` use it verbatim. |
| `allow_code_from` | `list[str]` | `[]` | Source packages whose external-command or entry-point handlers may run: overlay names from `overlays_enabled`, and/or `"<repo-local>"`. The engine package is implicit. |
| `auto_sync` | `bool` | `false` | Lets validate-then-sync-on-canonical-edit run `playbook sync` itself (never for edits to hooks, `[hooks]`, `[guardrails]`, `overlays_enabled`, `adapters_enabled`). |
| `wrapper_prefixes` | `list[str]` | `[]` | (shared name — proposed) Extra command prefixes the dispatcher strips before shell matching (e.g. `["proxy"]` for a command-rewriting launcher), beyond the built-in `env`/`sudo`/`timeout`/`nice`/`nohup`; rendered to `guard_config.shell.wrapper_prefixes` (§D.8.2). A stripped prefix is invisible to every guard, so no token of an entry may name a guarded command — a program a guard inspects by name (every builtin handler's `argv0s` and the guards' program tables), a built-in launcher, a runner (`uv`, `poetry`, …) or a shell/interpreter; such an entry is an H21 error. A launcher only one developer uses is declared at run time instead, through `PLAYBOOK_HOOK_WRAPPER_PREFIXES` (§B.2, §D.7): `.local.toml` never holds `[hooks]`. |
| `state_ttl_days` | `int` | `7` | (shared name — proposed) Age after which per-session state is swept (§D.6.1). |
| `render_remediation_allow` | `bool` | `false` | (shared name — proposed) Render the fixed engine list of remediation commands into `permissions.allow` (§C.2.8). Off by default: an allow list is a committed privilege grant. |

Per-event deadlines are **derived**, not configured (§D.4 formula), so `[hooks]` has no `deadlines_ms` key.

**Per-hook configuration — one model (locked).** Every per-hook knob lives in `[hooks.<hook-id>]`, which is the **consumer layer** of that hook's `handler.config`: validated against the handler's `CONFIG_SCHEMA` (H21) and merged after the repo-local layer with the §A.6 key policies (`relax` keys ignored for `mandatory` hooks). Key names are exactly the HOOK.md `config` keys, which §E and §F define per hook. Examples: `[hooks.stop-ci-parity-gate]` (`stages` ⊆ `typecheck`\|`tests` — the execution stages that run repo-controlled code, additionally gated by execution trust (§B.4); `verify_commands`, derived at sync from the consumer's pre-commit config and detector facts when absent; `max_blocks` `int` 1–8, default `2`; `budget_s`, default `3.0`), `[hooks.command-convention-guard] rules` (`list` of `{pattern, decision: "deny"|"warn", message}`, the engine ships zero rows), `[hooks.gate-weakening-guard]` (`added_line_patterns`, `protected_config_keys`, `justification_regex`; the first two `extend`). The coverage stage's execution switch is its own hook id (`[hooks.coverage-diff-gate]`, §F.1). There are no `[hooks.stop_gate]`, `[hooks.command_rules]` or `[hooks.gate_integrity]` tables.

**One reserved sub-table that is not a hook id:** `[hooks.commit_convention]` (addendum D-Q3), read by the commit-message hook **and** its CI/push twins: `cutover_date` (`str`, `"YYYY-MM-DD"`, a TOML string — not a date literal; unset ⇒ every commit is checked). Validated by H21. The convention itself lives in the consumer's `[tool.commitizen]` (commitizen's own config; default `cz_conventional_commits`), not in playbook config; loosening it is watched by gate-weakening-guard (§E.2).

"Stop-gate stages" are therefore not a separate list: each non-coordinator Stop stage is its own `Hook` (`events: [stop]`) switched by `tiers`/`enable`/`disable`, declaring its stage name in `handler.config.stage`; the run order is the engine constant `STOP_STAGE_ORDER` (§E.0.4), not `priority`.

**Effective on-formula** (`hook_policy.resolve_effective_hooks`, evaluated at sync; `w` = the winning definition after §A.6):

```
on(w) = cfg.enabled
        and w.enabled
        and applicable(w)          # applies_if ∧ linked rule survives ∧ (w.supports ∩ cfg.adapters ≠ ∅)
        and (w.mandatory
             or (w.id not in cfg.disable
                 and (w.id in cfg.enable or w.tier in cfg.tiers)))
```

**Absent table ⇒ off (no upgrade injection).** A consumer upgrading the engine without a `[hooks]` table gets **zero byte change** — no settings entries, no shim, no advisory text — and `playbook sync` prints one notice line (`hooks available: add [hooks] enabled = true or re-run playbook init`). New repos opt in through `playbook init` ("Enable assistant lifecycle hooks? [Y/n]"; non-interactive default yes, `--no-hooks` (shared name — proposed) to opt out). Once enabled, `default`-tier hooks are on by default as the catalog intends. This reconciles "default = on by default" with the engine-upgrade drift invariant (§B.7 Q3).

**`.coding-agent-playbook.local.toml` exclusion.** `[hooks]` and `[guardrails]` keys in the gitignored local file are **ignored** (sync warns; validate errors, H21): committed output (`.claude/settings.json`, the shim, `guard_config.json`) must not depend on a file CI never sees, and a gitignored, deep-merged file is an unreviewed off switch. This narrows §7.2's deep-merge for these two tables only. Per-developer deviation is runtime-only, through the hook-process environment (§B.2): `PLAYBOOK_HOOKS_DISABLE`, and a developer's own command launchers through `PLAYBOOK_HOOK_WRAPPER_PREFIXES`.

### B.2 Kill switches and escape hatches

| Switch | Where it lives | Scope | Effect |
| --- | --- | --- | --- |
| `[hooks] enabled = false` | committed config | all hooks, all machines | Nothing rendered; managed entries stripped. |
| `[hooks] disable = [...]` | committed config | listed non-mandatory ids | Not rendered. |
| `PLAYBOOK_HOOKS=off` | hook-process environment | every hook on this machine/session | Dispatcher returns no decision immediately; logged once per session by guard-decision-log; the next session-start briefing reports it. Applies to mandatory hooks too — an honest admission that the same-UID user can always switch hooks off locally; the off-workstation twin (CI) is the control. |
| `PLAYBOOK_HOOKS_DISABLE=a,b` | hook-process environment | listed non-mandatory ids | Runtime skip, reported like the above. |
| `PLAYBOOK_GATE=off` | hook-process environment | the Stop coordinator | Stop allowed with `systemMessage` "gate disabled — NOT verified". |
| `PLAYBOOK_ALLOW_GENERATED_EDIT=1` | hook-process environment | guard-generated-outputs | Hand edit allowed (sync will still overwrite it). |
| `PLAYBOOK_HOOK_WRAPPER_PREFIXES=proxy,proxy run` | hook-process environment | the shell guards and verify-run tagging | This developer's own command launchers, merged with `[hooks] wrapper_prefixes` into `guard_config.shell` for the dispatch (§D.7). An entry with a token naming a guarded command is ignored, logged and reported by `doctor`; it can only reveal a command, never hide one. |

Escape hatches cannot be self-granted in-session: the dispatcher reads these **only from its own `os.environ`**, never from a `VAR=1 cmd` prefix inside a Bash `tool_input`. On Claude Code `os.environ` **does** include every `env` key from the user, project, local and managed settings files (Claude sets them for every subprocess it starts, hooks included; `PLAYBOOK_*` and `PYTHON*` are not on its exclusion list). So whenever a hatch variable is present, the dispatcher (§D.7) reads the `env` objects of the settings files Claude loads — repo `.claude/settings.json`, the effective `.claude/settings.local.json` (§E.1 control-plane-guard resolves its location), `${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json` — and **ignores** a hatch defined there (a deliberate human override belongs in the launching shell), reporting it once in the session-start briefing and the decision log (`escape_via_settings_env`). control-plane-guard's deny on `env` edits stays, labelled a speed bump. `-I` already neutralizes `PYTHONPATH`/`PYTHONSTARTUP` for the dispatcher itself. Edits to `[hooks]`/`[guardrails]` by the agent are denied by control-plane-guard, and edits to `playbook/hooks/**` are `ask` (executable policy the user approves; §E.1 is the single verdict).

### B.3 The `[guardrails]` table — policy shared with off-workstation twins

(shared name — proposed; adopted from the catalog.) `[hooks]` is **mechanism** (which hooks run, how); `[guardrails]` is **policy data** read by hooks *and* by their off-workstation twins (`playbook` CI subcommands, pre-commit stages) and by harness-native permission rendering — so it applies even when `[hooks] enabled = false`. Parsed by `config.parse_guardrails_config(data) -> GuardrailsConfig`. Builtin handlers declare their domain (`CONFIG_DOMAIN`), and the domain's keys merge into `ResolvedHook.handler.config` after the layer merge of §A.6, using the same key policies:

| Domain.key | Type | Merge | Note |
| --- | --- | --- | --- |
| `secrets.extra_globs` | `list[str]` | `extend` | Appended to `SECRET_PATH_GLOBS` (P7). |
| `secrets.allow_paths` | `list[str]` | `relax` | Test fixtures; ignored for mandatory hooks. |
| `git.protected_branches` | `list[str]` | `extend` | Default `["main", "master", "release/*"]`. |
| `network.mode` | `"off"`\|`"ask"`\|`"enforce"` | `strictest` | network-egress-guard (overlay tier); the same values as its `config.mode` (§E.5). |
| `network.allowed_hosts` | `list[str]` | `relax` | Suffix match; loopback always allowed. |
| `dependencies.mode` / `.allowlist` | `str` / `list[str]` | `strictest` / `relax` | dependency-allowlist-guard; values owned by §E.4. |
| `audit.retain_days` | `int` | `replace` | local-audit-log. |
| `stop_sweep.mode` | `"block"`\|`"warn"`\|`"off"` | `strictest` | stop-diff-sweep. |

Commit-message **naming** is not a `[guardrails]` domain: the convention is commitizen's (`[tool.commitizen]`) and the cut-over is `[hooks.commit_convention] cutover_date` (§B.1, addendum D-Q2/D-Q3).

`relax` keys contributed by the **consumer** layer are ignored for `mandatory` hooks (sync warns). Thresholds for the coverage, metrics and docstring tools stay in the existing `[metrics]` table (`config.parse_metrics_config`, `config.py:100-164`; e.g. `[metrics.regression.coverage]`, or the per-family `ruff_violations` thresholds of §F.2 such as `[metrics.thresholds.ruff_violations]`) — one source of truth shared with `playbook metrics`; no parallel `[guardrails.metrics]`.

### B.4 Trust model

Hooks run with the user's full permissions, outside the harness permission system, on every matching tool call. Two rules follow: **no automatic execution of repo- or overlay-controlled code without a user-local trust entry**, and **every guard is labelled honestly** as a *boundary* (enforced by the harness against the same-UID agent) or a *speed bump* (a same-UID agent can route around it; an off-workstation twin is the control).

| Code a hook would run | Default | Approval | Recorded | Invalidated by | Label |
| --- | --- | --- | --- | --- | --- |
| Engine builtin handlers (in-tree, `@register_hook_handler`) | trusted | installing the engine | — | — | — (engine code) |
| Entry-point handlers from another distribution (`coding_agent_playbook.hook_handlers`) | blocked | `allow_code_from` names the distribution's top-level package (committed, reviewed) | — (no TOFU; §K) | removal from `allow_code_from` | speed bump |
| External-command handlers (overlay / repo-local `scripts/`) | blocked | `allow_code_from` **and** TOFU at an interactive `playbook sync` | `handlers[<id>] = {source, launcher, args_sha256, script_sha256, approved_at}` — keyed on the launcher name, the copied script's sha256 and the args' sha256 (never the interpreter path, which is per machine) | any change to source, launcher, args or script bytes | speed bump |
| Execution stages that run repo-controlled code (`pytest` + `conftest.py`, `mypy` + plugins, coverage) | off | enabled in `[hooks.stop-ci-parity-gate] stages` / `[hooks.coverage-diff-gate]` (committed) **and** TOFU at an interactive `playbook sync` | `execution = {stages_sha256, approved_at}` (hash of the machine-independent stage list: names, logical tools, args) | any stage change | speed bump |
| Tool binaries invoked by builtins (`ruff`, `cz`, the project python; `gitleaks` only if already present) | pinned, **not a trust record** | automatic at every write-mode `playbook sync` | `<git_dir>/playbook-hooks/machine.json` (§D.8.3), never the trust store | stat mismatch → stage skipped with "NOT verified (toolchain changed since sync)"; a re-pin to a different binary is printed in the sync summary and the next briefing | speed bump |

The trust store holds **approvals only**. The per-worktree interpreter pin (§C.2.7) is not a trust approval: it enables engine builtins only, and any write-mode sync (including an agent-run one) may write it.

**Trust store** (NEW `security/trust.py` — the one trust module, reader and writer, stdlib-only, on the dispatcher allow-list):

- Path: `default_trust_store_path()` = `$XDG_STATE_HOME/coding-agent-playbook/trust.json` (fallback `~/.local/state/…`; Windows `%LOCALAPPDATA%\coding-agent-playbook\trust.json`). Directory mode `0700`, file `0600`, atomic writes. A resolved path inside the repo root is refused. Tests inject `TrustStore(path)` — no env-var indirection.
- Keyed by `repo_key` = sha256 of `realpath(git rev-parse --path-format=absolute --git-common-dir)` (falls back to `realpath(repo_root)` outside git), so all worktrees of a clone share approvals, mirroring where Claude Code keeps `settings.local.json`.
- **Approval happens only at an interactive `playbook sync`** (stdin and stdout are TTYs): it lists each pending item with source, full command line and old → new hash, then asks `[y/N]` per item. There is deliberately **no non-interactive approve flag**: the agent's Bash tool has no TTY, and CI/headless runs never need approvals because they run the off-workstation twins, not hooks (eval scratch dirs do not inherit project hooks unless the eval opts in). Wrapping `playbook sync` in a pty allocator (`script`, `expect`, `unbuffer`) or piping input into it is denied by control-plane-guard — a speed bump, labelled as such.
- **Enforcement is at runtime**, by the dispatcher: committed files can change under the user (a `git pull` bringing a new script and a new hash in `guard_config.json`), so before running an external handler the dispatcher checks that the copied script's sha256 equals both `ResolvedHook.script_sha256` (rendered) and the trust-store record. Untrusted ⇒ treated as a handler error ⇒ the hook's `on_error` (`open`: skip + one note per session; `ask`: "hook X is not yet approved — ask the user to run `playbook sync` in a terminal"; `deny`: deny with the same reason — the fail-closed behaviour an overlay strict mode asked for). `playbook-hook doctor` and the session-start briefing list pending approvals.
- The store lives outside the repo but is writable by the same UID; control-plane-guard denies agent writes to its path. The only deployment the agent cannot tamper with is an enterprise **managed-settings** bundle (`allowManagedHooksOnly`, scripts in a root-owned path) that regulated overlays may render — documented as the sole *boundary* for hook integrity.

### B.5 The hook trust contract — `playbook validate` rules (L6)

Implemented as `hook_policy.classify_hook(hook, ctx) -> list[str]` (per hook) plus set-level checks, aggregated by NEW `_check_hooks` in `commands/validate.py` into `ValidationError(path, message)`; every message names the offending value and the expected shape. `playbook sync` refuses to render while any error stands (P8).

| # | Rule | Example message |
| --- | --- | --- |
| H1 | `HOOK.md` parses; frontmatter keys ⊆ schema; required fields present; types match §A.2. | `unknown key 'async'; allowed: id, name, …` |
| H2 | `id` matches `^[a-z0-9][a-z0-9-]{0,62}$` and equals the directory name; unique within a layer; not both `HOOK.md` and `HOOK.md.j2`; no `HOOK.md` beneath another hook directory. | `id 'Guard_X' must match ^[a-z0-9][a-z0-9-]{0,62}$ and equal directory 'guard-x'` |
| H3 | `events` non-empty, unique, ⊆ the nine canonical names. | `event 'PreToolUse' is not canonical; did you mean 'pre_tool_use'?` |
| H4 | `matcher` keys ⊆ `events`; each entry uses only the fields allowed for its event; tool classes ∈ the §A.2 vocabulary (`other` is not authorable); `mcp` on a hook that `supports` `opencode` is a **warning** (degraded there); every regex compiles; globs are non-empty relative patterns without `..`. | `matcher.stop.tools: 'tools' is not valid for event 'stop'` |
| H5 | `decisions` non-empty, ⊆ {`deny`,`ask`,`context`,`none`}, each valid for at least one declared event (the dispatcher clamps per firing event). **`allow` is always an error.** | `decision 'allow' is never permitted: it would bypass the harness permission system` |
| H6 | Exactly one of `handler` / `handlers`; `handlers` keys = `events` exactly. Per bound handler, exactly one form. Builtin: the name is registered (snake_case, `<name>:<role>` for companions); the handler declares support for its event; `config` validates against its `CONFIG_SCHEMA`; the handler's emittable decisions ⊆ `decisions`; the handler declares `MUTATES_INPUT = False`. | `handler.builtin 'guard_generated_output' is not registered; known: …` |
| H7 | External form: `command` ∈ {`python`,`bash`,`sh`,`node`}; `script` is a relative POSIX path under `scripts/`, resolves (not a symlink) inside the hook directory (`resolved.is_relative_to(hook_dir)`, the `links.classify_link` containment idiom) and is a regular file; `args` are strings without `://`; `config` is JSON-serializable; `scripts/` exists only for external handlers. | `script '../x.sh' escapes the hook directory` |
| H8 | No HTTP, async, prompt/agent or input-rewriting handlers: keys `type`, `url`, `headers`, `async`, `updated_input`, `prompt`, `model` are rejected with a contract message (they are also unknown keys, H1). Runtime backstop: the dispatcher drops `allow`, `updatedInput` and `permissionDecision: allow` from any handler output and treats the call as a handler error. | `HTTP/async/rewrite handlers are not part of the hook contract (SPEC §17.1)` |
| H9 | `0 < timeout ≤ 600`; `≤ 30` when `events` ∩ {`pre_tool_use`,`post_tool_use`,`post_tool_use_failure`,`user_prompt_submit`} ≠ ∅. A timeout above an event's deadline cap (§D.4) is clamped with a **warning**. | `timeout 45 exceeds 30 s for tool events` |
| H10 | `on_error` is valid for at least one declared event (event table, §A.2; it is clamped to `open` on the others); `deny` additionally requires an overlay `source_package`. | `on_error 'deny' (fail-closed) is reserved for overlay hooks` |
| H11 | `supports` non-empty ⊆ hook-capable adapters; **at least one** declared event is reachable on each listed adapter, i.e. a key of that adapter's `hook_support` (§C.1.1). A declared event that is unreachable on a listed adapter is a validate **warning**: it is not registered there and `playbook check` shows it `degraded` (OQ-43). Degraded cells are not errors. | error: `no declared event of hook 'x' is reachable on adapter 'opencode'`; warning: `event 'subagent_stop' is not supported by adapter 'opencode' (degraded)` |
| H12 | `tier` valid; `tier: overlay` only on engine-sourced hooks or on an overlay's same-id override of one (shipping config without activating it); `mandatory: true` only on overlay-sourced hooks and requires `enabled: true`. | `tier 'overlay' is reserved for engine mechanisms; an overlay's own hook uses 'default' or 'opt-in'` |
| H13 | Engine-sourced hooks are builtin-only and ship no `scripts/`. | — |
| H14 | Overlay overrides respect §A.6 (no handler swap, no disabling a default-tier hook, no dropped events/tool classes/`deny`/`ask`, no weaker `on_error`, no tier demotion). | `overlay 'x' override of 'destructive-command-guard' drops decision 'deny'` |
| H15 | No repo-local same-id override of a `mandatory` hook; `[hooks] disable` names no mandatory hook; `[hooks] enabled = false` is an error while an enabled overlay ships mandatory hooks. | `'pii-prompt-guard' is mandatory (overlay playbook_rules_bnp) and cannot be disabled` |
| H16 | External-command and entry-point handlers come from a `source_package` listed in `[hooks] allow_code_from` (consumer repos only; skipped without a consumer config, P8). | `hook 'bnp-sql-pii-columns' runs code from 'playbook_rules_bnp'; add it to [hooks] allow_code_from` |
| H17 | `applies_if` keys are known (`evaluate_predicate` raising `ValueError`, as `_check_applies_if` does for rules, `commands/validate.py:64-97`). | `applies_if: unknown fact 'orm_version'` |
| H18 | `linked_rule` resolves in the merged rule set. | `linked_rule 'python-error-handlng' not found` |
| H19 | Body: `.md.j2` compiles under the sandboxed environment and never calls `rule()`; markdown links are self-contained (`"hooks"` joins `_LINK_CHECKED_SUBDIRS`, `commands/validate.py:241`). | `body calls {{ rule(...) }} — hook bodies cannot include rules` |
| H20 | Authored rule ids do not start with the reserved advisory prefix `guardrail-`; a hook id equal to a rule or prompt id is reported (`playbook render` looks ids up across kinds). | `rule id 'guardrail-x' uses the reserved 'guardrail-' prefix` |
| H21 | `[hooks]` / `[guardrails]` parse (unknown keys, types); `enable`/`disable` ids exist and are disjoint; `allow_code_from` ⊆ `overlays_enabled` ∪ {`"<repo-local>"`}; no `wrapper_prefixes` entry has a token naming a guarded command (`hook_runtime.wrapper_policy.hidden_program`, §D.2.5); every `[hooks.<x>]` sub-table names an existing hook id (or the reserved `commit_convention`) and validates against that hook's `CONFIG_SCHEMA`; `[hooks.stop-ci-parity-gate] stages` ⊆ {`typecheck`, `tests`}; `[hooks.commit_convention] cutover_date` is a `"YYYY-MM-DD"` string; neither table appears in `.local.toml`. | `[hooks] disable: unknown hook id 'post-edit-ruff'` |

The OK line becomes `OK {rules + prompts + hooks} artifacts validated` (`commands/validate.py:394`).

### B.6 Lockfile v2

`.coding-agent-playbook.lock` (`_LOCKFILE_SCHEMA = 2`, landed once by P4). **One ownership model (locked): §C's per-element entries.** A file the engine owns wholly has one entry with `scope = ""`; a user-shared JSON file (`.claude/settings.json`) has **no** whole-file entry and instead one scoped entry per managed element. `LockEntry` fields — new ones default-valued and **omitted from the TOML when at their default**, so rule/prompt entries stay compact:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `path` / `sha256` / `bytes` | `str` / `str` / `int` | — | Unchanged for whole-file entries. For a scoped entry, the hash and size cover `canonical_json(element)` (§C.1.4). |
| `kind` | `rule`\|`prompt`\|`skill`\|`hook`\|`composite`\|`runtime` | `""` (v1) | `hook` = a copied external-handler script (§C.0); `runtime` = `guard_config.json`, the launcher, the OpenCode shim, and each managed settings element; `composite` = multi-source outputs (`CLAUDE.md`, `AGENTS.md`). |
| `artifact_id` | `str` | `""` | Canonical id; `"registration:<canonical_event>"` for a managed hook registration, `"permission:<list>:<string>"` for a managed `permissions`/`sandbox` array string (§C.2.8); `""` for composite and other runtime files. |
| `source` | `str` | `""` | `source_package` of the artifact (`"<repo-local>"` for repo-local); `""` for composite and runtime entries. |
| `adapter` | `str` | `""` | Adapter that wrote the path (`""` for the sync-level `guard_config.json` and copied scripts). |
| `scope` | `str` | `""` | `""` = the entry covers the whole file; `json:<pointer>` = one managed element of the array at that JSON Pointer (e.g. `json:/hooks/PreToolUse`, `json:/permissions/deny`); the element index is deliberately not recorded. |
| `executable` | `bool` | `false` | Git-style single exec bit for copied scripts (the `harness/manifest.py` `ScriptEntry` convention); compared on POSIX only. |

There is no `owned` list and no `adapter.extract_owned`: per-element hashes replace both.

```toml
schema_version = 2
engine_version = "0.2.0"
rendered_at = "2026-10-14T10:00:00Z"

[[entries]]
path = ".continue/rules/50-python-typing.md"
sha256 = "9c1e…"
bytes = 1834
kind = "rule"
artifact_id = "python-typing"
source = "coding_agent_playbook"
adapter = "continue"

[[entries]]
path = ".claude/settings.json"
sha256 = "41ab…"              # canonical_json of this one matcher group
bytes = 212
kind = "runtime"
artifact_id = "registration:pre_tool_use"
adapter = "claude_code"
scope = "json:/hooks/PreToolUse"

[[entries]]
path = ".coding-agent-playbook/hooks/guard_config.json"
sha256 = "07d2…"
bytes = 18340
kind = "runtime"
```

Semantics:

- **Drift.** `playbook sync --check` keeps its whole-byte compare (`commands/sync.py:249-266`): the §C.2.4 no-op short circuit means the scratch re-merge rewrites `settings.json` only when the managed projection differs, so user edits to `permissions`/`env` or a reformat are not drift, while a hand-edited or deleted managed element is; exec bits are compared for `executable` entries; orphans per P2. `playbook check` (`commands/check.py:140-155`): `scope = ""` → whole-file hash (unchanged); `scope = json:<pointer>` → parse the file and look for an element under the pointer whose canonical hash equals `sha256` (§C.2.6); `executable` mismatch → `mode drift: <path>`.
- **Ownership without a sentinel.** For files that cannot carry a sentinel (copied scripts, `SKILL.md`, `guard_config.json`), the previous lockfile is the ownership record: an entry with `kind` ∈ {`skill`,`hook`,`runtime`}, `scope = ""`, not regenerated by this sync, is deleted only if its on-disk sha256 still equals the recorded one; a modified orphan is reported, never deleted. A file with scoped entries is never deleted — its managed elements are rewritten or removed inside the adapter's `finalize` (§C.2.5).
- **Machine-local outputs.** The interpreter pin and `machine.json` (§C.2.7, §D.8.3) live under the git dir, never enter the lockfile or the drift comparison; committed output stays machine-independent.
- **Compatibility.** v1 lockfiles load (all new fields defaulted, `kind = ""` treated as unknown provenance: guard-generated-outputs falls back to the generic "generated file — run playbook sync" reason); the first sync rewrites v2. Older engines read v2 (their `from_dict` picks only `path`/`sha256`/`bytes`). The trust store is never written to the lockfile or anywhere in the repo.

### B.7 Open questions raised by §A and §B

The authoritative, deduplicated list is §K; the items below are its §A/§B sources, kept for local context.


1. **`[guardrails]` as a second top-level table.** Chosen to separate mechanism (`[hooks]`) from policy shared with CI/pre-commit twins, matching the catalog. Alternative: fold the domains into `[hooks.<domain>]` (one table, but twins would then read "hooks" config even with hooks disabled).
2. **`.local.toml` exclusion** of `[hooks]`/`[guardrails]` narrows SPEC §7.2's deep merge. Consequence: a developer cannot locally *enable* an extra opt-in hook (only disable at runtime via `PLAYBOOK_HOOKS_DISABLE`). Acceptable?
3. **Absent `[hooks]` ⇒ off.** Reconciles the catalog's "default tier = on by default" with the no-upgrade-drift invariant by making the repo-level switch opt-in (init writes `enabled = true`). Alternative: on-by-default for every consumer on upgrade (every consumer drifts and gains executable registrations unannounced).
4. **P6–P9 in Track P.** They are verified defects that specific hooks need; they could instead land in the first track that consumes them. P8's validate-gated sync may break consumers whose content fails `playbook validate` today — alternative: gate sync only on the hook rules (H1–H21).
5. **CLAUDE.md edits** (P3 sentinel wording, new invariants): CLAUDE.md is tracked in this worktree, but the project memory says harness files are local-only and gitignored since 2026-10-13. Commit the CLAUDE.md change or keep it local?
6. **Commit-message convention default (L9).** *Closed by addendum D-Q2/D-Q3*: commitizen (`cz_conventional_commits` unless the consumer configures `[tool.commitizen]`) plus `[hooks.commit_convention] cutover_date` (§F.4).
7. **TTY-only approvals.** No non-interactive approve flag exists by design. Is that acceptable for teams that bootstrap machines with scripts (they would run one interactive `playbook sync` per machine)?
8. **Entry-point handlers from overlay distributions** are gated by `allow_code_from` only (no TOFU hash), relying on the consumer's dependency lock to pin the version. Should they also require TOFU on (distribution, version)?
9. **Directory-only layout with recursive `HOOK.md` discovery** differs from skills' flat one-level walk (`sources/filesystem.py:183`). Align skills later, or keep the difference?
10. **Frontmatter fields beyond the requested list** — `decisions`, `mandatory`, `priority`, `handlers` (and `RuleFrontmatter.lint_codes`). *Resolved*: §C, §D, §E and §F adopt them as defined in §A.2/§A.7.
11. **In-memory `sync --check`.** P2 hardens the scratch copy; rendering into memory (no copy at all) would remove the cost and the symlink/secret exposure entirely but touches every adapter's write path. Defer?

---

## §C — Rendering hooks per harness (adapter contract)

This section fixes how a resolved, applies_if-filtered `Hook` (§A) becomes harness output: the `Adapter` ABC change, the Claude Code managed merge into `.claude/settings.json` (L4), the generated OpenCode V1 shim (L5), the advisory degrade for every hook-less target (L1), the support matrix, and the Agent Harness round trip. It consumes the runtime contract of §D (`playbook-hook dispatch <event> --harness H [--project-dir DIR]`, §D.1; payload normalization, §D.2; the `playbook.hook.wire/1` result, §D.3.5; the single Stop coordinator, §D.5) and does not redefine it. Config, trust and validate references point at §B; the canonical model at §A.

Names this section introduces are marked *(shared name — proposed)*. Everything else is either a shared name from the task brief or a real symbol cited by `file:line` (worktree HEAD `c5c583b`).

### §C.0 Output inventory: who writes what, and how ownership is proven

| Output | Writer | Ownership proof | Cleanup | Drift rule |
| --- | --- | --- | --- | --- |
| `.claude/settings.json` → managed matcher groups under `hooks.<Event>[]` (plus opt-in `permissions.allow` strings, §C.2.8) | `ClaudeCodeAdapter.finalize` | **lockfile hash** of each managed element's canonical JSON (§C.2.3). JSON has no comment syntax, so no sentinel is possible (L8 exception) | stale managed elements are removed **inside `finalize`** by a span-preserving splice. The file is **never** unlinked | managed projection only (§C.2.6) |
| `.claude/hooks/playbook/launch.sh` *(shared name — proposed)* | `ClaudeCodeAdapter.finalize` | sentinel on line 1 (`# <SENTINEL>`) + whole-file lockfile hash. Written only over nothing or a sentinel-tagged file: a same-named user file or a symlink at the path or on a parent dir below the repo root is refused before any adapter writes, sync exiting 1 naming it (`adapters/_owned_files.py`, review finding #2) | `_scan_for_stale` once `.claude/hooks/playbook` is added to `_output_directories` (claude_code_adapter.py:155-159) | byte compare |
| `.opencode/plugins/playbook-hooks.js` *(shared name — proposed)* | `OpenCodeAdapter.finalize` (NEW override) | sentinel on line 1 (`// <SENTINEL>`) + whole-file lockfile hash. Written only over nothing or a sentinel-tagged file: a same-named user plugin or a symlink at the path or on a parent dir below the repo root is refused before any adapter writes, sync exiting 1 naming it (`adapters/_owned_files.py`, review finding #1) | inherited first-line sentinel scan once `.opencode/plugins` is added to `_output_directories` (opencode_adapter.py:96-104) | byte compare |
| `AGENTS.md` → trailing `## Guardrails` section | `AgentsMdAdapter.finalize` | existing file sentinel | existing `cleanup_stale` (agents_md_adapter.py:96-116) | byte compare |
| `.continue/rules/30-guardrail-<id>.md` | `ContinueAdapter` through the ABC default `write_hook` | existing rule sentinel (renderer `continue_rule`) | existing sentinel scan (continue_adapter.py:83-87) | byte compare |
| `rules/30-guardrail-<id>.md`, `.playbook/hooks/<id>/**`, manifest `kind = "hook"` | `AgentHarnessAdapter.finalize` | sentinel (first body line) / prior manifest for scripts | existing scan + `.playbook/hooks` (§C.6) | byte compare |
| `<git-path playbook-hooks>/interpreter` (per-worktree engine-interpreter pin) and `<git-path playbook-hooks>/machine.json` (per-worktree tool pins, §D.8.3) | `playbook sync` write mode (not an adapter), via `hook_runtime/pin.py` | outside the working tree, never committed | `interpreter`: never by sync (first writer wins); `playbook-hook doctor --repin` rewrites it. `machine.json`: rewritten at every write-mode sync | not checked (machine-local) |
| `.coding-agent-playbook/hooks/guard_config.json` *(shared name — proposed)* | `commands/sync.py` (sync-level, not an adapter), whenever `[hooks] enabled` and a hook-capable adapter is on | whole-file lockfile entry, `kind = "runtime"` (JSON has no sentinel) | deleted by the ownership-without-sentinel rule of §B.6 when hooks are disabled | byte compare |
| `.coding-agent-playbook/hooks/scripts/<hook-id>/**` (copied external-handler scripts) | `commands/sync.py` (sync-level), `shutil.copy2` byte copies | whole-file lockfile entries, `kind = "hook"`, `executable` bit | §B.6 ownership-without-sentinel rule | byte compare + exec bit |

**`guard_config.json` location (locked; closes QC-5).** It is a **sync-level** output at one harness-neutral committed path, `.coding-agent-playbook/hooks/guard_config.json`, because an OpenCode-only repo needs it and SPEC §10.6.4 forbids the OpenCode adapter from writing under `.claude/`. `.playbook/hooks/` is not used: §C.6 already owns `.playbook/` for the agent_harness sidecar. The dispatcher finds the file from the repo root it discovers (§D.2.4), so no path travels in argv. Copied external-handler scripts live beside it, and their argv in `guard_config.json` is repo-relative; the interpreter comes from the pin or `machine.json`. guard-generated-outputs and control-plane-guard protect the whole `.coding-agent-playbook/hooks/` tree (§E.1).

### §C.1 Adapter ABC change and sync dispatch

#### §C.1.1 ABC additions (adapters/base.py)

All four additions are **concrete defaults**. An `@abstractmethod` would break third-party adapters registered through `coding_agent_playbook.adapters`. This is the same reasoning that keeps `write_skill` concrete (base.py:39-47).

```python
class Adapter(ABC):
    name: str

    #: Canonical event -> canonical decisions this adapter can render natively.
    #: Empty mapping (the default) = advisory-only adapter. playbook check/validate
    #: read it from the entry-point class; see §C.5 for the built-in values.
    hook_support: ClassVar[Mapping[str, frozenset[str]]] = {}  # (shared name — proposed)

    def begin_sync(
        self, repo_root: Path, prior_lock: Lockfile | None
    ) -> None:  # (shared name — proposed)
        """Called once per sync before any write_*. Default: no-op.
        Adapters that own sub-file regions (Claude settings.json) read their
        previous ownership hashes from ``prior_lock`` here."""

    def write_hook(self, hook: ResolvedHook, repo_root: Path) -> list[Path]:
        """Degrade a hook to advisory text.

        Default mirrors write_skill -> to_prompt: the hook's advisory rule
        (§A.8) is routed through this adapter's own rule channel. Hook-capable
        adapters override and fall back to ``super().write_hook`` for hooks they
        cannot enforce (event unreachable, or ``supports`` excludes them). A hook
        with an empty body has no advisory rule and degrades to nothing.
        """
        rule = hook.advisory
        return [] if rule is None else self.write_rule(rule, repo_root)

    def managed_lock_entries(self) -> list[LockEntry]:  # (shared name — proposed)
        """Sub-file ownership records produced by the last finalize(). Default: []."""
        return []
```

`ResolvedHook.advisory` is `Hook.to_advisory_rule()` (types.py, beside `Skill.to_prompt` at types.py:210), whose contract — `guardrail-<id>`, priority 30, scope, `hook_advisory` body, `Rule | None` — is locked once in §A.8 and not redefined here. `write_hook` takes the `ResolvedHook` produced by `hook_policy.resolve_effective_hooks` (§A.7), after its body is rendered (§C.1.3).

**Disagreement flagged (QC-10).** The research codemap recommends that `write_hook` be a no-op rather than an advisory degrade, so that enforcement never quietly becomes advice. L1 locks the degrade, and this section follows L1. The concern is mitigated in three ways:

1. Every advisory block states where the hook is enforced and that elsewhere it is advice (§C.4.1).
2. `playbook check` lists each hook per adapter with the §A.8 label set (`enforced` / `degraded` / `advisory` / `—`), using `hook_support`.
3. The `playbook sync` summary prints the counts.

#### §C.1.2 Built-in adapter overrides

| Adapter | `write_hook` | `hook_support` | Advisory channel |
| --- | --- | --- | --- |
| `claude_code` | buffers native hooks for `finalize`; others go to `super()` | all 9 canonical events (§C.5) | `write_rule` → buffered into `.claude/CLAUDE.md` (only for hooks it cannot enforce, normally none) |
| `opencode` | buffers native hooks for `finalize`; returns `[]` for the rest | `pre_tool_use`, `post_tool_use`, `session_start`, `stop` (degraded). `pre_compact` is not registered: its only decision is `none` (§A.2) and OpenCode has no transcript to checkpoint | none of its own: OpenCode reads `AGENTS.md`, which carries every hook's advisory (opencode_adapter.py:47-56 routes rules the same way) |
| `agents_md` | buffers **every** enabled hook into the Guardrails section | `{}` | `## Guardrails` (§C.4.2) |
| `continue` | inherits the ABC default | `{}` | `.continue/rules/30-guardrail-<id>.md` |
| `agent_harness` | buffers for `finalize` (§C.6) | `{}` | `rules/30-guardrail-<id>.md` + sidecar |

`agents_md` must override even though it inherits a `write_rule`. Routing through `write_rule` would interleave advisories with rule sections by priority, but L1 wants one contiguous Guardrails section.

#### §C.1.3 Sync dispatch (commands/sync.py, orchestrator.py)

**orchestrator.py**

- `Collision.kind` docs (orchestrator.py:53) gain `"hook"`.
- `OverlayResolver` gains `resolve_hooks` beside `resolve_skills` (orchestrator.py:99-105), exactly as §A.6 defines it: it does **not** delegate to `_resolve` (orchestrator.py:107-135), because `hook_policy.merge_hook_layers` needs every layer's definition of an id.
- `artifact_id_of` (orchestrator.py:138-153) needs no change as long as `HookFrontmatter` is a dataclass with `id` (§A).
- `SyncContext` gains `hooks_resolved: list[Hook] = field(default_factory=list)` after `skills_resolved` (orchestrator.py:236).
- `from_repo` adds `all_hooks = artifact_source.list_hooks()` beside orchestrator.py:268-270 and `hooks_resolved = resolver.resolve_hooks(...)` beside orchestrator.py:280-282, then passes it to the constructor (orchestrator.py:286-297). It also accepts the P8 `tolerate_hook_errors` and the P2 `facts` keywords.

**commands/sync.py, `_run_sync`** (sync.py:151-191). Each change, by location:

| Location | Change |
| --- | --- |
| sync.py:121 | unchanged: `_filter_applies_if` is **not** widened (§A.7) |
| after sync.py:157 | add `hooks, skipped = hook_policy.resolve_effective_hooks(ctx.hooks_resolved, rules, parse_hooks_config(ctx.config.extra_tables.get("hooks", {})), parse_guardrails_config(ctx.config.extra_tables.get("guardrails", {})), ctx.facts, ctx.repo_root)` — the single gating path (§A.7: on-formula, `applies_if`, `linked_rule`, guardrails merge, `supports ∩ [hooks] adapters`). `Config` has no `hooks` attribute; the tables live in `extra_tables` (P6). `skipped` feeds the sync summary (§C.1.5) |
| after sync.py:170 | add `hooks = [h.with_rendered_body(_render_hook_body(h, base_context, base_env)) for h in hooks]` (`with_rendered_body` sets `advisory` from the rendered body, §A.8). Only the advisory **body** of a `HOOK.md.j2` is rendered, with `base_env` (`is_prompt_context=False`, so `rule()` is unavailable, sandboxed per P1). Frontmatter, handler commands and scripts are never rendered |
| before sync.py:177 | add `prior_lock = ctx.state_source.load_lockfile()` |
| before the adapter loop | the ownership preflight, beside the `settings.json` one: for each adapter, `check_engine_owned(repo_root / path, repo_root)` on every path of `adapter.planned_runtime_outputs(hooks)` (the `runtime_outputs` its `finalize` will write for these hooks; the ABC default is every declared one once a hook targets the adapter). A user file or a symlink there raises `UserOwnedFileError`: exit 1 naming the file, nothing written, in every mode (review findings #1, #2) |
| sync.py:178-185 | per adapter: first `adapter.begin_sync(ctx.repo_root, prior_lock)`. After the skills loop (183-184), add `for hook in hooks: written.extend(adapter.write_hook(hook, ctx.repo_root))`. Then the existing `finalize` (185). Then `managed.extend(adapter.managed_lock_entries())` |
| after sync.py:185 | sync-level writes (not adapters), when `[hooks] enabled` and a hook-capable adapter is on: `guard_config.json` from `[h.to_json() for h in hooks]` plus the §D.8.2/§E.0.5 tables, and the copied external-handler scripts (§C.0) |
| sync.py:187-191 | `cleanup_stale` loop unchanged; it always runs after **every** adapter's `finalize`. `_run_sync` now returns the single `SyncResult(written, removed, provenance, managed)` of P4 |
| sync.py:93-118 | the single signature `_build_lockfile(written, repo_root, engine_version, provenance, managed)` (P4). A path that has any `managed` entry gets **no** whole-file entry; its scoped entries are appended instead. This stops `playbook check` (check.py:140-155) from reporting every user edit to `permissions` or `env` as drift |
| sync.py:205-210 | in write mode only, after the lockfile is saved: `pin.ensure_interpreter_pin(ctx.repo_root)` and `pin.write_machine_pins(ctx.repo_root, ...)` (`hook_runtime/pin.py`, §C.2.7, §D.8.3) run when `[hooks]` is enabled and `claude_code` or `opencode` is an enabled adapter. Then hook summary lines (§C.1.5) |
| sync.py:246 | `_run_check` reads `SyncResult` (P4) and reports the `removed` set (P2) |

`_filter_skills` (sync.py:137-141) is untouched.

**Ordering.** Hooks are dispatched after skills and before `finalize`, because both hook-capable adapters buffer and compose in `finalize`.

#### §C.1.4 LockEntry extension

P4 lands the whole v2 field set once (§B.6); this section is the user of `scope: str = ""` *(shared name — proposed)*. The empty string means the entry covers the whole file, which is the current behavior.

Scoped entries:

| Field | Value for a managed hook registration |
| --- | --- |
| `path` | `.claude/settings.json` |
| `scope` | `json:/hooks/<ClaudeEvent>` (a JSON Pointer to the **array**; the element index is deliberately not recorded, because user inserts shift it) |
| `sha256` | `sha256(canonical_json(element))` with `canonical_json = json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()` |
| `bytes` | length of the canonical bytes |
| `kind` / `adapter` / `source` / `artifact_id` | `"runtime"` / `"claude_code"` / `""` / `"registration:<canonical_event>"` (the §B.6 values) |

`Lockfile.from_dict` (lockfile.py:34-48) defaults `scope` to `""`, so lockfiles from before the bump still load. `_LOCKFILE_SCHEMA` (sync.py:35) is bumped once, together with L7's fields.

Edits to managed elements of `.claude/settings.json` are owned by **control-plane-guard** (§E.1), which already simulates the JSON diff; guard-generated-outputs skips paths whose entries are all scoped.

#### §C.1.5 Sync output

`playbook sync` gains these lines (extends SPEC §12.2):

```
✓ Hooks: 31 enabled (claude_code: 31 enforced; opencode: 27 enforced, 3 degraded, 1 advisory; continue: 31 advisory)
✓ .claude/settings.json: 2 managed entries updated, 0 removed (user keys untouched)
! .opencode/plugins/playbook-hooks.js changed: restart OpenCode to load it
! warning: .claude/settings.json hooks.PreToolUse: managed entry was edited by hand; restored. Change hooks in playbook/hooks/ or [hooks], then run 'playbook sync'.
```

### §C.2 Claude Code (L4)

#### §C.2.1 Rendered shape

There is **one managed matcher group per canonical event** that has at least one enabled hook (L3). Each group holds **one** command handler, and fan-out happens in-process in the dispatcher. `SessionStart` is registered whenever **any** Claude registration exists, even if no `session_start` hook is enabled. It carries the dispatcher's session bootstrap (§D.6.1 TTL sweep, the §E.1 heartbeat) and is the launcher's single visible-failure channel (§C.2.7). Timeouts in the example are illustrative values of the §D.4 formula (default pack, no execution stages).

Example (user-owned keys and the user's own hook group are preserved as-is; managed groups are the ones with the launcher command):

```json
{
  "permissions": { "deny": ["Read(./.env)"] },
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "~/.claude/hooks/command-rewrite.sh" } ] },
      { "matcher": "Bash|Edit|Glob|Grep|MultiEdit|NotebookEdit|PowerShell|Read|Write",
        "hooks": [ { "type": "command",
                     "command": "sh \"${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}/.claude/hooks/playbook/launch.sh\" dispatch pre_tool_use --harness claude_code",
                     "timeout": 32 } ] }
    ],
    "PostToolUse": [
      { "matcher": "Bash|Edit|MultiEdit|NotebookEdit|PowerShell|Write",
        "hooks": [ { "type": "command",
                     "command": "sh \"${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}/.claude/hooks/playbook/launch.sh\" dispatch post_tool_use --harness claude_code",
                     "timeout": 12 } ] }
    ],
    "SessionStart": [
      { "hooks": [ { "type": "command",
                     "command": "sh \"${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}/.claude/hooks/playbook/launch.sh\" dispatch session_start --harness claude_code",
                     "timeout": 6 } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command",
                     "command": "sh \"${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}/.claude/hooks/playbook/launch.sh\" dispatch stop --harness claude_code",
                     "timeout": 5, "statusMessage": "playbook: verifying before stop" } ] }
    ]
  }
}
```

**Emission rules** (pure functions in `coding_agent_playbook/hook_registrations.py` *(shared name — proposed; distinctive on purpose — the event/tool-class/support tables themselves live only in `hook_policy.py`, §A.11)*, stdlib-only; `plan_registrations(hooks, adapter) -> list[HookRegistration]` and `to_claude_group(reg) -> dict` *(shared names — proposed)*):

- **Handler keys.** Exactly `type`, `command`, `timeout`, and `statusMessage` on `stop` / `subagent_stop` only. All of these are in the SchemaStore schema.
  - Never `if`: one rule per handler, and a non-tool event with `if` never runs.
  - Never `async` on a deciding registration. **One exception (amends L3; accepted, OQ-19):** at most one extra `async: true`, non-deciding, output-free `PostToolUse` registration (matcher `*`, lock `artifact_id = "registration:post_tool_use:async"`), rendered only when an enabled hook whose `decisions == [none]` binds a handler declaring `ASYNC_SAFE = True` (today only local-audit-log's `activity_log`). Claude delivers async results on the next turn, so that dispatch writes nothing to stdout (asserted by test).
  - Never `args` / exec form: Windows needs a real `.exe` (§C.2.7).
  - Never `http`, `prompt`, `agent` or `mcp_tool` (L6).
  - Never `onFailure` in default mode: it is absent from SchemaStore and needs Claude ≥ 2.1.295. **Overlay strict mode** (one merged question, §K): `"onFailure": "block"` is rendered on a registration iff an enabled member on that event has `on_error: deny` (overlay-only, H10), never on `pre_tool_use` unless the overlay opts in explicitly; such a registration's command appends `--strict-launch` (§C.2.7) so the launcher exits 1 — which `onFailure` turns into a block — on a missing pin or a crash. `doctor` checks `claude --version` ≥ 2.1.295 before this is relied on (older CLIs ignore the key).
- **Command.** Shell form, which Claude runs as `sh -c` on POSIX and under Git Bash on Windows. The command is exactly `sh "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}/.claude/hooks/playbook/launch.sh" [--strict-launch] dispatch <event> --harness claude_code` — the §D.1 argv, with no `--config` or digest, so registration bytes never change when only `guard_config.json` changes.
  - `${CLAUDE_PROJECT_DIR:-…}` is deliberately **not** Claude's exact `${CLAUDE_PROJECT_DIR}` placeholder token. The shell expands it from the environment variable Claude sets for hooks; when a harness that reads this file does not set it (§C.5.2), the fallback is the git top level, not the cwd, so the path is cwd-independent (git runs only on that fallback).
  - A fixture test pins this behavior with the variable set, unset, and unset with the cwd in a subdirectory.
- **Timeout** (seconds): the **one formula owned by §D.4** — `ceil(deadline_ms[event] / 1000) + 2`, where `deadline_ms` is rendered into `guard_config.json`. OpenCode `timeout_ms` is the same number × 1000. Sync asserts, and a unit test checks, `registration_timeout_s * 1000 ≥ deadline_ms[event] + 1000` for every rendered event, so the harness never kills the dispatcher before its watchdog has written a decided result.
  - The explicit `SessionEnd` timeout raises Claude's shared 1.5 s budget.
  - The harness timeout is only a backstop, and it fails open.
- **Group order is deterministic.** The managed group keeps its existing array index. A new group is appended after the user's groups. New event keys are appended to `hooks` in canonical event order (§C.2.2).

#### §C.2.2 Event names and the matcher union

| Canonical event | Claude event | Matcher |
| --- | --- | --- |
| `session_start` | `SessionStart` | omitted (bootstrap needs `startup\|resume\|clear\|compact\|fork`) |
| `user_prompt_submit` | `UserPromptSubmit` | omitted (Claude silently ignores it) |
| `pre_tool_use` | `PreToolUse` | tool-class union |
| `post_tool_use` | `PostToolUse` | tool-class union |
| `post_tool_use_failure` | `PostToolUseFailure` | tool-class union |
| `stop` | `Stop` | omitted (no matcher) |
| `subagent_stop` | `SubagentStop` | union of member `agent_type` allowlists, or omitted when any member is unfiltered; a union containing `:` (plugin-scoped `plugin:agent` names) is anchored `^(?:…)$` |
| `pre_compact` | `PreCompact` | union of `manual`/`auto`, or omitted when both |
| `session_end` | `SessionEnd` | omitted |

**Tool classes.** The matcher union is computed over the members' tool classes, using the **single vocabulary and name table of §A.2** (`shell`, `edit`, `write`, `notebook_edit`, `read`, `search`, `web`, `subagent`, `mcp`; `other` is runtime-only), read from `hook_policy.TOOL_CLASS_NAMES`. The same table drives the OpenCode prefilter (§C.3); `notebook_edit` has no OpenCode tool and `mcp` is unsupported there (validate warns; `playbook check` shows `degraded`). A member whose `tools` and `tool_names` are both empty matches every tool.

**Matcher string:**

- If any member matches every tool, the matcher is `"*"`.
- If it contains only plain identifiers, it is a sorted `A|B|C` list. Claude treats a matcher made only of letters, digits, `_`, `-`, space, comma and `|` as an exact list (hyphenated names exact since 2.1.195), so `Edit` does **not** match `NotebookEdit`.
- If it contains a regex class (`mcp`), the whole matcher is anchored: `^(?:Bash|Edit|…|mcp__.*)$`. Any regex character turns the entire matcher into an unanchored JS regex.

#### §C.2.3 Ownership: lockfile hashes, never markers

A managed element is identified **only** by its canonical-JSON hash recorded in the prior lockfile (§C.1.4). The engine never writes comments (strict JSON) or marker keys. SchemaStore declares `additionalProperties: false` on handlers and matcher groups, and Claude Code's handling of unknown keys is undocumented.

The launcher path token `/.claude/hooks/playbook/launch.sh` inside a handler `command` is a **secondary** signal. It is used only to classify conflicts (§C.2.5), never to claim ownership silently.

Teammates share ownership through the committed `.coding-agent-playbook.lock`. When Bob pulls Alice's sync, his sync finds the groups by hash, plans no change, and writes nothing except his own pin.

#### §C.2.4 Merge algorithm (span-preserving)

The algorithm lives in `src/coding_agent_playbook/adapters/claude_settings.py` *(NEW; shared name — proposed)*. It is pure, stdlib-only, and testable without an adapter. The public entry point is `merge_managed_entries(text: str | None, desired: Mapping[str, list[dict]], prior: list[LockEntry]) -> MergeResult(text, changed, warnings, entries)`. Errors raise `SettingsMergeError(path, line, col, message)`.

1. **Read.** If `.claude/settings.json` is absent, the document is `{}` and new files use a 2-space indent and LF line endings. If the file holds only whitespace, it is treated as `{}` with a warning.
2. **Parse strictly.**
   - Use `json.loads` with `object_pairs_hook` rejecting duplicate keys and `parse_constant` rejecting `NaN` / `Infinity`.
   - Any failure (comments and trailing commas are syntax errors in Claude Code too) raises `SettingsMergeError` with the path and position. Sync exits 1 and **writes nothing**.
   - The top level must be an object. `hooks`, if present, must be an object of arrays of objects. Otherwise the error carries the offending value and the expected shape.
3. **Plan on the semantic document.** For each Claude event `E`:
   - `want` = the desired managed group, or none.
   - `owned` = the elements of `hooks[E]` whose canonical hash equals a prior-lock entry with `scope == "json:/hooks/E"`.
   - `suspect` = the remaining elements whose every handler `command` contains the launcher token.
   - `mixed` = elements in which a launcher handler sits next to non-launcher handlers.
4. **Decide per event** (also see §C.2.5):

   | State | Action |
   | --- | --- |
   | `mixed` non-empty | `SettingsMergeError` naming `hooks.E[i]`: "move your handler to its own matcher group" |
   | `want` equals one element of `owned` ∪ `suspect` by canonical equality | no-op. Extra copies are deleted with a warning |
   | `want` present, `owned` ∪ `suspect` non-empty but not equal | replace the first such element in place and delete the rest. A `suspect` replacement warns "edited by hand; restored" |
   | `want` present, nothing found | append `want` at the end of `hooks[E]` (an info line if the prior lock had an entry: "re-added") |
   | `want` absent | delete every `owned` ∪ `suspect` element. An array that becomes empty is removed, and an empty `hooks` object is removed |

5. **No-op short circuit.** If the plan is empty, the file is **not rewritten**. This one rule gives byte stability for user keys, user hook groups, user formatting, key order inside managed groups (canonical equality ignores it) and escape sequences.
6. **Apply textually.**
   - A minimal strict-JSON span scanner (`JsonSpanIndex` *(proposed)*, string-aware, around 150 lines) records byte spans for top-level members, `hooks` members, event-array elements, and the elements of every **managed array pointer**.
   - Edits are replace-element, delete-element (with its separating comma), append-element, append-member-to-`hooks` and append-`hooks`-member, plus the generic **managed string elements of a JSON array at pointer P** operation: append an engine string, delete an engine string whose lock entry says it is ours, create missing parent objects/arrays, never touch user elements. The managed pointers are exactly `/hooks/<Event>` (objects, steps 3–4) and the string arrays `/permissions/allow`, `/permissions/deny`, `/sandbox/filesystem/denyRead`, `/sandbox/network/allowedDomains` (one lock entry per string, `scope = json:<pointer>`, §B.6). They are spliced into the original text.
   - Inserted fragments are `json.dumps(fragment, indent=<detected>, ensure_ascii=False)`, re-indented to the insertion depth.
   - The detected style comes from the file: indent width or tab from the first indented line, CRLF vs LF, a trailing newline, and a UTF-8 BOM (kept).
   - Bytes outside the spliced spans are never touched.
7. **Self-check.** Re-parse the result and assert semantic equality with the planned document. On a mismatch, raise `SettingsMergeError` and do not write. A file whose meaning differs from the plan never reaches disk.
8. **Write atomically, guarding against races.**
   - Re-read the file just before writing. If its bytes changed since step 1 (for example, Claude Code persisted a permission approval to `projectSettings`), redo steps 2–7 once, then fail.
   - Write bytes, not text, through a byte-level variant of `_atomic_write_text` (sources/filesystem.py:200-211). Its `write_text` would translate newlines on Windows.
9. **Return.** `finalize` returns `[settings_path]` **only when the file was written**. `managed_lock_entries()` always returns the scoped entries for every desired group, including no-op ones.

`ClaudeCodeAdapter.finalize` (claude_code_adapter.py:131-153) is split into `_compose_claude_md` and `_compose_settings`. The early return at :140-141 is removed, so a hooks-only repo with no rules still gets its registrations.

`cleanup_stale` (claude_code_adapter.py:161-189) never touches `settings.json`. Managed-element removal is a `finalize` concern because it is sub-file.

#### §C.2.5 Stale entries and hand edits

**Stale.** A hook that is disabled, filtered out by `applies_if`, or removed from the canonical source drops its event's `want`, or changes it. Step 4 deletes or replaces the prior-hash element. Removing the **last** managed element leaves the file in place (possibly `{}`). The adapter never deletes a file that users and Claude Code co-own.

**Hand edit: locked as restore-and-warn.** A managed group is generated output, exactly like `.claude/commands/<slash>.md`, which sync already overwrites. A hand edit is either:

- intent that belongs in canonical sources or `[hooks]` (the warning names both), or
- tampering, for example an agent narrowing the matcher to drop `Bash`. Restoring is the secure default.

Either way, `sync --check` reports the edit as drift before the restore, so CI catches it.

**Mixed group → error.** It is the only case where restoring would destroy user content.

**Deleted managed group.** Deleting a managed group is not an off switch. It is re-added. Disabling goes through `[hooks]`, which control-plane-guard protects.

#### §C.2.6 Drift semantics for JSON entries

Because of the no-op short circuit (step 5), the existing whole-byte compare in `_run_check` (sync.py:249-266) is already correct for `settings.json`. The scratch copy (sync.py:239) contains the user's keys and the committed lockfile, so the re-merge is rewritten, and therefore reported, **only** when the managed projection differs. `playbook check` (check.py:140-155) gains a scoped branch: for `scope = json:<pointer>`, it parses the file and looks for an element under the pointer whose canonical hash equals `sha256`.

| On-disk state | `sync --check` | `playbook check` |
| --- | --- | --- |
| user edited `permissions`, `env`, `model`, … | clean | clean |
| user reformatted the file or reordered keys | clean | clean |
| user added their own hook group | clean | clean |
| managed group hand-edited | drift: `.claude/settings.json` "Generated content differs" | `managed entry edited: .claude/settings.json#/hooks/PreToolUse` |
| managed group deleted | drift | `managed entry missing: …` |
| hook disabled canonically, group still on disk | drift | n/a (the lockfile is rewritten by the next sync) |
| invalid JSON | exit 1, "cannot verify: invalid JSON at L:C" | `unreadable: .claude/settings.json` |
| `launch.sh` missing or edited | drift (whole-file entry) | `missing` / `hash mismatch` |

#### §C.2.7 Interpreter path: LOCKED design

**The tension.** The catalog wants the hook launched by an absolute, pinned interpreter, with `-I`, never bare `python3`. That avoids:

- the Anaconda 3.8 `python3` without `tomllib`;
- the Windows Store stub, which fails open;
- stdlib shadowing by an agent-written `fnmatch.py`;
- `PYTHONPATH` / `PYTHONSTARTUP` injection through the settings `env` key.

But `.claude/settings.json` is committed and shared across machines.

**Decision: the committed launcher is machine-independent, and a per-worktree pin lives outside the working tree.**

- `settings.json` references only `.claude/hooks/playbook/launch.sh`. That is a generated, committed, lockfile-tracked POSIX `sh` script that is identical on every machine.
- The launcher reads the absolute interpreter from `<git-path playbook-hooks>/interpreter`. That is the same per-worktree, mode-0700, never-committed state root §D.6.1 uses: `.git/playbook-hooks/` in a main checkout and `.git/worktrees/<name>/playbook-hooks/` in a linked worktree. It is the **only** engine-interpreter pin; `machine.json` beside it holds tool pins only (§D.8.3).
- It then runs `<pin> -I -m coding_agent_playbook.hook_runtime "$@"`.

§D.1 makes `python -m coding_agent_playbook.hook_runtime` equivalent to the `playbook-hook` console script. Registrations deliberately use `-I -m` and not the console-script wrapper, because the wrapper's shebang carries no `-I`.

| Option | Committed bytes machine-independent | Fresh clone | Verdict |
| --- | --- | --- | --- |
| A. absolute interpreter written into `settings.json` | **no**: `sync --check` drifts on every other machine and in CI, and `$HOME` paths leak into the repo | works only on the machine that synced | rejected |
| B. registration in `settings.local.json` | yes (nothing committed) | **no hooks, and nothing reviewable**. Claude Code itself rewrites this file (permission approvals). Since v2.1.211 it lives at the git repo root (main checkout root for worktrees), so one file is shared by all worktrees and a per-worktree venv pin collides | rejected |
| C. bare `playbook-hook` resolved on `PATH` | yes | silent fail-open whenever the venv's `bin/` is not on Claude's `PATH` (IDE launches); PATH hijack; no `-I` | rejected |
| **D. committed launcher + per-worktree pin under the git dir** | **yes** | **inactive until someone runs `playbook sync` in that worktree**: explicit and visible. The pin enables **engine builtins only**; it is not a trust approval (any write-mode sync, including an agent-run one, may write it), and repo- or overlay-controlled code still needs the §B.4 trust store. A `claude -p` run in a fresh CI clone stays inert | **locked** |

**Rendered launcher.** The sentinel is on line 1, which is possible because the launcher is invoked as `sh launch.sh`, so it needs neither a shebang nor an exec bit (P3: engine-generated files carry no shebang). It uses builtins only on the success path, and derives the repo root from its own path so it never depends on the hook cwd:

```sh
# AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync'
# Claude Code launcher for playbook-hook (specs/prK-lifecycle-hooks.md §C.2.7). Machine-independent:
# the interpreter comes from the per-worktree pin that `playbook sync` writes under the git dir.
# Exit status is 0, or 2 only for a dispatcher-decided deny (signalled as 10), so a broken install
# can never block a tool call. --strict-launch (overlay strict mode) exits 1 on failure instead.
strict=
if [ "${1:-}" = --strict-launch ]; then strict=1; shift; fi
root=${0%/.claude/hooks/playbook/launch.sh}
[ "$root" != "$0" ] || root=${CLAUDE_PROJECT_DIR:-$PWD}
gitdir=$root/.git
if [ -f "$gitdir" ]; then                       # linked worktree: .git holds "gitdir: <path>"
  IFS= read -r line < "$gitdir" || :
  gitdir=${line#gitdir: }
  case $gitdir in /* | [A-Za-z]:*) ;; *) gitdir=$root/$gitdir ;; esac
fi
state=$gitdir/playbook-hooks
py=
if [ -r "$state/interpreter" ]; then IFS= read -r py < "$state/interpreter" || :; fi
if [ -n "$py" ] && [ -x "$py" ]; then
  "$py" -I -m coding_agent_playbook.hook_runtime "$@"
  rc=$?
  case $rc in 0) exit 0 ;; 10) exit 2 ;; esac   # a raw 2 (usage, interpreter error) is NOT a deny
  why="dispatcher exited $rc"
  printf '%s %s %s\n' "$(date +%s)" "${2:-?}" "$why" 2>/dev/null >> "$state/launcher.log"
else
  why="no interpreter pin"
fi
if [ -n "$strict" ]; then exit 1; fi              # onFailure:"block" turns this into a block
if [ "${2:-}" = session_start ]; then
  printf '{"systemMessage":"playbook lifecycle hooks are INACTIVE (%s). Run: playbook-hook doctor","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"playbook lifecycle hooks are not active this session; apply the AGENTS.md Guardrails section yourself."}}\n' "$why"
fi
exit 0
```

**Failure policy: fail open, visibly, once per session.**

- **Exit-code contract.** The dispatcher signals a rendered deny with the private code `10` (§D.3.5); the launcher maps `10 → 2` and `0 → 0`. Any other dispatcher code — including a raw `2` from a usage error, a version-skewed engine or the interpreter itself — is logged and mapped to `0`, because a raw 2 on PreToolUse would block every tool call with usage text (only on Stop/SubagentStop is an exit 2 with a "No such file or directory" stderr non-blocking).
- A missing pin, a non-executable pin, or a dispatcher exit other than 0 or 10 (for example an `ImportError` after the engine was uninstalled from the pinned env) → exit 0, except under `--strict-launch` (exit 1).
- Only the `session_start` registration speaks:
  - a `systemMessage` to the user;
  - `additionalContext` to the model, pointing at the AGENTS.md Guardrails advisory.
- Crashes on hot-path events are appended to `launcher.log`. The next SessionStart dispatcher run reports and rotates that log (§D.6.1), so a pre-tool crash is not invisible.
- Outside strict mode the launcher never blocks. Guard-class failure semantics (internal error → `ask`, or `deny` when headless) live **inside** the dispatcher (§D.4), which exits only 0 or 10.

**Pin lifecycle.** The helpers live in `coding_agent_playbook/hook_runtime/pin.py` (listed in the §D.1 module table; jinja2-free so `doctor` reuses them): `ensure_interpreter_pin`, `write_machine_pins`, `read_interpreter_pin`.

| When | Behavior |
| --- | --- |
| `playbook sync` (write mode; also via `playbook init`) | write `sys.executable` **unresolved** (a venv's `bin/python` is a symlink, and resolving it escapes the venv and its site-packages), plus a newline, mode 0600 in a 0700 dir. Only when the pin is **absent or not an executable file**: first writer wins, so the pin never flaps between a venv, pre-commit's cached env and `uvx` |
| `playbook sync --check`, eval scratch dirs | never written |
| `playbook-hook doctor` | verifies the pin exists and is executable, that `<pin> -I -c "import coding_agent_playbook.hook_runtime"` succeeds, and that its version equals `guard_config.json`'s `engine_version` |
| `playbook-hook doctor --repin [PYTHON]` *(flag proposed)* | overwrites (default: doctor's own `sys.executable`) |
| `sys.executable` looks ephemeral (path under a uv cache `archive-v0` or pipx temp root) | sync warns: "pinned an ephemeral interpreter; run `playbook-hook doctor --repin <stable python>`" |
| non-git repo | no git dir, so no pin and hooks stay inactive; sync warns. **Hooks are git-only in v1** (closes QC-9; §D.6.1 has no non-git state root) |

**Hot path.** The success path costs `sh -c` → `sh launch.sh` (builtins only) → Python `-I` start-up plus the §D import-light dispatcher. Two shell starts add roughly 2–4 ms against the catalog's ≤ 100 ms p95 per event. `date` runs only on failure.

#### §C.2.8 `settings.local.json` and `permissions`

- **`settings.local.json`: never written** (v1). It is Claude Code's personal file: auto-gitignored, written by Claude on approvals, and located at the repo root shared across worktrees. The codemap also says the engine must not write it. `doctor` reads it only to report `disableAllHooks: true`.
- **`permissions.allow` (remediation commands): opt-in, off by default.** It is enabled by `[hooks] render_remediation_allow = true` *(shared name — proposed; a `[hooks]` key, §B.1)*. When on, the same managed-array machinery (§C.2.4, scope `json:/permissions/allow`, one scoped lock entry per string) appends a **fixed engine list** of commands that do not execute repo-controlled code:
  - `Bash(playbook validate)`
  - `Bash(playbook check)`
  - `Bash(playbook sync --check)`
  - `Bash(playbook sync)`
  - `Bash(ruff check .)`
  - `Bash(ruff format --check .)`

  `python -m pytest -q` and `python -m mypy` are **excluded** even though the catalog lists them. They run `conftest.py` and mypy plugins, which is exactly the repo-controlled execution the trust principle forbids auto-allowing.

  Why opt-in:
  - an allow list is a committed privilege grant to every teammate, and a default would mean an engine upgrade silently widens permissions;
  - L2 lets overlays only **add to deny** tables, so overlays can never contribute allow entries;
  - L6 forbids hook-issued `allow`. A reviewed, rendered config entry is not a hook decision, but the default must still not widen privilege.

  User-owned allow entries are never touched.
- **`permissions.deny` and `sandbox.*` (native twins).** The mechanism is the generic managed-array operation of §C.2.4 (scopes `json:/permissions/deny`, `json:/sandbox/filesystem/denyRead`, `json:/sandbox/network/allowedDomains`; one lock entry per string). Which twins are rendered, and whether they follow their guard's enablement, is specified by §E.4/§E.5. This section only guarantees the merge contract: append-only for engine entries, user entries untouched, and engine entries removed when their guard is disabled. Scalar sandbox switches (`sandbox.enabled`, `failIfUnavailable`, `network.strictAllowlist`) are **not** rendered into the project file; the last is user/managed-scope only. Without them the `sandbox.*` arrays are speed bumps (§E.4).

#### §C.2.9 Claude-specific caveats (documented, checked by `doctor` where possible)

- **Launch directory.** Project settings are read only from the session's primary working directory's `.claude/`, with no parent fallback. Launching `claude` in a subdirectory loads no playbook hooks. The briefing heartbeat (§E.1) cannot run there either, so this goes in the README.
- **Trust and `-p`.** Interactive sessions hold all hooks until the folder's trust dialog is accepted. `-p` / SDK runs count as trusted and run committed hooks immediately, which is why design D's "inert until local sync" matters for CI clones.
- **Cloud sessions.** Multi-repo Anthropic-hosted cloud sessions read only `enabledPlugins` / `extraKnownMarketplaces` from repo settings. Hooks there are absent (verified correction).
- **Policy kill switches.** `disableAllHooks` (any file), managed `allowManagedHooksOnly` and `strictPluginOnlyCustomization: ["hooks"]` silently drop project hooks. `doctor` reads the settings files plus the managed-settings paths and reports which one applies.
- **Hot reload.** Settings-file hook edits apply to the **running** session (research, verified; there is no startup snapshot). A `playbook sync` takes effect without a restart — and so does an agent edit that removes a managed group, which is why control-plane-guard's PreToolUse deny on structured edits of the settings files is the in-session control (§E.1; QC-12 closed).
- **Windows.**
  - Supported only with Git Bash, which is what Claude Code uses for the Bash tool and for shell-form hooks.
  - A PowerShell-only install runs `sh …` under PowerShell, the command fails, and Claude shows its non-blocking "hook error" notice: fail-open (QC-4).
  - `tool_input.file_path` arrives with backslashes. Normalization is the dispatcher's job (§D.2.4).
- **Concurrent handlers.** All matching handlers run in parallel, including the user's own (for example a command-rewriting hook). The playbook group sees the original `tool_input`, never another hook's `updatedInput`. **Known gap:** any user, plugin or skill hook that returns `updatedInput` can change the executed input after the playbook verdict (the last `updatedInput` to finish wins); ordering cannot close this because Claude runs hooks in parallel. control-plane-guard treats the creation of new hook carriers as a policy edit (§E.1).

### §C.3 OpenCode V1 (L5)

#### §C.3.1 File and module rules

- **Exactly one file**, `.opencode/plugins/playbook-hooks.js`.
  - It is written only over nothing or a file with the line-1 sentinel. A user's plugin of that name, a non-regular file, or a symlink at the path, `.opencode` or `.opencode/plugins` is refused before any adapter writes (sync exits 1 naming it; `--check` prints `Cannot verify <path>: <reason>.`), never overwritten or written through.
  - It is auto-discovered by V1's non-recursive `{plugin,plugins}/*.{ts,js}` scan, so `opencode.json(c)` is never touched (SPEC §10.6.4 holds for it).
  - It is plain `.js`, because the Electron desktop sidecar runs it under Node, not Bun.
  - Its imports are only `node:` built-ins: no `@opencode-ai/plugin` runtime import, no `node_modules`, no Bun `$`.
- **Exactly one export**: the default object. OpenCode loads every export as a plugin ("Plugin export is not a function"), so helpers and constants stay unexported.
- **Never** subdirectories or helper files in `.opencode/plugins/`. V2 loads immediate subdirectories as plugin packages.
- **Sentinel.** Line 1 is `// ` + the reconciled `renderer.SENTINEL` (L7). The `.opencode/plugins` entry in `_output_directories` therefore makes the inherited first-line scan clean up a stale shim. The duplicate `_default_cleanup` in opencode_adapter.py:106-131 should be deleted in favor of the ABC's (base.py:74-100); it is byte-identical.
- **Rendering.** The shim is rendered from a packaged static template, `src/coding_agent_playbook/templates/hook_shims/opencode-plugin.js`. A single placeholder, `/*@@REG@@*/`, is replaced (via `str.replace`) by `json.dumps(reg, sort_keys=True, separators=(",", ":"))`.
  - **Not Jinja**: JS braces would fight it, and L7 limits Jinja to bodies.
  - The launcher (§C.2.7) uses the same mechanism from `templates/hook_shims/claude-launch.sh`.
  - `templates/hook_shims/` is engine wiring outside the bundled content, so `FileSystemArtifactSource` never walks it.
- **SPEC amendments.** §2.2 (the "No OpenCode plugins" non-goal), §10.6.2 and §10.6.4 change from "users author plugins" to "the adapter owns exactly `plugins/playbook-hooks.js`; every other file in `.opencode/plugin(s)/` is user-owned". Q8 in §19 is resolved. The catalog's control-plane-guard path `.opencode/plugin/playbook-*` is corrected to `.opencode/plugins/playbook-hooks.js`.

#### §C.3.2 Shim skeleton (rendered; `REG` shown for a typical default pack)

```js
// AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync'
// OpenCode V1 plugin: forwards lifecycle events to playbook-hook (specs/prK-lifecycle-hooks.md §C.3).
// Export ONLY the default object (OpenCode loads every export as a plugin). Import only node: built-ins.
import { spawn } from "node:child_process"
import { readFileSync } from "node:fs"
import { dirname, isAbsolute, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

// Repo root from this file's location: ctx.worktree is "/" outside git (project.ts:217@v1.19.0).
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..")
const REG = {"post_tool_use":{"timeout_ms":12000,"tools":["apply_patch","bash","edit","write"]},"pre_tool_use":{"timeout_ms":32000,"tools":["apply_patch","bash","edit","glob","grep","read","write"]},"session_start":{"timeout_ms":6000},"stop":{"timeout_ms":5000}}
const TOOL = { bash: "Bash", edit: "Edit", write: "Write", read: "Read", glob: "Glob", grep: "Grep",
  webfetch: "WebFetch", websearch: "WebSearch", task: "Agent", todowrite: "TodoWrite",
  question: "AskUserQuestion", skill: "Skill" }           // apply_patch and MCP/plugin tools pass through
const ALIAS = { filePath: "file_path", oldString: "old_string", newString: "new_string",
  replaceAll: "replace_all", patchText: "patch_text", include: "glob" }
const EVENT = { pre_tool_use: "PreToolUse", post_tool_use: "PostToolUse",
  session_start: "SessionStart", stop: "Stop" }
const CAP = 4000          // hard ceiling per injected block; the dispatcher's own caps are lower
const RESP_CAP = 65536    // tool output forwarded to post_tool_use
const deferred = new Map() // callID -> pre_tool_use context, appended to that call's result
const system = new Map()   // sessionID -> session_start context, re-pushed on every model request
const carry = new Map()    // sessionID -> last stop findings, replaced at the next session.idle
const notes = new Map()    // sessionID -> wire `notice` lines, pushed once on the next model request
let warned = false

const wants = (event, tool) => !!REG[event] && (REG[event].tools === "*" || REG[event].tools.includes(tool))

function interpreter() {   // per-worktree pin written by `playbook sync` (§C.2.7)
  let gitdir = join(ROOT, ".git")
  try {
    const m = /^gitdir:\s*(.+?)\s*$/m.exec(readFileSync(gitdir, "utf8"))  // linked worktree
    if (m) gitdir = isAbsolute(m[1]) ? m[1] : resolve(ROOT, m[1])
  } catch { /* .git is a directory (EISDIR) or absent */ }
  try {
    const py = readFileSync(join(gitdir, "playbook-hooks", "interpreter"), "utf8").split(/\r?\n/)[0].trim()
    return isAbsolute(py) ? py : null
  } catch { return null }
}

function inactive(why) {   // fail open; say so once per process
  if (!warned) { warned = true; console.error(`[playbook] lifecycle hooks inactive: ${why}; run 'playbook-hook doctor'`) }
  return { decision: "none", reason: "", context: "", notice: "", failed: why }
}

function parse(code, out) {   // playbook.hook.wire/1 (§D.3.5); exit 10 = decided deny
  if (code !== 0 && code !== 10) return inactive(`dispatcher exited ${code}`)   // a raw 2 is not a deny
  const text = out.trim()
  let j = {}
  if (text) { try { j = JSON.parse(text) } catch { return inactive("dispatcher wrote non-JSON stdout") } }
  const deny = code === 10 || j.decision === "deny"   // ask was already degraded to deny (§D.3.6); "allow" does not exist (L6)
  return {
    decision: deny ? "deny" : "none",
    reason: String(j.reason ?? "").trim() || (deny ? "Blocked by a playbook hook." : ""),
    context: (Array.isArray(j.context) ? j.context.join("\n") : "").slice(0, CAP),
    notice: String(j.notice ?? "").slice(0, CAP),
  }
}

const note = (sid, r) => { if (sid && r.notice) notes.set(sid, [...(notes.get(sid) ?? []), r.notice].slice(-5)) }

function dispatch(event, payload) {
  const py = interpreter()
  if (!py) return Promise.resolve(inactive("no interpreter pin (run 'playbook sync')"))
  return new Promise((done) => {
    let out = "", err = "", settled = false
    const finish = (r) => { if (!settled) { settled = true; clearTimeout(timer); done(r) } }
    const child = spawn(py, ["-I", "-m", "coding_agent_playbook.hook_runtime", "dispatch", event,
      "--harness", "opencode", "--project-dir", ROOT],
      { cwd: ROOT, shell: false, windowsHide: true, stdio: ["pipe", "pipe", "pipe"] })
    const timer = setTimeout(() => { child.kill(); finish(inactive(`${event} exceeded ${REG[event].timeout_ms} ms`)) },
      REG[event].timeout_ms)
    child.stdout.setEncoding("utf8").on("data", (d) => { out += d })
    child.stderr.setEncoding("utf8").on("data", (d) => { err += d })
    child.stdin.on("error", () => {})                   // EPIPE when the dispatcher exits without reading
    child.on("error", (e) => finish(inactive(`spawn failed (${e.code ?? e.message})`)))
    child.on("close", (code) => finish(parse(code, out)))
    child.stdin.end(JSON.stringify(payload))
  })
}

const toolInput = (args) => {      // deep copy: the shim never mutates output.args (L6, no updatedInput)
  const input = JSON.parse(JSON.stringify(args ?? {}))
  for (const [native, alias] of Object.entries(ALIAS)) if (native in input && !(alias in input)) input[alias] = input[native]
  return input
}
const toolPayload = (event, input, args, extra) => ({
  hook_event_name: EVENT[event], session_id: input.sessionID, tool_use_id: input.callID,
  tool_name: TOOL[input.tool] ?? input.tool, tool_input: toolInput(args), cwd: ROOT, ...extra })

async function server() {
  return {
    "tool.execute.before": async (input, output) => {
      if (!wants("pre_tool_use", input.tool)) return
      const r = await dispatch("pre_tool_use", toolPayload("pre_tool_use", input, output.args, {}))
      note(input.sessionID, r)
      if (r.decision === "deny") throw new Error(r.reason)   // becomes the tool's error result; the loop continues
      if (r.context) {
        deferred.set(input.callID, r.context)
        if (deferred.size > 256) deferred.delete(deferred.keys().next().value)  // after() never fires on failure
      }
    },
    "tool.execute.after": async (input, output) => {
      let ctx = deferred.get(input.callID) ?? ""
      deferred.delete(input.callID)
      if (wants("post_tool_use", input.tool) && typeof output.output === "string") {   // MCP results are skipped
        const r = await dispatch("post_tool_use", toolPayload("post_tool_use", input, input.args,
          { tool_response: { output: output.output.slice(0, RESP_CAP), title: output.title ?? "" } }))
        note(input.sessionID, r)
        if (r.context) ctx = ctx ? `${ctx}\n${r.context}` : r.context
      }
      if (ctx && typeof output.output === "string") output.output += `\n\n[playbook] ${ctx}`
    },
    "experimental.chat.system.transform": async (input, output) => {
      const sid = input.sessionID
      if (!sid) return
      if (REG.session_start && !system.has(sid)) {
        const r = await dispatch("session_start", { hook_event_name: "SessionStart", session_id: sid, source: "startup", cwd: ROOT })
        note(sid, r)
        system.set(sid, r.failed
          ? `playbook lifecycle hooks are NOT active this session (${r.failed}); apply the AGENTS.md Guardrails section yourself.`
          : r.context)
      }
      for (const text of [system.get(sid), carry.get(sid), ...(notes.get(sid) ?? [])]) if (text) output.system.push(text)
      notes.delete(sid)
    },
    event: async ({ event }) => {      // fire-and-forget: OpenCode does not await this hook
      if (event.type !== "session.idle" || !REG.stop) return
      const sid = event.properties?.sessionID
      const r = await dispatch("stop", { hook_event_name: "Stop", session_id: sid, stop_hook_active: false, cwd: ROOT })
      note(sid, r)   // the dispatcher returns the combined Stop result on stdout; carry is its only carrier (§C.3.6)
      const text = r.decision === "deny" ? `The previous turn ended with unresolved playbook gate findings:\n${r.reason}` : r.context
      if (text) carry.set(sid, text.slice(0, CAP)); else carry.delete(sid)
    },
  }
}

export default {
  id: "playbook.hooks",
  server,                                     // OpenCode V1 (object default export documented >= 1.18.29; doctor warns below)
  async setup() {                             // OpenCode V2: inert stub so V2 loads without error (QC-1)
    console.error("[playbook] OpenCode V2 detected: lifecycle hooks inactive; AGENTS.md Guardrails are advisory")
  },
}
```

**`REG` construction.** `REG` is produced by `to_opencode_reg(regs) -> dict` *(proposed, `hook_registrations.py`)*:

- One key per canonical event that is reachable on OpenCode (§C.5) and has at least one member declaring `opencode` (`pre_compact` never is, §C.1.2).
- `tools` = the sorted union of the members' tool classes mapped to OpenCode names (§A.2 table). `apply_patch` is included whenever `edit` or `write` is. `"*"` is used when any member matches every tool.
- `timeout_ms` = the §D.4 registration timeout × 1000 (the same formula as Claude, §C.2.1).
- `session_start` is always present when any key is, for the bootstrap and the inactive notice.

**Notices.** Wire `notice` lines (user notes, deferred notes drained by the dispatcher on every OpenCode dispatch, §D.6.4) are queued per session and pushed once into the next model request's system context — the OpenCode equivalent of Claude's `systemMessage`.

**Reload behavior.** A change that alters only `guard_config.json` takes effect on the next dispatch with no restart, because the dispatcher reads it per call (no path or digest is baked into the shim). A change to `REG` alters the shim bytes, and V1 has no plugin hot reload, so sync prints the restart notice (§C.1.5).

#### §C.3.3 Payload translation (OpenCode V1 → Claude-shaped stdin)

This follows the reference design in OpenCode PR #52765 (open and unmerged, written against V2 names), applied to V1's native names. Native argument keys are **kept**, and snake_case aliases are added beside them, so the §D.2.2 normalizer can read either; this alias table is the one §D.2.2 uses (V1 names only — a glob/grep `path` is a search directory and is never aliased to `file_path`). There is no extra shim envelope: the normalizer classifies by `tool_name`, which carries the native name for pass-through tools such as `apply_patch`. Tool hooks carry no cwd (#50133), so `cwd` is always `ROOT`. The dispatcher is invoked with the §D.1 argv `dispatch <event> --harness opencode --project-dir ROOT`, so it never guesses the harness or the root from the payload.

| OpenCode V1 tool | Native args (v1.19.0) | `tool_name` | Aliases added to `tool_input` |
| --- | --- | --- | --- |
| `bash` | `command`, `timeout` (ms), `workdir` | `Bash` | none (`command` is shared; `workdir` is kept for path resolution) |
| `edit` | `filePath`, `oldString`, `newString`, `replaceAll` | `Edit` | `file_path`, `old_string`, `new_string`, `replace_all` |
| `write` | `filePath`, `content` | `Write` | `file_path` |
| `apply_patch` (GPT models, instead of edit/write) | `patchText` | `apply_patch` (passed through unsplit; the §D.2.2 normalizer maps it to the `edit`+`write` classes and parses `*** Add/Update/Delete File:` / `*** Move to:` headers, one parser shared with a future Codex adapter) | `patch_text` |
| `read` | `filePath`, `offset`, `limit` | `Read` | `file_path` |
| `glob` / `grep` | `pattern`, `path` (+ `include`) | `Glob` / `Grep` | `glob` ← `include` |
| `webfetch` / `websearch` | `url`, `format`, `timeout` / query | `WebFetch` / `WebSearch` | none |
| `task` | description, prompt, agent | `Agent` (Claude's current name; PR #52765 uses `Task`, so the normalizer accepts both) | none |
| `todowrite`, `question`, `skill` | — | `TodoWrite`, `AskUserQuestion`, `Skill` | none |
| MCP `<server>_<tool>`, plugin tools, `execute` | — | not forwarded (`wants()` prefilters on REG names); were they forwarded, they would classify `other` | none |

**Event payload fields:**

- `hook_event_name` and `session_id` (`input.sessionID`).
- `tool_use_id` (`input.callID`) on tool events.
- `tool_response: {output, title}` on `post_tool_use` (built-in tools only; the output string is truncated to 64 KiB).
- `source: "startup"` on `session_start`.
- `stop_hook_active: false` on `stop`. Loop protection lives in the coordinator's engine state, not in this flag.

Absent fields, which the dispatcher must tolerate:

- `transcript_path` (OpenCode has none);
- `permission_mode`: treated as `default`, never `plan`, so the plan-mode skip of the Stop gate cannot trigger;
- `last_assistant_message`: `prompt-output-contract-on-stop` is inert on OpenCode (§E.2).

#### §C.3.4 Decision mapping and context limits

| Canonical decision | `pre_tool_use` | `post_tool_use` | `session_start` | `stop` |
| --- | --- | --- | --- | --- |
| `deny` | `throw new Error(reason)`: the model sees it as the tool's error result and the loop continues | n/a (rejected by validate) | n/a | **cannot block** (§C.3.6): the reason is carried into the next turn |
| `ask` | never on the wire: the dispatcher degrades it to deny with the reason prefixed "Needs user approval (OpenCode cannot ask)" (§D.3.6, `ev.harness == opencode` is unattended) | n/a | n/a | n/a |
| `context` | deferred: stashed by `callID` and appended to the **same call's** result in `tool.execute.after`. A denied call carries its context in the reason instead | appended to `output.output` as `\n\n[playbook] …` (built-ins only; MCP `CallToolResult` shapes are left untouched) | pushed into `output.system` on every model request for that session (experimental API) | carried into the next turn's system context |
| `notice` (wire field, any event) | queued, pushed once into the next request's system context | same | same | same |
| `none` / harness-level failure | proceed | proceed | inactive notice in system context | nothing |

`pre_compact` is not registered on OpenCode (§C.1.2).

Context blocks are capped at 4,000 chars in the shim. That is only a ceiling: the dispatcher enforces the pack's tighter caps, such as ≤ 600 chars at session start and ≤ 8 diagnostic lines after an edit.

**Harness-level failures fail open, matching Claude Code semantics.** These are: timeout, spawn error, non-JSON output, an exit code other than 0 or 10, and a missing pin. They are reported with one `console.error` per process and a system-context notice. OpenCode *could* enforce fail-closed here, but parity with Claude, plus not bricking every tool call, wins. Overlay strict mode can flip it (QC-11).

The `tool.execute.before` throw semantics conflict with open issue #52837, which claims throws are swallowed, while v1.19.0 source shows they propagate. An env-gated end-to-end test (`PLAYBOOK_E2E_OPENCODE=1`, `# pragma: no cover`, never in CI, the same discipline as `OpenCodeRunner`) pins the behavior.

#### §C.3.5 Spawn mechanics

- **Asynchronous `spawn`, not `spawnSync`.** `spawnSync` blocks the OpenCode server's event loop for the hook's whole duration, stalling every session and the UI for up to the timeout. The async form still awaits inside the hook, which is what blocking requires, and it lets the shim kill the child on its own deadline. OpenCode enforces **no** hook timeout: `Plugin.trigger` awaits sequentially with no cap, so a hung shim would stall the tool call forever.
- **Arguments.** `shell: false` with an argv array, so paths with spaces need no quoting. The interpreter is the absolute pin, never `python3` / `python` / `node` lookup. `process.execPath` is the opencode binary, not `node`.
- **Environment.**
  - `cwd: ROOT`, derived from `import.meta.url` because `ctx.worktree` is `/` for non-git directories.
  - `windowsHide: true`.
  - `stdin.on("error")` swallows EPIPE when the dispatcher exits without reading.
  - The environment is inherited (§D.7: escape hatches are read only from the hook process environment).
- **Windows.** Shebangs and exec bits are irrelevant because the pinned `python.exe` is spawned directly. `child.kill()` maps to `TerminateProcess` and does not kill grandchildren. The dispatcher bounds its own subprocesses (`proc.py`, §D.1).
- **Runtime support.** Bun implements `node:child_process.spawn` with piped stdio. The Electron sidecar is Node. Both are covered by the `node:`-only rule.

#### §C.3.6 Event reachability and the Stop coordinator on OpenCode

| Canonical event | V1 carrier | Status |
| --- | --- | --- |
| `pre_tool_use` | `tool.execute.before` (runs before OpenCode's own permission prompt) | native: deny, ask→deny, deferred context |
| `post_tool_use` | `tool.execute.after` | native: context |
| `session_start` | `experimental.chat.system.transform`, memoized per `sessionID`. `session.created` is not used: it is fire-and-forget and cannot inject | degraded: context only, experimental API |
| `pre_compact` | not registered: the event's only decision is `none` and OpenCode payloads carry no `transcript_path` to checkpoint | advisory (precompact-checkpoint is Claude-only, §E.5) |
| `stop` | `event` → `session.idle` (bus; **not awaited**; cannot block or re-prompt: #12472 / #16626) | degraded: evidence-only |
| `user_prompt_submit` | not rendered in v1. `chat.message` blocking is undocumented | advisory (QC-2) |
| `post_tool_use_failure` | none: `tool.execute.after` does not fire when a tool throws (#50133) | advisory |
| `subagent_stop` | none: there are no subagent events in the V1 plugin API | advisory (`subagent-stop-verify` is Claude-only, §E.2) |
| `session_end` | none (`session.deleted` is deletion, not end) | advisory |

**The Stop coordinator on OpenCode is evidence-only.** On `session.idle` the shim invokes `dispatch stop --harness opencode` (fire-and-forget, with its own timeout), and the single coordinator (L3) runs its usual stages cheapest-first with tree-fingerprint short-circuiting. Because nothing can keep the loop going:

1. The dispatcher **returns** the combined result on stdout (decision `deny` + reason, or context; §D.5.6) instead of storing a deferred note, and the shim's `carry` map is its single carrier: the findings (≤ 40 lines, per the coordinator's own cap) are pushed into the system context on every request until the next `session.idle` replaces or clears them. `carry` is in-memory, so an OpenCode restart drops it; the decision log keeps the record.
2. The coordinator records the outcome in the decision log, and its `max_blocks` counter is **not** consumed (`can_block=False` only suppresses the block budget). It knows the harness from `--harness opencode` (§D.5.6).
3. The AGENTS.md Guardrails advisory for each Stop-tier hook ("run the gate before claiming done") remains the user-facing instruction.

An automatic SDK re-prompt (`ctx.client.session.prompt`) is **not** used in v1. It would create agent-to-agent loops outside `max_blocks` control (QC-3).

#### §C.3.7 Lifecycle notes

- **Restart.** V1 has no plugin hot reload, so a changed shim needs an OpenCode restart. Sync says so (§C.1.5).
- **Files OpenCode writes itself.** At startup OpenCode writes `.opencode/.gitignore`, `.opencode/package.json`, `package-lock.json` and `node_modules`. None of these is in `written` or the lockfile, so they are invisible to drift. The engine never writes `.opencode/.gitignore`, because OpenCode skips its own when one exists.
- **Plugin load failures are silent.** Load failures inside `applyPlugin` (a bad export, a throw in `server`) are only logged through `Effect.logError`, not surfaced in the UI (verified correction). The golden-file test plus an optional `node --check` syntax test are therefore the guard against a malformed shim.
- **Opting out.** `OPENCODE_DISABLE_PROJECT_CONFIG=1` and `--pure` silently drop project plugins. `doctor` reports both when it sees them in its environment.

### §C.4 Advisory degrade: AGENTS.md, Continue, agent_harness

#### §C.4.1 The `hook_advisory` projection

The renderer gains two formats *(names proposed)*. Both are added to `BUILTIN_FORMATS` (renderer.py:31-40) with dispatch branches before the `NotImplementedError` guard (renderer.py:177-180), so `playbook render <hook-id>` works:

- `hook_advisory`: markdown, shared by all three advisory targets;
- `hook_claude_settings`: the JSON projection of the hook's event registration, debug-only.

`hook_advisory` output:

```markdown
### <hook name>

<rendered advisory body>

*Enforced by lifecycle hooks on: Claude Code, OpenCode. Everywhere else this is guidance: apply it yourself.*
```

The enforcement line is **static**. It is computed from the hook's declared adapter list (§A, L6) intersected with the event reachability in §C.5. It does not depend on which adapters this repo enables, so AGENTS.md bytes do not vary across teammates' `.local.toml` files. Variants:

- Every declared adapter is degraded for the event: "Checked (not blocked) on: OpenCode …".
- Nothing can enforce it: "Not enforced automatically; apply it yourself."

#### §C.4.2 Where the advisory lands

| Adapter | Location | Composition |
| --- | --- | --- |
| `agents_md` | trailing `## Guardrails` section of `AGENTS.md` | `AgentsMdAdapter` gains `_buffered_hooks: list[tuple[str, str]]` (id, rendered block). `finalize` (agents_md_adapter.py:75-94) appends, after the rule sections, `## Guardrails\n\nThese practices are enforced automatically by lifecycle hooks on assistants that support them; on every other assistant, follow them yourself.\n\n` and then the blocks sorted by hook id. The early return at :83-84 becomes `if not (self._buffered_rules or self._buffered_hooks)`, so a hooks-only repo still gets `AGENTS.md` (SPEC §4.3 "always generated") |
| `continue` | `.continue/rules/30-guardrail-<id>.md` | ABC default → `ContinueAdapter.write_rule` (continue_adapter.py:53-68) with `continue_rule` → `alwaysApply: true`, sentinel line 1. SPEC §3's claim that "the Continue CLI supports hooks" is refuted (P5: the loader exists but nothing calls it, and the project is end-of-life), so advisory is the only correct output |
| `claude_code` | `.claude/CLAUDE.md` section, **only** for hooks it cannot enforce, plus one fixed heartbeat line | Advisories are normally empty: natively enforced hooks add nothing to CLAUDE.md; deny reasons and the session-start briefing carry the context, and duplicating 30+ advisories into every Claude session would cost tokens for no enforcement gain. When session-start-playbook-briefing is enabled, `_compose_claude_md` appends exactly one line (owned here, cited by §E.1): `If PLAYBOOK-GUARDS: OK did not appear at session start, tell the user guardrails are not running before risky work.` It is never written to AGENTS.md |
| `opencode` | none (reads `AGENTS.md`) | — |
| `agent_harness` | `rules/30-guardrail-<id>.md`, listed under HARNESS.md "Always consult these" | §C.6 |

**Byte stability.**

- With `[hooks]` off, or no enabled hooks, no Guardrails section is emitted, and `AGENTS.md`, CLAUDE.md and `.continue/` are byte-identical to today.
- Hooks with an empty body (infrastructure such as `guard-decision-log`) produce no advisory block anywhere.
- §E.0.2's master switch is written by `playbook init` and is not flipped by engine upgrades. An engine upgrade therefore only changes these files in repos that opted into hooks, in the same way a new engine rule already does.
- The heartbeat line changes `.claude/CLAUDE.md` bytes once, in repos that enable the briefing; it is fixed text, so it never varies across machines.
- `playbook validate` warns when an advisory body exceeds 600 chars (proposed), to keep AGENTS.md lean.

#### §C.4.3 Claude command frontmatter (for §E.3 `write_scope`)

Read-only prompts render `disallowed-tools: Edit Write NotebookEdit` in `.claude/commands/<slash>.md` (§E.3). `_render_prompt_claude_command` (renderer.py:282-299) emits no frontmatter today; for such prompts it emits a line-1 `---` fence and moves the sentinel to the first body line — the second sentinel position P3's `_sentinel.has_sentinel` accepts, which `ClaudeCodeAdapter._scan_for_stale` (claude_code_adapter.py:191) and the guards adopt. Prompts without `write_scope` render byte-identically to today. (The existing OpenCode command renderer instead writes the sentinel before its `---` fence, renderer.py:336; it is unchanged.)

### §C.5 Harness support matrix and incidental reach

#### §C.5.1 Matrix

D = deny, A = ask, C = context. "Validate" means `playbook validate` rejects that decision for that event on every adapter (L6 "actions an enabled adapter can't express"). The matrix is encoded once as `HOOK_SUPPORT` in `hook_policy.py` (§A.11), and the built-in adapters' `hook_support` ClassVars are taken from it.

| Canonical event | Claude Code (native event: allowed decisions → wire form) | OpenCode V1 | AGENTS.md-only harnesses (Codex, Cursor, Copilot, Gemini, Continue, agent_harness clients) |
| --- | --- | --- | --- |
| `session_start` | `SessionStart`: C → `hookSpecificOutput.additionalContext` | C (system transform, experimental) | advisory |
| `user_prompt_submit` | `UserPromptSubmit`: D → `decision:"block"` + `reason` (shown to the **user**); C → `additionalContext`; A: validate | advisory (QC-2) | advisory |
| `pre_tool_use` | `PreToolUse`: D → `permissionDecision:"deny"` + reason; A → `"ask"` (§D.3.6 degrades to deny when headless); C → `additionalContext` | D (throw); A → D; C deferred into the result | advisory |
| `post_tool_use` | `PostToolUse`: C → `additionalContext`; D, A: validate (the tool already ran) | C (built-in tools) | advisory |
| `post_tool_use_failure` | `PostToolUseFailure`: C | advisory | advisory |
| `stop` | `Stop` (coordinator only, L3): D → `decision:"block"` + reason (continues the agent); C → **`systemMessage`** (Stop `additionalContext` would also force continuation); A: validate | evidence-only: D/C carried into the next turn | advisory |
| `subagent_stop` | `SubagentStop`: D → `decision:"block"`; C → `systemMessage` | advisory | advisory |
| `pre_compact` | `PreCompact`: side effects only. D: validate (blocking a recovery compaction fails the request); no C channel | not registered (`none` only; §C.1.2) | advisory |
| `session_end` | `SessionEnd`: side effects only (output discarded; timeout raises the 1.5 s shared budget) | advisory | advisory |

`playbook validate` errors when a hook declares an adapter for which its event is **unreachable**, for example `subagent_stop` with `opencode`. It does not error for degraded cells. Those appear in `playbook check` as `degraded` per adapter.

Tool-class gaps also produce validate warnings and a `degraded` label in `playbook check`: `mcp` on OpenCode, and `notebook_edit` on OpenCode.

#### §C.5.2 Incidental reach (untested, out of scope for v1 adapters)

Other harnesses read `.claude/settings.json` hooks at runtime, so the managed registrations reach them without an adapter. v1 documents this as **untested reach** and does not design for it (SPEC §2.2: no Cursor/Codex/Gemini adapters).

**Locked v1 behavior.** When the dispatcher is invoked with `--harness claude_code` and the stdin payload is not Claude-shaped, it exits 0 with no output and records `foreign_payload` once per session in the decision log (§D.6.2). "Not Claude-shaped" is a **heuristic**: `hook_event_name` does not match the registered event; `session_id` is missing; a foreign marker is present (`cursor_version`, `conversation_id`); a top-level `timestamp` key is present (VS Code Local, Copilot CLI PascalCase and Gemini payloads carry one; Claude's documented common fields do not); or `CLAUDE_PROJECT_DIR` is unset in the hook environment (Claude always sets it; Copilot documents none; Cursor and Continue set it as an alias, hence the marker check). Golden payloads per harness pin each branch. Inert beats a mis-normalized guard that false-denies.

| Harness | How it reaches us | Specific risks |
| --- | --- | --- |
| Cursor | imports `.claude/settings.local.json`, `.claude/settings.json` and `~/.claude/settings.json`: IDE on by default (Settings → Third-Party Imports toggle); the CLI (`cursor-agent`) always, with no switch. Cursor 3.24.9 treats a Claude settings file as hooks config only when its entries include a `matcher` key and silently skips the file otherwise (the matcher-less SessionStart/Stop groups affect whether it loads). Imported Stop hooks get `loop_limit: null` (no loop cap) | **Events, tools and outputs are remapped.** `PreToolUse` becomes `preToolUse`; `Bash` becomes `Shell` and `Edit` becomes `Write` (Glob has no equivalent); `permissionDecision` becomes `permission`; a Stop block becomes `followup_message`. The payload carries Cursor-native fields, so the dispatcher goes inert. **Fail-open by default** (no `failClosed`). **Windows**: a confirmed PowerShell bug prepends a UTF-8 BOM to stdin, so the dispatcher must strip a leading `﻿` before parsing. **Double execution**: users who also author `.cursor/hooks.json` |
| GitHub Copilot CLI | reads `.claude/settings*.json` by default, subject to folder trust; in `-p` mode only with `GITHUB_COPILOT_PROMPT_MODE_REPO_HOOKS=true`, an already-trusted folder, or `COPILOT_ALLOW_ALL=true`; no per-repo switch other than all-or-nothing `disableAllHooks` | **`preToolUse` is fail-closed on errors**: any non-zero exit other than a timeout denies **every** tool call. This is why the launcher exits only 0 or 2 and why the registration path is cwd-independent (`${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel …)}`; Copilot documents no project-dir variable). **Windows + Copilot CLI is a deny-all risk**: Copilot's `command` field runs under PowerShell there, where `${…:-…}` is not parameter expansion and `sh` is usually absent → non-zero → every tool call denied. `doctor` warns when `copilot` is on PATH. Exit-2 denies are honoured; `hookSpecificOutput` ask/context are ignored (flat schema). Whether Copilot parses Claude's nested matcher groups is undocumented (a single item error rejects the whole inline hooks field). The cloud agent reads only `.github/hooks/`, so it is not reached |
| VS Code (Local harness) | reads Claude format only with `chat.useClaudeHooks` (default OFF) | drops matchers, so the launcher runs for every event. Its stdin is Claude-shaped (same PascalCase event names, `session_id`, `transcript_path`) plus a top-level `timestamp`, which the foreign check above catches. Tool events would be inert anyway (VS Code-internal tool names); lifecycle events would otherwise run the full dispatcher, including the Stop stages, while VS Code expects Stop `decision`/`reason` inside `hookSpecificOutput` |
| Gemini CLI | does **not** read `.claude/` at runtime. `gemini hooks migrate --from-claude` is a one-shot conversion | migrate copies `timeout` unchanged into a **milliseconds** field (12 s becomes 12 ms, so every hook times out and fails open), and its event and tool vocabularies differ. The README tells users not to migrate playbook-managed entries |
| Codex | does not read `.claude/settings.json`. Its own `.codex/hooks.json` uses `deny_unknown_fields` at top level (only `description` / `hooks`) | not reached. Notes for a future Codex adapter: use `description` as the sentinel; new or changed hooks are skipped **with a startup warning** pointing to `/hooks` until re-trusted; the trust hash covers the normalized event, matcher and single handler (command, normalized timeout, async, statusMessage, additionalContextLimit; commandWindows only on Windows), so reformatting or editing `description` does not re-prompt; linked worktrees read the root checkout's `.codex/` (relevant to `.claude/worktrees/*`); exit 2 needs a non-empty stderr reason to block; an unknown handler `type` drops the whole `hooks.json` |
| Continue `cn` | dormant loader reads `.claude/settings*.json`, but nothing calls it | not reached (dead code) |

### §C.6 import-harness / validate-harness / manifest round trip

The Agent Harness spec defines no hook or lifecycle-event concept. Its only executable unit is an agent-invoked skill script. `agent_harness` is therefore **advisory-only** (`hook_support = {}`). It still has to keep the `playbook/hooks/` → harness → `import-harness` round trip lossless, which is what the sidecar exists for (SPEC §20.10).

**Emit (AgentHarnessAdapter).**

- `write_hook` buffers hooks into `self._hooks`, beside the buffers at agent_harness_adapter.py:75-102.
- `finalize` (agent_harness_adapter.py:106-135) treats any hook as non-empty input at the guard on line 117.
- Per enabled hook, it emits:
  - **Sidecar copy (always):** `.playbook/hooks/<id>/HOOK.md`, with canonical frontmatter, the sentinel as first body line (§10.7.3) and the un-rendered body. Bundled scripts (overlay or repo-local external-command handlers) are byte-copied with `shutil.copy2` to `.playbook/hooks/<id>/scripts/` and recorded as `ScriptEntry(path, executable)` (manifest.py:38-43). `.playbook/` already carries `.harnessleaf` (agent_harness_adapter.py:428-432), so harness clients and `validate-harness` treat all of this as opaque. Hook scripts are never exposed as skill scripts, because event-triggered semantics would be lost.
  - **Client-facing advisory (only when the body is non-empty):** `rules/30-guardrail-<id>.md`, with `description` frontmatter and the `hook_advisory` body. It is emitted through the always-rule writer (`_emit_always_rules`, agent_harness_adapter.py:312-322) with manifest recording suppressed (proposed `record_manifest=False`), so it is listed in `RULES.md` and under HARNESS.md "Always consult these" (agent_harness_adapter.py:400-410). It is **presentation only**, not a manifest entry, so a lossless import never turns it into a spurious `Rule`.
- **Cleanup.** `.playbook/hooks` is added to the scanned directories next to `_TOP_LEVEL_DIRS` (agent_harness_adapter.py:50, 436-437). Ownership is the sentinel for `HOOK.md` and the prior manifest for scripts (`_read_prior_engine_files`, agent_harness_adapter.py:439-454).

**Manifest (harness/manifest.py).**

- `ArtifactKind` (manifest.py:35) gains `"hook"`.
- `ManifestEntry` (manifest.py:46-87) gains `hook_frontmatter: dict[str, Any] = field(default_factory=dict)`.
- `_KIND_FIELDS["hook"] = ("name", "body", "is_templated")` (manifest.py:111-125).
- `_entry_to_table` emits `hook_frontmatter` as an inline table for kind `"hook"`, like `extra_frontmatter` for skills (manifest.py:128-137). `_entry_from_table` reads it back (manifest.py:140-164).
- The entry is keyed by `.playbook/hooks/<id>/HOOK.md`.
- **No schema bump.** Older engines read the table fine (unknown keys are ignored) and warn-and-skip the unknown kind (import_harness.py:261-264). Adding a kind is forward compatible.
- **Constraints.** `_toml.format_scalar` (_toml.py:59-104) has no `None` branch, and no float branch until P6 adds one (P6 lands float and date support for `[metrics]` anyway). Hook frontmatter keeps `timeout: float` and float `handler.config` values; `None` values are dropped by `_without_empty` (types.py:45-47). Test: `tests/harness/test_manifest_roundtrip.py::test_hook_float_timeout_and_config_roundtrip` (a hook with `timeout: 2.5` and a float threshold in `config`).

**Import (commands/import_harness.py).**

- `ImportResult` (import_harness.py:66-78) gains `hooks: list[Hook]`.
- `_import_lossless` gains `elif entry.kind == "hook": result.hooks.append(_hook_from_entry(absolute, entry))`, beside :255-260. `_hook_from_entry` rebuilds the hook from `hook_frontmatter`, `body` and `is_templated` through `Hook.from_dict`. Like `_skill_from_entry`, it never trusts the rendered file, and it restores exec bits with `_restore_exec_bit` (import_harness.py:239-243) for each `ScriptEntry.executable`.
- `_write_result` (import_harness.py:494-502) gains `_write_hook(hook, into)`. It writes `<into>/hooks/<id>/HOOK.md` (or `.md.j2` when `is_templated`), following the §A repo-local layout, plus `scripts/` through `_copy_tree(..., restore_exec=True)` (import_harness.py:472-483).
- The summary at import_harness.py:531-536 counts hooks.
- **Best-effort mode (no sidecar).** A `rules/NN-guardrail-*.md` file is imported as a `Rule`, with a lossiness warning: "looks like a degraded hook advisory; the canonical hook cannot be reconstructed without .playbook/manifest.toml".

**Validate (commands/validate_harness.py).** No change. Guardrail rule files are ordinary content files with a `description`, and `.playbook/` is opaque (`_is_opaque`, validate_harness.py:63-74). A regression test asserts that an emitted tree with hooks validates with zero findings.

### §C.7 Tests for this section

All tests are hermetic and use the CI command (`uv run python -m pytest -q`, no path args). They never call a real `claude` / `opencode`.

| File | Covers |
| --- | --- |
| `tests/unit/test_claude_settings.py` *(NEW)* | the full §C.2.4 decision table; the no-op short circuit leaves bytes identical (4-space, tab, CRLF, BOM, `\u` escapes, user key order); splice edits keep every byte outside the edited spans; duplicate keys / NaN / comments / trailing commas → `SettingsMergeError` with path:line:col and no write; mixed group → error; suspect group → restore + warning; empty `hooks` removed and the file never unlinked; race re-read; the self-check rejects a corrupted splice |
| `tests/unit/test_hook_registrations.py` *(NEW)* | matcher union (exact list vs anchored regex vs `*`); the §D.4 timeout formula and the `registration_timeout_s * 1000 ≥ deadline_ms + 1000` assertion for every event; `HOOK_SUPPORT` drives validate errors and warnings; `to_opencode_reg` determinism |
| `tests/unit/test_lockfile.py` | a schema-1 lockfile loads with `scope=""`; scoped entries round-trip; `_build_lockfile` emits no whole-file entry for a scoped path |
| `tests/adapters/test_claude_code.py` | creates settings.json when absent; hooks-only repo (no rules) still registers; idempotent second sync (no write); disabling the last hook strips the managed groups; `launch.sh` sentinel and stale cleanup; `managed_lock_entries` |
| `tests/adapters/test_claude_launcher.py` *(NEW, POSIX-only)* | runs the rendered launcher with `/bin/sh` against a fake pin and fake dispatcher module: dispatcher 0 → 0; 10 → 2; a raw 2 → 0 + `launcher.log` line; missing pin → exit 0 + SessionStart JSON only on `session_start`; dispatcher exit 1 → exit 0 + log line; `--strict-launch` with a missing pin → exit 1; linked-worktree `.git` file; root derived from `$0`; the rendered registration command with `CLAUDE_PROJECT_DIR` set, unset, and unset with the cwd in a subdirectory |
| `tests/adapters/test_opencode.py` | shim golden file; line-1 sentinel; exactly one `export`; no non-`node:` imports; `REG` bytes deterministic (no `pre_compact` key); stale shim removed; optional `node --check` (skipped when node is absent, without relying on the autouse `shutil.which` stub) |
| `tests/hook_runtime/test_wire_contract.py` *(NEW, cross-section golden)* | §D `render_opencode` output for deny, context and notice → the shim's `parse()` (run under `node` when present, else a line-for-line Python port kept beside the template) → the expected `{decision, reason, context, notice}`; a raw exit 2 is `inactive`, never a deny |
| `tests/adapters/test_agents_md.py`, `test_continue.py` | Guardrails section ordering and the enforcement line; AGENTS.md byte-identical with hooks off; empty-body hooks omitted; Continue `30-guardrail-<id>.md` |
| `tests/adapters/test_agent_harness.py`, `tests/harness/test_manifest_roundtrip.py`, `tests/harness/test_import_roundtrip.py` | kind `"hook"` round trip (frontmatter, body, exec bits); an old-engine read warns and skips; validate-harness is clean; guardrail files are not imported as rules in lossless mode |
| `tests/cli/test_sync.py`, `tests/cli/test_check.py` | every §C.2.6 drift row; the pin is written in write mode only, first-writer-wins, and never in `--check` |

### §C.8 Open questions raised by §C

- **QC-1 — OpenCode V2.** The shim ships an inert `setup()` so that V2 loads it without the "must export … setup" error, and logs that hooks are inactive. Should v1.x instead port the shim? The port would be `ctx.tool.hook("execute.before")`, plus `ctx.permission.hook("evaluate")` for deny-with-message. It has to handle the renames (`bash`→`shell`, `apply_patch`→`patch`, `task`→`subagent`, `filePath`→`path`), and V2's Promise-hook throw path, which is undocumented (a defect, not a `Tool.Error`). Recommendation: keep the stub until V2 becomes OpenCode's default installer.
- **QC-2 — OpenCode `user_prompt_submit`.** Whether a throw from `chat.message` blocks a prompt is undocumented. Rendering it (for the overlay `pii-prompt-guard`) needs the env-gated e2e test first.
- **QC-3 — OpenCode Stop re-prompt.** Evidence-only (locked for v1) or an SDK `session.prompt` re-entry bounded by the coordinator's `max_blocks`?
- **QC-4 — Windows without Git Bash.** Claude Code has no per-OS command field. A second `shell: "powershell"` registration would violate L3 and double-run on Git Bash systems. Accept fail-open there (current lock), or ship a PowerShell launcher variant selected at sync time per machine? The latter puts machine-specific bytes into the committed file.
- **QC-5 — `guard_config.json` owner and location.** *Resolved* (§C.0): sync-level writer, `.coding-agent-playbook/hooks/guard_config.json`.
- **QC-6 — Advisory drift on upgrade.** *Resolved*: `[hooks] advisory = false` already exists (§B.1, §A.8).
- **QC-7 — Incidental reach.** Inert (locked) vs best-effort under Copilot CLI, whose PascalCase payloads are Claude-shaped enough that guards could run. If best-effort, Copilot's fail-closed `preToolUse` makes dispatcher robustness a hard requirement. **Release blocker for repos used with Copilot CLI** until verified against a real CLI (env-gated test, never in CI), given the Windows deny-all risk (§C.5.2).
- **QC-8 — `permissions.allow` default.** Opt-in (locked) against the catalog's "always render". `pytest` and `mypy` are excluded by the trust principle. Confirm.
- **QC-9 — Non-git repos.** *Resolved*: hooks are git-only in v1 (§C.2.7 pin table); §D.6.1 has no non-git state root.
- **QC-10 — Advisory degrade vs the codemap's no-op recommendation.** L1 is followed, with explicit enforcement labelling (§C.1.1). Raised for the record.
- **QC-11 — Overlay strict mode (merged with E-Q6 and Q-D2; this is the single entry).** Proposed trigger (§C.2.1): render `"onFailure": "block"` on a registration iff an enabled member on that event has `on_error: deny` (overlay-only), never on `pre_tool_use` unless the overlay opts in explicitly; the registration appends `--strict-launch` so a missing pin or crash exits 1. OpenCode equivalent: fail-closed shim timeouts for those events. Confirm the trigger, and whether an explicit `[hooks] harness_failure = "open" | "closed"` key is still wanted.
- **QC-12 — Snapshot vs hot reload.** *Resolved*: no snapshot; §E.1 and §D.8.1 use the hot-reload rationale.
- **QC-13 — Async audit registration (amends L3; replaces E-Q1).** Sign off the single optional async, non-deciding, output-free `PostToolUse` registration of §C.2.1, or keep local-audit-log on the synchronous registration without `Read`/`Grep`/`Glob` coverage.
- **QC-14 — OpenCode version floor.** The `{id, server}` default-object export is documented from 1.18.29; on an older V1 the load fails silently (`Effect.logError` only). State "OpenCode ≥ 1.18.29" in SPEC §10.6 and the README; `doctor` runs `opencode --version` when present and warns below the floor.

### §C.9 SPEC sections amended by this section

- §2.2 / §2.3: OpenCode plugin generation moves from v2 aspiration to v1 (one generated shim).
- §3: the Continue claim is corrected (L7); the Plugin (OpenCode) glossary entry states the one generated shim under `.opencode/plugins/` (§C.3.1).
- §10.1: the four ABC additions. Also fixes the stale sentence "only ClaudeCodeAdapter overrides `finalize()`"; `agents_md` and `agent_harness` already override it.
- New §10.3.2: settings.json managed merge, launcher, pin.
- §10.4: Guardrails section.
- §10.6.2 / §10.6.4: the shim exception.
- §10.7.2 / §10.7.3: hooks advisory plus the `.playbook/hooks/` sidecar.
- §12.2 / §12.3 / §12.4: summary lines and scoped drift.
- §14.4: `LockEntry.scope` and scoped entries. Also corrects the example, which still shows a `[file_hashes]` table while lockfile.py writes `[[entries]]`.
- §19: Q8 resolved.
- §20.10: kind `"hook"`; the new `lint_codes` / `write_scope` / `output_contract` sidecar fields (§A.7).
- §10.6: the OpenCode ≥ 1.18.29 floor (QC-14).
- §10.3: the Claude command frontmatter for `write_scope` (§C.4.3) and the CLAUDE.md heartbeat line (§C.4.2).

---

## §D — The `playbook-hook` runtime

The runtime is the one process every harness event goes through. It reads the harness payload, normalizes it into a `CanonicalEvent`, fans out in-process to the enabled hooks, combines their results under one decision rule, renders that decision back into the harness's wire format, and records decisions and session state outside the working tree. This section defines that process: packaging, the canonical event, the decision model, the failure policy, the Stop coordinator, state, escape hatches, `guard_config.json`, and testability.

**Out of scope here:**
- What each hook decides. That is §E, the pack, and §F, the new tools.
- How registrations are written into `.claude/settings.json` and the OpenCode plugin. That is §C.
- The `Hook` artifact schema. That is §A.

The runtime consumes the compiled form of all three through `guard_config.json` (§D.8).

### §D.0 Contract with §C (launcher, pin, shim)

§C owns the launcher, the interpreter pin and the OpenCode shim (L4, L5); this section references them and does not redefine them.

| # | Contract (defined in §C, consumed here) |
| --- | --- |
| A-C1 | **Claude command** (§C.2.1, §C.2.7): the committed launcher reads the per-worktree pin `<git_dir>/playbook-hooks/interpreter` and runs `"<pin>" -I -m coding_agent_playbook.hook_runtime dispatch <event> --harness claude_code`. Never bare `python3`, never the console-script wrapper. No config path or digest travels in argv. |
| A-C2 | **Launcher exit codes** (§C.2.7): the launcher exits only 0 or 2 — 2 only when the dispatcher exits `DENY_EXIT = 10`; a missing pin, a crash or any other dispatcher code (a raw 2 included) → exit 0 + a `launcher.log` line, with the INACTIVE `systemMessage`/`additionalContext` only on `session_start`. The sole exception is the overlay strict mode's `--strict-launch` (exit 1, for `onFailure: "block"`). Exit 1 by default would deny every tool call under Copilot CLI, whose `preToolUse` is fail-closed on any non-timeout error. |
| A-C3 | **OpenCode spawn** (§C.3.2): the shim spawns the pin directly with `dispatch <event> --harness opencode --project-dir <ROOT>`, writes the Claude-shaped payload (L5, the §C.3.3 alias table) on stdin, enforces its own timeout, attaches `stdin.on('error')`, maps exit 10 to a throw, and treats a spawn failure, timeout or any other code as **fail-open**. It parses `playbook.hook.wire/1` (§D.3.5). |
| A-C4 | **Config path** (§C.0): `guard_config.json` is a sync-level output at the fixed repo-relative path `.coding-agent-playbook/hooks/guard_config.json`; the runtime resolves it from the repo root it discovers (§D.2.4). |
| A-C5 | **Timeouts**: one formula, owned by §D.4 — `deadline_ms[event]` is rendered into `guard_config.json`, and every registration timeout is `ceil(deadline_ms / 1000) + 2` seconds (§C.2.1 asserts it at sync). |

### §D.1 Packaging and launch

**Entry points.** There are two entry points to one `main(argv) -> int`:
- **For harnesses:** `python -I -m coding_agent_playbook.hook_runtime` (A-C1), through `hook_runtime/__main__.py`.
- **For humans** (`simulate`, `doctor`, ad-hoc `dispatch`): a new console script in `[project.scripts]` (pyproject.toml:44–46 today holds `playbook` and `coding-agent-playbook`):

  ```toml
  playbook-hook = "coding_agent_playbook.hook_runtime.cli:main"   # NEW
  ```

A console-script wrapper puts `.venv/bin` (not the cwd) on `sys.path[0]`, but it still honors `PYTHONPATH`, `PYTHONSTARTUP`, `PYTHONHOME` and user site-packages from the harness environment. `-I` removes all of those, which is why registrations never use the wrapper.

**Subcommands (L3).**

```
playbook-hook dispatch <event> --harness claude_code|opencode [--project-dir DIR]
playbook-hook simulate <event> [--harness H] [--repo DIR] [--config PATH] [--state DIR]
                               [--unattended] [--env NAME=VALUE]... [--format text|json] < payload.json
playbook-hook doctor [--repo DIR] [--since DAYS] [--repin [PYTHON]] [--format text|json]
playbook-hook --version
```

`<event>` is a canonical event name: `session_start`, `user_prompt_submit`, `pre_tool_use`, `post_tool_use`, `post_tool_use_failure`, `stop`, `subagent_stop`, `pre_compact` or `session_end`. This is the **one** `dispatch` argv; §C renders exactly it (golden test: `tests/hook_runtime/test_cli_argv.py` parses the exact §C launcher and shim argv with `hook_runtime.cli`). `--project-dir` defaults to `CLAUDE_PROJECT_DIR`, else the cwd. The config is found at `<worktree_root>/.coding-agent-playbook/hooks/guard_config.json` (A-C4). `dispatch` hand-parses its fixed argv and does not use `argparse`.

**Exit codes.** `dispatch` exits `0` (proceed; stdout may carry JSON) or `DENY_EXIT = 10` (a rendered deny whose harness exit code is 2; the launcher and the shim map it). It **never** exits 2 itself: an unknown flag, a missing argument or an argv/payload mismatch is a `ContractFault` handled by the failure policy (§D.4), so a usage error or a version-skewed engine can never masquerade as a deny. `simulate` and `doctor` are cold paths, use `argparse`, and may exit 2 on usage errors.

**Modules.** All are NEW and live under `src/coding_agent_playbook/hook_runtime/` unless another path is given. Each module has one responsibility and stays under 300 lines.

| Module | Responsibility | Hot path? |
| --- | --- | --- |
| `__init__.py` | Docstring only, no imports | yes |
| `__main__.py` | `raise SystemExit(cli.main(sys.argv[1:]))` | yes |
| `cli.py` | argv → subcommand; fixed-argv fast parse for `dispatch` | yes |
| `dispatch.py` | `run_event(event_name, harness, stdin_bytes, deps) -> WireOutput`: the 9-step pipeline below | yes |
| `deps.py` | `RuntimeDeps` (DI): `env`, `clock`, `proc`, `git`, `state`, `trust`, `out`/`err` streams, `exit: Callable[[int], NoReturn]` (default `os._exit`), `timer_factory` (default `threading.Timer`) | yes |
| `event.py` | `CanonicalEvent`, `ToolCall`, `ToolClass`, `EventName`, `Harness`, `RepoInfo`, `StopInfo` | yes |
| `harness/claude.py` | `parse_claude(payload, env) -> CanonicalEvent`; `render_claude(ev, combined) -> WireOutput` | yes |
| `harness/opencode.py` | `parse_opencode(...)`, `render_opencode(...)` | yes |
| `paths.py` | `find_repo(start) -> RepoInfo \| None` (stdlib `.git` walk); `normalize_path(...) -> NormalizedPath`; glob compile/match | yes |
| `shell.py` | `parse_shell(text, kind, cwd, cfg) -> ShellCommand`; `write_targets(segment)` | yes |
| `gitargv.py` | `parse_git(segment) -> GitInvocation` (`-C`, `-c k=v`, `GIT_CONFIG_*` env); shared by the §E git guards | on git segments |
| `decision.py` | `Decision`, `HandlerResult`, `CombinedResult`, `combine(...)` | yes |
| `caps.py` | `OutputCaps` constants, `clamp_lines`, `quote_data` | yes |
| `policy.py` | `is_unattended(ev, env, cfg)`, `on_handler_error(...)`, the decision-support matrix | yes |
| `registry.py` | `@register_hook_handler`, the static builtin module map, `resolve_handler(spec)` | yes |
| `config.py` | `load_guard_config(repo, state) -> GuardConfig \| ConfigFault` (JSON only; digest check per §D.8.1) | yes |
| `pin.py` | `ensure_interpreter_pin`, `read_interpreter_pin`, `write_machine_pins`, `read_machine_pins` (§C.2.7, §D.8.3); used by sync, `doctor --repin` and the stage runner | sync / doctor / stop |
| `state.py` | `StateStore`: root resolution, 0700, locks, atomic JSON read-modify-write, TTL sweep | yes |
| `session.py` | `SessionState`: `once`, flags, the asked-ids set, deferred notes | yes |
| `ledger.py` | session ledger append/read | post/stop |
| `escape.py` | kill switches; `pragma_at_head(...)` | yes |
| `proc.py` | **the only** `subprocess`/`shutil.which` seam; lazy `import subprocess`; mandatory `timeout=` | when used |
| `git.py` | `GitPort` Protocol + `SafeGit` (§D.5.3): `head_tree`, `fingerprint`, `diff_added`, `cat_head`, `ls_untracked`; `_git_memo.MemoGit`, the dispatch's per-snapshot memo | when used |
| `security/trust.py` (§B.4; not a `hook_runtime` module) | the one `TrustStore` (reader and writer, user-local, outside the repo) | stop / external |
| `watchdog.py` | event deadline timer that emits the failure-policy result and calls `os._exit` | yes |
| `stop/coordinator.py` | `StopCoordinator.run(ev, deps) -> CombinedResult` | stop |
| `stop/stages.py` | `Stage` Protocol, `StageResult`, ordering/planning from `stop_gate.stages` | stop |
| `stop/output.py` | the ≤40-line combined reason composer | stop |
| `canary.py` | in-process canaries shared by the session-start heartbeat (§E) and `doctor` | session_start / doctor |
| `simulate.py`, `doctor.py` | the human subcommands | no |
| `handlers/*.py` | builtin handlers; a module may hold several related handlers (e.g. `ruff_feedback.py`), and `registry._BUILTIN_HANDLER_MODULES` maps each registry name (snake_case, `<name>:<role>` for companions, §A.2) to its module | per hook |
| `protected.py` | `protected_paths(cfg) -> ProtectedSet` (§E.1) | yes |
| `src/coding_agent_playbook/security/{patterns,paths,secrets,audit,trust}.py` | the single sources for `SECRET_PATH_GLOBS` (created by P7) and the secret rules, `PathPolicy`/`is_secret_path`, `scan_text`, the JSONL audit writers, and the trust store; shared with sync, the detector and CLI tools (§D.8) | yes, stdlib only |

**Import-light contract** (enforced by test, §D.9):
- **Allowed on the dispatch path.** Stdlib only: `sys`, `os`, `json`, `re`, `fnmatch`, `shlex`, `hashlib`, `dataclasses`, `enum`, `time`, `stat`, `errno`, `threading`, `unicodedata` (darwin), and `fcntl`/`msvcrt`. Engine modules only from `coding_agent_playbook.hook_runtime.*` and `coding_agent_playbook.security.*`. The runtime never imports `_sentinel`, `hook_policy` or `types`: everything it needs from them (the sentinel string, the compiled hook records) is rendered into `guard_config.json` at sync.
- **Forbidden on the hot path** (`pre_tool_use`, and the python-edit branch of `post_tool_use`). `jinja2`, `yaml`, `importlib.metadata`, `tomllib`, `packaging`, `argparse`, and every other `coding_agent_playbook.*` package: `cli`, `renderer`, `orchestrator`, `adapters`, `sources`, `commands`, `evaluators`, `evals`, `detector`.
- **Branch-local lazy imports (the complete allow-list; cold branches only).** Each row is imported inside the handler, only when its trigger holds; `test_import_budget.py` asserts per branch:

  | Module | Event / branch | Trigger | Measured cost |
  | --- | --- | --- | --- |
  | `tomllib` | `session_start` | lockfile read (briefing; §D.8.1 digest cache refresh) | ~19 ms |
  | `tomllib` | `pre_tool_use`, TOML-edit branch of control-plane-guard and dependency-allowlist-guard | the edited path is a `.toml` policy/manifest file | ~19 ms |
  | `tomllib` | any event | the lockfile's stat changed since the cached digest (§D.8.1) | ~19 ms, once per change |
  | `detector` (pulls `packaging`, `detector.py:14-15`) | `post_tool_use`, source-changed branch (resync-on-detector-input-change) | a detector-relevant dependency set changed | measured by §E.1's test |
  | `evals.loader`, `evals.validator`, `evals.task`, `sources.filesystem` (yaml) | `post_tool_use`, source-changed branch (eval-task-authoring-lint) | an `eval_tasks/*/task.toml` edit | 0.5–1 s (rare) |
  | `evaluators.metrics_gate` (§F.0.3; jinja2-free, verified as `commands.metrics` is today: 0.12 s, no `jinja2`/`cli`/`yaml`) | `stop`, the `quality-metrics` / `docstrings` / `coverage` stages | the stage runs | 0.1–0.2 s |

  Anything that pulls jinja2 runs as a child process (§E.0.1).
- **Prerequisite P-D1.** `coding_agent_playbook/__init__.py` imports `importlib.metadata` at module load to set `__version__`. Measured on the worktree venv (CPython 3.13.9, `-X importtime`), `import coding_agent_playbook` cost 106–249 ms, of which `importlib.metadata` was 69–190 ms cumulative. Every `hook_runtime` import pays that cost, so the 100 ms hot-path budget is unreachable until `__version__` is computed lazily. The exact shape (verified clean under the repo's ruff select set; a bare module `__getattr__` with `__all__ = ["__version__"]` raises ruff F822): `if TYPE_CHECKING: __version__: str` plus `def __getattr__(name: str) -> str` that, for `"__version__"`, computes `importlib.metadata.version("coding-agent-playbook")` (falling back to `"0.0.0+local"`), caches it in `globals()`, and raises `AttributeError` otherwise. The consumers `cli.py:19`, `commands/check.py:12`, `commands/init.py:10` and `commands/sync.py:16` keep working unchanged. Test: `tests/unit/test_package_init.py::test_import_does_not_load_importlib_metadata` (fresh interpreter; `importlib.metadata` absent from `sys.modules` after `import coding_agent_playbook`).

**Interpreter.**
- **Engine ≥3.12 interpreter only** (`requires-python = ">=3.12"`), at the pinned absolute path (A-C1). Never bare `python3`:
  - On this machine it is Anaconda 3.8.8 with no `tomllib`.
  - On Windows it can be the Store stub.

  Both fail open with a non-blocking "hook error" notice, because a non-0/2 exit is a non-blocking error.
- **Always `-I`.** It implies `-E` (ignore `PYTHON*`), `-s` (no user site-packages) and `-P` (no cwd/script dir on `sys.path`). Editable installs still resolve, because `.pth` files in the venv's site-packages are processed; this was verified with `-I -c 'import coding_agent_playbook'` on the worktree venv.
- **Verified shadowing hazard.** I ran this from a scratch dir containing an agent-style `fnmatch.py` that raises on import:
  - `python -m json.tool` raised the shadow module.
  - `python -I -m json.tool` did not.

  The hook cwd follows the agent's `cd` (research), so `-I` is mandatory.

**Measured budgets.** The catalog figures, re-measured where marked.

| Path | Cost |
| --- | --- |
| `import coding_agent_playbook.cli` | 0.37–0.76 s (catalog); 0.50–0.81 s warm, 6.2 s cold (re-measured on this machine) |
| Import-light dispatcher (stdlib + guards) | 0.07–0.09 s (catalog), **after P-D1** |
| `python -I -c pass` | 0.04–0.11 s (re-measured under load); the floor all budgets sit on |
| `tomllib` import | about 19 ms cumulative (`-X importtime`). This is why the hot path reads `guard_config.json`, not TOML |
| Hot path (`pre_tool_use`/`post_tool_use`, all guards) | **p95 ≤ 100 ms** per event |
| `session_start` | **≤ 300 ms** |
| Stop, default stages | **≤ 3 s** (ruff 0.03–0.04 s; metrics about 2.4 s per file, catalog) |
| Execution stages (opt-in + trust) | tens of seconds |

**One process per event invocation.** There is one registration per harness event (L3). The dispatcher fans out to every bound hook in-process, so there are never N cold starts per tool call. The dispatch pipeline:

```
stdin ─▶ 1 env gate (PLAYBOOK_HOOKS)      ─▶ 2 read stdin (cap) + harness parse → CanonicalEvent
      ─▶ 3 load guard_config (+ digest)   ─▶ 4 select hooks: event ∧ adapter ∧ enabled ∧ match
      ─▶ 5 run handlers (ordered; first guard deny short-circuits; per-handler failure policy; watchdog)
      ─▶ 6 combine + caps + ask degradation ─▶ 7 render → stdout JSON + exit code (one write)
      ─▶ 8 decision log + ledger + session state (after the write)  ─▶ 9 exit
```

**I/O discipline.**
- **stdout.** At start the dispatcher saves `real_out = os.dup(1)` and redirects fd 1 to fd 2 (`os.dup2(2, 1)`). Stray prints from handlers, overlay code or child processes therefore can never corrupt the one JSON object Claude parses: Claude parses stdout as JSON only when the entire stdout is one JSON object (whitespace allowed); anything else is plain text (a debug-log entry on most events). The response is written once to `real_out` under a lock that the watchdog shares.
- **stdin.** Read fully, capped at 16 MiB. Beyond the cap the rest is drained without storing it (avoiding EPIPE in the OpenCode shim) and `CanonicalEvent.truncated = True`.
- **stderr.** Non-empty only on `pre_tool_use` deny (the reason, see §D.3.5) and on one-per-session internal notes. Claude never shows exit-0 stderr to the model (research).

### §D.2 Payload normalization

#### §D.2.1 The canonical event

```python
# hook_runtime/event.py (NEW) — frozen, slotted; handlers never mutate
class EventName(StrEnum):  # values == the shared snake_case names
    SESSION_START = "session_start"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    POST_TOOL_USE_FAILURE = "post_tool_use_failure"
    STOP = "stop"
    SUBAGENT_STOP = "subagent_stop"
    PRE_COMPACT = "pre_compact"
    SESSION_END = "session_end"


class Harness(StrEnum):  # == adapter entry-point names (pyproject.toml:52-56)
    CLAUDE_CODE = "claude_code"
    OPENCODE = "opencode"


class ToolClass(StrEnum):  # exactly the §A.2 vocabulary + the runtime-only OTHER
    SHELL = "shell"
    EDIT = "edit"
    WRITE = "write"
    NOTEBOOK_EDIT = "notebook_edit"
    READ = "read"
    SEARCH = "search"
    WEB = "web"
    SUBAGENT = "subagent"
    MCP = "mcp"
    OTHER = "other"  # unmapped tools; matched only by a member that matches every tool


@dataclass(frozen=True, slots=True)
class RepoInfo:
    worktree_root: str  # realpath of the worktree top level
    git_dir: str  # per-worktree git dir (.git, or .git/worktrees/<name>)
    common_dir: str  # shared git dir (git_dir/commondir, else git_dir)
    is_linked_worktree: bool


@dataclass(frozen=True, slots=True)
class StopInfo:
    stop_hook_active: bool
    last_assistant_message: str  # capped to the last 8,000 chars
    agent_transcript_path: str | None  # subagent_stop only


@dataclass(frozen=True, slots=True)
class CanonicalEvent:
    name: EventName
    harness: Harness
    session_id: str  # sanitized [A-Za-z0-9._-]{1,128}; "" if absent
    turn_id: str | None  # Claude prompt_id (absent before first input)
    cwd: str  # event cwd, realpath (follows the agent's cd)
    project_dir: str  # --project-dir / CLAUDE_PROJECT_DIR, realpath
    repo: RepoInfo | None  # None outside git (hooks are then inert, §C.2.7)
    permission_mode: str | None  # default|plan|acceptEdits|auto|dontAsk|bypassPermissions
    agent_id: str | None
    agent_type: str | None
    tool: ToolCall | None  # pre/post tool events only
    prompt: str | None  # user_prompt_submit only; never logged, never persisted
    source: str | None  # session_start: startup|resume|clear|compact|fork; pre_compact: manual|auto
    stop: StopInfo | None  # stop / subagent_stop only
    transcript_path: str | None
    unattended: bool  # policy.is_unattended(), computed once at parse time
    truncated: bool  # stdin exceeded the cap
    raw_event_name: str  # harness-native name, for diagnostics only
```

`ToolCall` carries everything a handler may inspect. It is parsed once per event, and the shell parse is memoized on first access.

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | `str` | Claude-shaped tool name (OpenCode names mapped by the shim, L5) |
| `native_name` | `str` | the harness's own name (`bash`, `apply_patch`, …); equals `name` on Claude |
| `tool_class` | `ToolClass` | from the table in §D.2.3 |
| `use_id` | `str \| None` | `tool_use_id` / OpenCode `callID` |
| `paths` | `tuple[NormalizedPath, ...]` | every path-bearing argument, normalized |
| `write_paths` | `tuple[NormalizedPath, ...]` | paths the call writes (`edit`/`write`/`notebook_edit`, patch targets) |
| `command` | `ShellCommand \| None` | SHELL only; parsed lazily (§D.2.5) |
| `content` | `tuple[ContentFragment, ...]` | text about to be persisted, as `(path, field, text)`: `Write.content`, `Edit.new_string`, `MultiEdit.edits[].new_string`, `NotebookEdit.new_source`, the `+` lines of patch hunks |
| `mcp_server` | `str \| None` | Claude `mcp_server.name` (v2.1.274+), else parsed from `mcp__<server>__<tool>` |
| `response` | `ToolResponse \| None` | post events: `ok`, `exit_code` (parsed from the `Exit code N` prefix on failure), `error` (capped 2,000 chars), `is_interrupt` |
| `raw_input` | `Mapping[str, object]` | read-only view; never logged |

#### §D.2.2 Per-harness parsers

**Claude Code** (`harness/claude.py`). Input is one JSON object on stdin.
- **Common fields:** `session_id`, `prompt_id`, `transcript_path`, `cwd`, `permission_mode` (not on every event), `hook_event_name`, `agent_id`, `agent_type`.
- **Per event:**
  - `tool_name`, `tool_input`, `tool_use_id`, `mcp_server` (PreToolUse/PostToolUse/PostToolUseFailure);
  - `tool_response`, `duration_ms` (PostToolUse);
  - `error`, `is_interrupt` (PostToolUseFailure);
  - `prompt` (UserPromptSubmit);
  - `source` (SessionStart);
  - `stop_hook_active`, `last_assistant_message` (Stop/SubagentStop);
  - `agent_transcript_path` (SubagentStop);
  - `trigger` (PreCompact);
  - `reason` (SessionEnd).
- **`project_dir`** = env `CLAUDE_PROJECT_DIR`, which stays at the session root in worktrees, while `cwd` follows the agent.
- **Unknown keys are ignored** (forward compatible).
- **Foreign-payload check first.** The §C.5.2 heuristic runs before anything else: a payload whose `hook_event_name` does not map to the argv event, that lacks `session_id`, carries a foreign marker or a top-level `timestamp`, or arrives with `CLAUDE_PROJECT_DIR` unset is **foreign** → exit 0, no output, `foreign_payload` logged once per session. A payload that passes it but is otherwise malformed (unparseable JSON, a missing required field) is a `ContractFault` (§D.4).
- **Windows paths** arrive with backslashes (verified docs) and are normalized in §D.2.4.

**OpenCode** (`harness/opencode.py`). Input is the shim's Claude-shaped payload (L5, PR #52765):
- **Fields:** `{hook_event_name, session_id (sessionID), tool_use_id (callID), tool_name (mapped, or the native name for pass-through tools), tool_input (native args + the §C.3.3 V1 aliases filePath→file_path, oldString→old_string, newString→new_string, replaceAll→replace_all, patchText→patch_text, include→glob), cwd, tool_response?}`. A glob/grep `path` is a search directory and is **never** aliased to `file_path` (on V1 `path` is not a file argument; a V2 port would alias `path→file_path` for read/edit/write only).
- **No shim envelope.** Classification is by `tool_name`; there is no `playbook_shim` key.
- **Directory.** `project_dir` comes from `--project-dir` (the shim passes its `ROOT`, derived from `import.meta.url`), never from `ctx.worktree`, which is `/` for a non-git directory.
- **Pass-through tools:**
  - `apply_patch` (V1): paths parsed from the envelope lines `*** Add File: `, `*** Update File: `, `*** Delete File: `, `*** Move to: `; `content` = `+` lines per file; classes `edit` + `write`.
- **Arguments.** The V1 `bash` args are only `command`, `timeout`, `workdir` (verification: no `description`). `workdir` becomes the segment cwd.

#### §D.2.3 Tool-class classification

The classes and names are §A.2's single table; this adds the path fields the normalizer reads.

| `ToolClass` | Claude Code | OpenCode V1 (native) | Path fields |
| --- | --- | --- | --- |
| `shell` | `Bash`, `PowerShell` (Windows; `kind="powershell"`) | `bash` | `command` (+ `workdir`) |
| `edit` | `Edit`, `MultiEdit` (legacy) | `edit`, `apply_patch` | `file_path` (alias of `filePath`); patch envelope |
| `write` | `Write` | `write`, `apply_patch` | `file_path`; patch envelope |
| `notebook_edit` | `NotebookEdit` | — | `notebook_path` |
| `read` | `Read` | `read` | `file_path` |
| `search` | `Glob`, `Grep` (absent by default on macOS/Linux/WSL, where searches arrive as Bash) | `glob`, `grep` | `path` (the `pattern`/`glob`/`include` are patterns, not paths) |
| `web` | `WebFetch`, `WebSearch` | `webfetch`, `websearch` | none (`url` kept in `raw_input`) |
| `subagent` | `Agent`, `Task` | `task` | none |
| `mcp` | `mcp__<server>__<tool>` | not distinguishable (`<server>_<tool>`) and not forwarded by the shim → documented gap | none parsed |
| `other` | everything else (`Skill`, `ExitPlanMode`, `TodoWrite`, …) | everything else | none |

#### §D.2.4 Path normalization

`normalize_path(raw, *, base, repo, platform=sys.platform) -> NormalizedPath`. The steps:
1. **Separators.** If the payload is from win32, or `raw` matches `^[A-Za-z]:\\`, replace `\` with `/`.
2. **Home.** Expand `~` (Claude already expands `~` and relative paths for file tools; OpenCode and Bash targets may not).
3. **Relative paths.** Join to `base`: the segment cwd for Bash targets, otherwise the event `cwd`.
4. **Symlinks.** `os.path.realpath(p, strict=False)` resolves symlinks and `..`. `is_symlink = realpath != normpath(joined)`.
5. **Repo-relative path.** If the realpath lies under `repo.worktree_root`, `repo_rel` is the POSIX path relative to it. If it lies under another worktree sharing `repo.common_dir` (a sibling linked worktree), `repo_rel` is relative to **that** worktree root and `same_repo=True`. Otherwise `outside_repo=True` and `repo_rel=None`.
6. **Match key.** `key = repo_rel or realpath`. On `darwin` and `win32`, apply `unicodedata.normalize("NFC", key).casefold()`. Pattern keys are folded the same way when the config loads. This step is needed for two verified reasons:
   - `fnmatch.fnmatch('.ENV', '.env*')` is `False` on darwin;
   - `realpath` does not fold case (`/tmp/../TMP` → `/private/TMP`).

   Over-matching on a case-sensitive APFS volume is the safe direction for guards.
7. **Stat facts.** One `os.lstat` gives `exists` and `nlink`, the hard-link signal. `realpath` cannot see through hard links, so secret-path guards treat `nlink > 1` on a non-matching file as unknown (§E).

**Glob semantics** (compiled once per process into regexes):
- `**` matches across `/`; `*` and `?` do not cross `/`; `[...]` classes are supported.
- A pattern with no `/` matches the basename at any depth (gitignore-like).
- Matching is `re.fullmatch` on `key`.

**Repo discovery** (`find_repo`) uses no subprocess:
1. Walk up from `project_dir` to the first ancestor containing `.git`.
2. If `.git` is a directory, it is the `git_dir`. If it is a file, `git_dir` is its parsed `gitdir: <path>`.
3. `common_dir` is the content of `<git_dir>/commondir`, resolved against `git_dir`, if that file exists; otherwise `git_dir`.

An integration test asserts equality with `git rev-parse --git-dir --git-common-dir --show-toplevel` on a real tmp repo with a linked worktree.

#### §D.2.5 Shell parsing (`shell.py`)

```python
@dataclass(frozen=True, slots=True)
class Redirect:
    op: str  # '>', '>>', '>|', '<', '&>', '2>', '<<', '<<-', '<<<', …
    target: str | None  # None for heredocs
    fd: int | None


@dataclass(frozen=True, slots=True)
class Segment:
    argv: tuple[str, ...]  # effective argv after env-prefix strip + wrapper unwrap
    raw_argv: tuple[str, ...]  # as written (post-shlex)
    env: tuple[tuple[str, str], ...]  # NAME=value prefixes, incl. those consumed by `env`
    wrappers: tuple[str, ...]  # unwrapped chain, e.g. ("proxy", "timeout")
    redirects: tuple[Redirect, ...]
    heredoc_bodies: tuple[str, ...]  # data only, never parsed as commands
    cwd: str | None  # resolved cwd (after `cd X &&`, git -C, workdir); None = unknown
    dynamic: frozenset[int]  # argv indexes containing $VAR / ${…} / $(…) / backticks
    origin: str  # top | subst | bash_c | eval | xargs | find_exec
    depth: int
    pipes_to_next: bool  # `a | b` (curl|sh detection)
    background: bool
    args_open: bool  # xargs / find -exec: runtime-appended args


@dataclass(frozen=True, slots=True)
class ShellCommand:
    text: str
    kind: str  # posix | powershell
    segments: tuple[Segment, ...]
    parse_error: str | None  # set ⇒ handlers take their conservative branch
```

**Algorithm.** A stdlib scanner handles quotes, escapes, comments, control operators (`;` `&&` `||` `|` `&` newline), `( … )` and `{ …; }` groups, `$( … )` and backticks (extracted and parsed recursively as `origin="subst"`), process substitution, redirections and heredocs. Heredoc bodies are captured as data, so a commit message that mentions `-n` or `--no-verify` is never flagged (§E block-precommit-bypass). Each segment's words go through `shlex.split(posix=True)`. Leading `NAME=value` tokens go to `env`.

**Unwrapping** is applied repeatedly up to depth 4, matching on the basename of `argv[0]`:

| Wrapper | Consumed before the inner argv |
| --- | --- |
| `env` | `-i`, `-u NAME`, `-0`, `--`, `NAME=V…` (into `env`); `-S STR` → split and reparse |
| `sudo`, `doas` | `-u/-g/-h/-p/-C/-D/-r/-t/-U ARG`; flags `-E -H -n -S -k -b`. `-i`/`-s` with no command → interactive shell (empty argv) |
| `command` | `-p` (`-v`/`-V` is a lookup, not a wrapper) |
| `exec` | `-a NAME`, `-c`, `-l` |
| `nohup`; `time [-p]`; `nice [-n N]`; `ionice [-c C] [-n N]`; `stdbuf -i/-o/-e M` | as listed |
| `timeout` | `-s SIG`, `-k DUR`, `--preserve-status`, `--foreground`, `-v`, then `DURATION` |
| `xargs` | `-I R`, `-L/-n/-P/-s N`, `-d D`, `-E S`, `-a F`; flags `-0 -r -t -p -x`; default inner `echo`; `args_open=True` |
| `bash`/`sh`/`zsh`/`dash`/`ksh` | `-c SCRIPT` (including combined `-lc`, `-ec`, `-xc`, `-euc`) → recursive parse (`origin="bash_c"`). `bash file.sh` is opaque, not unwrapped |
| `eval` | args joined → recursive parse |
| `find … -exec/-execdir/-ok CMD … ;` | CMD extracted as an extra segment (`args_open=True`); `find` itself stays a segment (for `-delete`) |
| `guard_config.shell.wrapper_prefixes` | longest-prefix token strip, e.g. `["proxy run", "proxy"]` for a command-rewriting launcher. A user's own rewriting hook runs in parallel on the *original* input, but agents also type `proxy …` literally (catalog principle 18). A prefix is stripped as bare tokens, so none of its tokens may name a guarded command, launcher, runner or shell (`wrapper_policy.hidden_program`; H21 for `[hooks]`). At run time `PLAYBOOK_HOOK_WRAPPER_PREFIXES` adds a developer's own prefixes (§D.7) |
| `guard_config.shell.runner_wrappers` | default `uv run`, `uvx`, `poetry run`, `pdm run`, `hatch run`, `pipx run`, with their own options skipped. Kept in `wrappers`, so command-convention-guard still sees `uv run mypy` |

**Limits and degradation.**
- Limits: text ≤ 64 KiB, nesting depth ≤ 4, ≤ 256 segments. Exceeding any limit sets `parse_error="limit"`.
- An unbalanced quote, or any other scanner failure, sets `parse_error`. The segments are then a best-effort regex split on `;|&&|\|\||\|`, and every handler treats the command as **unknown**: guards take their conservative branch (for destructive-command-guard, a raw regex then `ask`).
- `kind="powershell"` is never shlex-parsed: `segments=()` and handlers apply their PowerShell regex rows.
- **`write_targets(segment) -> list[str]`** is the shared extractor for §E's file guards. It returns redirect targets (`>`, `>>`, `>|`, `&>`), `tee` operands, `sed -i`/`perl -pi` files, `cp`/`mv`/`install` destinations, and `rm`/`truncate`/`dd of=` operands. Sources are never returned, so `cp AGENTS.md /tmp/x` passes.

### §D.3 Decision model

#### §D.3.1 Handler contract and registry

```python
class Decision(StrEnum):  # precedence: DENY > ASK > CONTEXT > NONE
    DENY = "deny"
    ASK = "ask"
    CONTEXT = "context"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class HandlerResult:
    decision: Decision
    hook_id: str
    rule_id: str = ""  # stable id for the decision log, e.g. "rm_root"
    reason: str = ""  # deny/ask text (≤4 lines after clamp)
    context: tuple[str, ...] = ()  # advisory items for the model (CONTEXT)
    user_note: str = ""  # user-facing (systemMessage / OpenCode notice)
    dedupe_key: str = ""  # SessionState.once() key for context items
    degraded: bool = False  # produced by the failure policy, not the handler


class HandlerFn(
    Protocol
):  # (shared name — proposed; not types.HookHandler, the frontmatter dataclass)
    def __call__(self, ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None: ...
```

- **`HandlerContext`** carries:
  - `hook`: the hook's `guard_config.hooks.<id>` record (the `ResolvedHook.to_json()` schema of §A.7: `handlers.<event>.config`, `on_error.<event>`, `timeout_ms`, `decisions`);
  - `cfg`: the `GuardConfig`;
  - `git`: the `GitPort`;
  - `session`: the `SessionState`;
  - `ledger`;
  - `proc`;
  - `deadline`: monotonic seconds.

  `None` means `NONE`. A handler must not write to stdout, must not mutate `ev`, and must not return any decision outside `Decision`. L6: there is no `allow`, no `updatedInput` and no HTTP.
- **`@register_hook_handler(name)`** registers a builtin under its registry name — snake_case and shareable across hooks, with `"<name>:<role>"` for companions (the §A.2 naming rule). Two choices keep it import-light:
  - **No eager module scan.** `registry._BUILTIN_HANDLER_MODULES: Final[dict[str, str]]` statically maps each handler name to its module. `resolve_handler()` imports only the modules of the hooks bound to the current event, and the decorator fires at that import. A test imports every handler module and asserts that the static map equals the decorator registry.
  - **No `importlib.metadata` at run time.** Out-of-tree handlers from the `coding_agent_playbook.hook_handlers` entry-point group are resolved **at `playbook sync`**, using the same in-tree-wins dedup as `evaluators/checks/registry.py:166` `_load_check_entry_points`. They are written into `guard_config` as `{"kind": "entry_point", "target": "pkg.mod:attr", "dist": "pkg==1.2.0"}`. At run time the runtime imports `pkg.mod` directly. Per §B.4 such a handler runs only when its distribution's top-level package is in `[hooks] allow_code_from` (no TOFU record; §K tracks whether to add one); otherwise it is skipped as `untrusted` with one note per session. The empty group table `[project.entry-points."coding_agent_playbook.hook_handlers"]` is declared in `pyproject.toml` (P-D5).
- **External handlers** (`{"kind": "external", "argv": [...], "sha256": ...}`, overlay or repo-local, L1):
  - They run through `proc.run` with the hook's `timeout_ms`. stdin is the **canonical** event as JSON (`schema: "playbook.hook.event/1"`), not the harness payload.
  - stdout must be one JSON object: `{"decision": "deny|ask|context|none", "reason"?, "context"?: [str], "user_note"?}`. Any other value, extra decision keys (`allow`, `updatedInput`, `permissionDecision`), invalid JSON or a non-zero exit is an internal error (§D.4).
  - Execution needs a §B.4 trust entry matching the launcher name, the copied script's sha256 and the args' sha256 (never the interpreter path, which is per machine); `argv` in `guard_config` is repo-relative and the interpreter is resolved from the pin / `machine.json`.

#### §D.3.2 Selection and ordering

A hook is selected when all of these hold:
- the event is in its `events`;
- its `supports` include the harness;
- it is present in `guard_config.hooks` (sync has already applied the §B.1 on-formula, `applies_if` and the `[hooks]` enable/disable lists; the runtime never evaluates `applies_if`) and not listed in `PLAYBOOK_HOOKS_DISABLE` unless `mandatory` (§D.7);
- its `matcher.<event>` accepts the event (tool class / tool names / path globs / command regexes).

The order is `(class rank, priority, id)` — the same rule as §A.2's `priority`. Guard class comes before quality class (§D.4), so the order is deterministic and never depends on dict order.

The **first guard-class `DENY` short-circuits** the rest of the event's handlers: a deny is final, and skipping the rest saves latency. `ASK` and `CONTEXT` accumulate.

#### §D.3.3 Combination rule

`combine(results, *, ev, cfg) -> CombinedResult`:
1. **Ask degradation**, per result: `effective = DENY if r.decision is ASK and ev.unattended else r.decision`. It is logged as `ask→deny` with the reason prefixed `Needs user confirmation; unattended run, so denied: `.
2. **Final decision** = the maximum `effective` under `DENY > ASK > CONTEXT > NONE`. With no results it is `NONE`.
3. **Reason** (final ∈ {DENY, ASK}): the reasons of the results whose `effective` equals the final, in handler order. Clamped to ≤ 4 lines, ≤ 160 chars per line, ≤ 600 chars. If more than one handler contributed and lines were dropped, the last line is `(+N more playbook findings)`.
4. **Context** (only when final = CONTEXT): the context items of the CONTEXT results, after `SessionState.once(dedupe_key)`, capped per §D.3.4. Context is **dropped** under DENY/ASK, because the tool does not run and the reason is what matters.
5. **User notes**: from every result, NONE included. Deduped, ≤ 6 lines, ≤ 800 chars.
6. **Declared-decision check.** A result whose decision ∉ the hook's declared `decisions` is a `contract_violation`, handled by the failure policy (§D.4) before combination.
7. **Event support check.** If the final decision is not allowed for the event (§D.3.5 matrix), it is mapped down (ASK→DENY, DENY/ASK→CONTEXT, or →NONE as the matrix says) and logged as `contract_violation`. `playbook validate` should already have rejected the hook (L6).

#### §D.3.4 Output caps and sanitization

| Channel | Cap | Enforced in |
| --- | --- | --- |
| deny/ask reason | ≤ 4 lines, ≤ 160 chars/line, ≤ 600 chars; names the safe alternative and never teaches a bypass (§E owns the wording) | `combine` |
| pre/post `context` diagnostics | ≤ 5 items from project config, ≤ 8 total per event; deduped per session by `(path, code, sha1(message)[:8])` | `combine` + `SessionState.once` |
| `session_start` context | the heartbeat line + anomalies, ≤ 600 chars; nothing else when clean | the briefing handler (§E) |
| Stop combined reason | ≤ 40 lines, ≤ 4,000 chars | `stop/output.py` |
| `systemMessage` / OpenCode `notice` | ≤ 6 lines, ≤ 800 chars | `combine` |
| any single output field | ≤ 4,000 chars, well under Claude's 10,000-char overflow-to-file threshold | renderer |

`quote_data(s, limit=200)` is the only way a repo-derived string (path, branch, commit subject, message excerpt) enters model-facing text. It truncates to `limit`, then `json.dumps(..., ensure_ascii=True)`, which escapes control characters and newlines and quotes the result. Guard posture is reported as categories, never as patterns, internal hostnames or identity values (catalog principle 15).

#### §D.3.5 Decision-support matrix and rendering

The renderers (`render_claude`, `render_opencode`) are the only producers of harness output. They emit from a **closed key allowlist**: `hookSpecificOutput.{hookEventName, permissionDecision ∈ {deny, ask}, permissionDecisionReason, additionalContext}`, top-level `decision: "block"`, `reason` and `systemMessage`. A test asserts that `allow`, `defer`, `updatedInput`, `updatedToolOutput`, `continue`, `suppressOriginalPrompt`, `initialUserMessage`, `watchPaths`, `reloadSkills` and `sessionTitle` can never appear.

| Canonical event | Allowed decisions | Claude Code rendering | OpenCode rendering (wire result → shim) |
| --- | --- | --- | --- |
| `pre_tool_use` | deny, ask, context, none | **deny:** stdout `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":R}}`, the same R on stderr, harness **exit 2** (process exit `DENY_EXIT = 10`, mapped by the launcher). **ask:** the same JSON with `"ask"`, exit 0. **context:** `{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":C}}`, exit 0. **none:** no stdout, exit 0 | deny (ask already degraded, §D.3.6) → `{"decision":"deny",…}`, process exit **10** (the shim throws; OpenCode has no ask primitive). context → the shim defers it to `tool.execute.after` (§C.3.4) |
| `post_tool_use` | context, none | `hookSpecificOutput.additionalContext` (`hookEventName:"PostToolUse"`), exit 0 | context → appended to `output.output` |
| `post_tool_use_failure` | context, none | the same with `"PostToolUseFailure"` | V1: no event (`tool.execute.after` does not fire on a throw); V2: `execute.after` with `status: "error"` |
| `user_prompt_submit` | deny, context, none (ask→deny) | deny: `{"decision":"block","reason":R}`, exit 0 (R is shown to the **user**, not Claude). context: `additionalContext` | not rendered in v1 (§C.3.6, QC-2); hooks on this event declare `supports` without `opencode` |
| `session_start` | context, none | `hookSpecificOutput.additionalContext` (`"SessionStart"`), exit 0 | context → `experimental.chat.system.transform` (§C) |
| `stop` / `subagent_stop` | deny, context, none | deny: `{"decision":"block","reason":R}`, **exit 0, never exit 2**. context-only: **`systemMessage` only**, never `hookSpecificOutput.additionalContext`, because on Stop that also continues the conversation (verified docs) and would turn every warning into a forced continuation | `stop` only (no `subagent_stop` on V1). Not blockable (`session.idle` is fire-and-forget): the combined result is **returned** on stdout (decision deny + reason, or context) with process exit 0, and the shim's `carry` injects it on the next turn (§C.3.6) |
| `pre_compact` | none | exit 0; side effects only (precompact-checkpoint) | not registered (§C.1.2) |
| `session_end` | none | exit 0 | unsupported |

Every event also renders the combined user notes as top-level `systemMessage` (Claude) or `notice` (OpenCode). On OpenCode, `notice` also carries the session's deferred notes, drained on every dispatch (§D.6.4).

**OpenCode wire result** *(shared name — proposed: `playbook.hook.wire/1`; the shim's `parse()` reads exactly these fields, §C.3.2, and a cross-section golden test pins both sides, §C.7)*:
- stdout: `{"v":1,"decision":"deny"|"context"|"none","reason":str,"context":[str],"notice":str}`;
- process exit **10 iff `decision == "deny"`** on `pre_tool_use`, else 0. A minimal shim keyed only on the exit code still blocks; a raw 2 is never a deny.

**Why a harness exit 2 on PreToolUse deny.** Exit 2 + stderr is the deny channel: on exit 2 the stderr text is the reason, and any JSON on stdout is still read but cannot override the block. The JSON is therefore redundant there; it is kept because it costs nothing. Exit 2 keeps the deny working when a shell profile echo (Git Bash, or `BASH_ENV` pointing at `~/.bashrc`, in Claude's `sh -c` wrapper) corrupts stdout. `ask` and `context` have no such fallback, so `doctor` runs the exact registered command and checks that stdout is a single JSON object.

**Why exit 0 on Stop.** The verified exit-2 reclassification on Stop/SubagentStop ("No such file or directory" with empty stdout) cannot misfire on a JSON `decision: "block"`. `onFailure` has no effect on Stop either way.

#### §D.3.6 Ask degradation (defined once)

`is_unattended(ev, env, cfg) -> bool` is true when **any** of these hold. Each value is read only from the hook process environment (§D.7).

| Signal | Source |
| --- | --- |
| `PLAYBOOK_HOOK_UNATTENDED=1` *(shared name — proposed)* | set by `ClaudeCodeRunner._invoke_agent` (`evals/claude_code_runner.py:107`) and `OpenCodeRunner._invoke_agent` (`evals/opencode_runner.py:108`) on the child env. **Prerequisite P-D2:** both currently call `subprocess.run` without `env=` |
| `CI` ∈ {`true`, `1`} or `GITHUB_ACTIONS=true` | CI runners |
| `ev.harness == opencode` | OpenCode has no ask primitive (the plugin can only throw or pass) |
| `ev.permission_mode == "dontAsk"` | Claude auto-denies anything not pre-approved; rendering our own deny makes the reason deterministic and logged |

- **When unattended**, `ASK` becomes `DENY` by default; with `[hooks] unattended_ask = "warn"` (§B.1; values `"deny"` | `"warn"`) it becomes `CONTEXT` plus a user note instead. `combine` implements both.
- **Claude `-p` as a fallback.** Claude Code itself turns a hook `ask` into a deny, with the reason in the tool result, in a `-p` run with no permission host (verified docs). An undetected headless run therefore still never hangs on an ask.
- **Auto mode.** A hook `ask` floors the decision at a prompt in `auto` mode **for unsandboxed Bash** since 2.1.211 (CHANGELOG); behaviour for file tools, MCP tools and sandboxed Bash under auto mode is undocumented (Q-D1).
- **`bypassPermissions`** is treated as attended. See Q-D1.

### §D.4 Failure policy

Every hook declares `on_error` (L6), clamped per firing event (§A.2: `open` on every event that allows only `open`). The runtime derives the failure class from the effective per-event value:

| `on_error` *(values: shared name — proposed)* | Class | Who may use it |
| --- | --- | --- |
| `ask` | guard | engine guards (default for every guard-class pack hook) |
| `deny` | guard, strict | overlays only (validate rejects it in engine and repo-local hooks) |
| `open` | quality | feedback, lint, log and Stop-stage hooks |

| Failure | Guard (`ask`) | Guard strict (`deny`) | Quality (`open`) |
| --- | --- | --- | --- |
| A handler raises, its subprocess times out, or an external handler returns a contract-violating result | `ASK` (→ `DENY` unattended), reason `Playbook guard <id> failed internally; confirm this action manually.`, `degraded=True`, logged | `DENY` | `NONE`; one user note per session per hook (`<id> skipped: internal error — run playbook-hook doctor`); logged |
| The event watchdog fires (deadline reached) | the result for the pending guard handlers as above; results already computed are kept | `DENY` | `NONE` |
| Unparseable payload, missing required field, or a bad argv (`ContractFault`; never a process exit 2). An argv/payload event mismatch is a foreign payload (inert, §D.2.2), not a fault | `pre_tool_use`: `ASK`/`DENY`-unattended; other events: `NONE` + log | `DENY` | `NONE` |
| `guard_config.json` missing, or its sha256 ≠ the lockfile's `guard_config.json` entry (§D.8.1), or `schema_version` newer than the runtime supports (`ConfigFault`) | `ASK` (→ `DENY` unattended) **once per session**, reason `Playbook guard configuration is missing or changed since sync; ask the user to run playbook sync.`; then `NONE` plus a degraded user note. Never an ask on every call (no bricking) | `DENY` every call | `NONE` + one note |
| Trust missing for an external handler or an execution stage | not a failure: skipped, one note per session, logged `untrusted` | same | same |
| State dir unusable (symlinked, not owned by uid, unwritable) | proceed **stateless** (dedupe and budgets off, so the Stop gate can only report, never block), one stderr note | same | same |
| Decision-log write fails | silent, one stderr note per session | same | same |

**Harness-level fail-open is unavoidable and documented** (verified docs):
- In Claude Code only exit 2, or a JSON `deny`/`block`, blocks.
- A non-0/2 exit, a launcher that cannot start, invalid JSON, or a timeout are all non-blocking — Claude shows a non-blocking "hook error" notice and the action proceeds. The exception is PreModelSwitch, which is not a canonical event.
- `onFailure: "block"` (v2.1.295+) turns a command-hook failure into a block on PreToolUse, but has **no effect** on Stop, SubagentStop, TaskCompleted, TeammateIdle or async hooks. Because the default launcher maps every failure to exit 0, `onFailure` can only fire with `--strict-launch` (§C.2.1, overlay strict mode).
- OpenCode's `Plugin.trigger` has no timeout at all. The shim's own timeout fails open (A-C3).

The runtime closes the gap from inside with two mechanisms:
- the watchdog emits a decided result before the harness timeout;
- `ConfigFault` asks rather than allowing.

What it cannot cover (a dead interpreter) is covered by twins:
- the harness-native `permissions.deny` rows rendered from the same tables (§C/§E);
- the session-start heartbeat line, whose absence the CLAUDE.md heartbeat line reports (§C.4.2, §E.1);
- `playbook-hook doctor`;
- the CI twin `playbook ci` (§F.5).

**The one timeout formula (owned here; §C renders it, validate checks it).**
- `deadline_ms[event] = min(ENGINE_DEADLINE_CAP_MS[event], Σ timeout_ms of the hooks enabled on that event)`, rendered into `guard_config.deadlines_ms` at sync. Caps *(constant name proposed)*: `pre_tool_use` 30,000; `post_tool_use` 60,000; `post_tool_use_failure` 30,000; `user_prompt_submit` 30,000; `session_start` 15,000; `pre_compact` 30,000; `session_end` 8,000 (Claude's shared 1.5 s SessionEnd budget is raised by the explicit registration timeout).
- `stop` / `subagent_stop`: `deadline_ms = min(595,000, 1000 · (stop_gate.budget_s + Σ timeout_s of the enabled execution stages))`; default stages only (`budget_s = 3.0`) give 3,000.
- Registration timeout (seconds) = `ceil(deadline_ms / 1000) + 2`, on Claude and (× 1000) on the OpenCode shim. Sync asserts `registration_s * 1000 ≥ deadline_ms + 1000` for every rendered event.
- A member `timeout` above its event's cap is clamped at validate with a warning (H9). Per-member budgets inside the event are enforced by `proc.run` timeouts on subprocesses; in-process handlers are bounded by the event watchdog.

**Watchdog** (`watchdog.py`):
- The deadline per event is `guard_config.deadlines_ms[event]`.
- A daemon timer from `deps.timer_factory` takes the output lock. If the main path has not written yet, it writes the failure-policy result, appends one `degraded` decision-log line, and calls `deps.exit(code)` (default `os._exit`). Both seams exist so the watchdog is unit-tested in-process with a fake timer that fires synchronously and a fake exit that raises a sentinel exception; one subprocess smoke test covers the real `os._exit` (the real call is `# pragma: no cover`), and no timer thread outlives a test (`filterwarnings = ["error"]`).
- It works on POSIX and Windows (no `SIGALRM`).

### §D.5 The Stop coordinator

#### §D.5.1 Ownership and flow

The coordinator is the dispatcher's only `stop` handler (L3). stop-ci-parity-gate owns its policy (§E.0.4). Every other Stop hook contributes a named **stage**, which is the catalog's "tier". `subagent_stop` runs the same engine with a scoped stage list (§D.5.6).

```python
def run(ev: CanonicalEvent, deps: RuntimeDeps) -> CombinedResult:
    if deps.env.gate_off:  # PLAYBOOK_GATE=off, hook env only (§D.7)
        return note_once("Playbook stop gate disabled (PLAYBOOK_GATE=off): work NOT verified.")
    if ev.permission_mode == "plan":
        return NONE
    st = deps.state.stop_chain(ev)  # locked read-modify-write
    if not ev.stop.stop_hook_active or st.turn_id != ev.turn_id:
        st.reset(ev.turn_id)  # a new stop chain
    fp = deps.git.fingerprint()  # §D.5.3; None outside git or on error
    plan = plan_stages(cfg.stop_gate, ev, deps.ledger, fp, deps.git.head_tree())
    if fp is not None and (fp.unchanged_vs_head or fp == deps.state.last_green()):
        plan = plan.only(
            needs_diff=False
        )  # e.g. output-contract still runs (review tasks have no diff)
    if st.blocks >= cfg.stop_gate.max_blocks:
        return allow_not_verified(st.last_stage, "block budget exhausted")
    if fp is not None and fp == st.last_blocked_fp:
        return allow_not_verified(st.last_stage, "unchanged since the last block")
    results = run_stages(plan, budget_s=cfg.stop_gate.budget_s, deps=deps)
    return compose(results, st, fp, deps)  # block / notes / record green
```

`allow_not_verified` returns `NONE` plus the user note `Playbook gate RED at <stage> — NOT verified.` Red is never presented as green.

`compose`:
- **Block.** If any stage is `red`, it increments `st.blocks`, sets `st.last_blocked_fp = fp` and `st.last_stage`, and returns one `DENY` whose reason is the combined text (§D.5.4).
- **Green.** If every planned default stage is `green` and `fp` is known, it records `last_green = fp` (worktree-level, not session-level) and adds the first-green-per-fingerprint note `verified locally (<stages>); the CI matrix is authoritative` (§E).
- **Not verified.** A `skipped` stage (timeout, crash, tool signature changed, toolchain missing) adds `NOT verified: <stage> skipped (<category>)` and prevents recording green.
- **Warnings.** `warn` lines go to user notes, or into the block reason when there is one.

**Block budget.** A stop chain is the sequence of Stops linked by `stop_hook_active=true`. Claude sets it false on the first Stop of a turn. It is reset on a new `turn_id` (Claude `prompt_id`) or when `stop_hook_active` is false. `max_blocks = 2` (`[hooks.stop-ci-parity-gate] max_blocks`, §E). Combined with the fingerprint rule, Claude's own cap of 8 consecutive continuations (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`) is never reached.

#### §D.5.2 Stage order and execution

The run order is the engine constant `STOP_STAGE_ORDER: Final[tuple[str, ...]]` *(shared name — proposed; `hook_runtime/stop/stages.py`)*, whose values and owners are §E.0.4's table. Each Stop-stage hook declares only its stage name, in `handler.config.stage`; `priority` never orders stages.

`drift` → `lint` → `quality-metrics` → `docstrings` → `gate-integrity` → `secrets` → `notebooks` → `verify-claim` → `output-contract` → `tests-nudge` → `typecheck` → `tests` → `coverage`

```python
class StageCost(IntEnum):
    # Mirrors evaluators/scope.py:39 CostTier values; not imported, because importing
    # evaluators.scope runs evaluators/__init__ (heavy). A test asserts the ordering stays equal.
    DETERMINISTIC = 0
    EXECUTION = 1


@dataclass(frozen=True, slots=True)
class StageResult:
    stage: str
    status: str  # green | red | warn | skipped
    lines: tuple[str, ...] = ()  # model-facing diagnostics (sanitized, quote_data for repo strings)
    user_lines: tuple[str, ...] = ()  # always-to-user lines (e.g. gate loosenings, §E)
    skip_category: str = ""  # timeout | crash | tool_changed | toolchain_missing | untrusted


class Stage(Protocol):
    name: str
    cost: StageCost
    needs_diff: bool
    mode: str  # block | warn (from config)

    def applies(self, plan: StopPlan) -> bool: ...  # e.g. drift: ledger touched canonical/generated

    def run(self, plan: StopPlan, deadline: float) -> StageResult: ...
```

**Execution rules:**
1. All applicable **deterministic** stages run in order, each with `timeout = min(stage.timeout_s, remaining budget)`. The default budget is `budget_s = 3.0` for the default stages.
2. `tests-nudge` runs only when stages `drift`…`verify-claim` produced no `red` (§E).
3. **Execution** stages (`typecheck`, `tests`, `coverage`) run only when all of these hold. This is the cost-tiered short-circuit of `evaluators/scheduler.py:52` `schedule(op="and")`, mirrored here.
   - no deterministic stage is `red`;
   - the stage is enabled (opt-in);
   - `TrustStore.allows(repo.common_dir, scope="exec_stages", digest=sha256(stop_gate.stages))` holds, so a changed stage list needs re-approval;
   - the stage's tool pin matches its stat signature (§D.8.3).

   Otherwise the stage is `skipped` with category `untrusted` or `tool_changed`, and the note never says green.
4. **Commands.** Every stage command is built from the machine-independent `stop_gate.stages[]` record (logical `tool` + `args`) and the per-machine pins in `machine.json` (§D.8.3), never from a repo file read at run time. Where `uv` is used it is `uv run --frozen --no-sync …` (L8; validate rejects other forms). All stage child processes go through `proc.run` with `timeout=` and `stdout=PIPE`.
5. **The `quality-metrics`, `docstrings` and `coverage` stages** import `evaluators.metrics_gate` in-process (the branch-local allow-list, §D.1). They call `run_metrics_gate`, the library entry §F.0.3 extracts from `commands/metrics.py:574` `run()`, so they never parse printed text. **Prerequisite P-D3 is §F.0.3 item 1** (the extraction, plus the `timeout=` on `_git_show`'s `subprocess.run`, `commands/metrics.py:212`, which §F.0.3 item 7 adds; the coordinator watchdog bounds it meanwhile). They are the documented exception that reads `[metrics]` live (§E.0.2).

#### §D.5.3 Working-tree fingerprint and `SafeGit`

**Fingerprint** (`SafeGit.fingerprint() -> Fingerprint`). It is a real git tree id, computed in a temp index so the user's index is never touched:
1. Copy `<git_dir>/index` (equivalently `git rev-parse --git-path index`) to `<state>/tmp/index.<pid>`. If the index is missing, start empty.
2. `git ls-files --others --exclude-standard -z` lists the untracked set. Each untracked path is stat'ed. A path is **excluded** if it matches `secret_path_globs`, or if it is larger than `fingerprint_max_file_bytes` (default 5 MiB; `*.pt`, `*.pkl` and the like, §E stop-diff-sweep). So are tracked paths matching `secret_path_globs`.
3. `GIT_INDEX_FILE=<tmp> git add -A --pathspec-from-file=- --pathspec-file-nul` with the pathspec list `.` followed by `:(exclude,literal)<path>` for each excluded path. This needs git ≥ 2.26.
4. `GIT_INDEX_FILE=<tmp> git write-tree` gives `tree_id`. The temp index is deleted.
5. `aux` = `sha256` over the sorted `(path, size, mtime_ns)` of the excluded paths. Secret contents are never read or hashed, and large files are never hashed. `Fingerprint = (tree_id, aux)`, rendered `<tree_id>` when `aux` is empty and `<tree_id>:<aux[:12]>` otherwise.
6. `unchanged_vs_head` = `tree_id == HEAD^{tree}` and `aux == ∅`. The tree id doubles as git-commit-push-policy-guard's advisory cache key (§E), and it is only valid when `aux` is empty.

**`SafeGit`: every git invocation in the runtime goes through it.** Verified on this machine (Apple Git 2.39.3), in a scratch repo where `.gitattributes` maps `*.txt` to a filter whose `filter.<name>.clean` runs a command:
- `GIT_INDEX_FILE=<tmp> git add -A` **executed the clean filter**.
- `git diff HEAD` **also executed it**.
- With `-c filter.<name>.clean=`, neither executed it, and the resulting tree id was unchanged.
- `git --attr-source=<empty tree>` (git ≥ 2.40) is **unavailable** on 2.39.3, so it cannot be the mitigation.

Because `.git/config` and `.gitattributes` are agent-writable, an unhardened Stop hook would be an edit-to-exec escalation (catalog principle 8). `SafeGit.run(args, *, timeout)` therefore:
- **Neutralizes filter drivers.** It discovers them once per process (`git config --null --name-only --get-regexp '^filter\.'`, cached in `<state>/cache/git-filters.json` keyed by the mtimes of the repo, worktree and global config files). For each driver it prepends `-c filter.<n>.clean= -c filter.<n>.smudge= -c filter.<n>.process=`.
- **Disables other hook points.** It prepends `-c core.fsmonitor=false` (`core.fsmonitor` can name an executable), and adds `--no-ext-diff --no-textconv` to every `diff`/`log -p`/`show` call. It uses `cat-file -p <rev>:<path>` for blob reads.
- **Scrubs the child env.** It removes `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` (except its own), `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`, `GIT_CONFIG_VALUE_*` and `GIT_EXTERNAL_DIFF`. It sets `GIT_OPTIONAL_LOCKS=0`, `GIT_TERMINAL_PROMPT=0`, `GIT_PAGER=cat` and `LC_ALL=C`.
- **Bounds time.** Timeouts are 2 s on hot-path calls (pragma checks, §E git guards) and 5 s in Stop stages. A timeout raises `GitTimeout`, which is handled by the failure policy.
- **Answers each distinct read once per dispatch.** A dispatch is one snapshot of the working tree, so the dispatcher's git (`_ports.LazyGit`) is a memoizing `SafeGit` (`_git_memo.MemoGit`): a call to a read-only subcommand (`rev-parse`, `ls-files`, `diff`, `cat-file`, `grep`, `status`, `log`, `for-each-ref`, `merge-base`) with the same argv, stdin and accepted exit codes spawns once, and later askers reuse its answer. Temp-index calls (the fingerprint's `add` / `write-tree`) always spawn, a failed or timed-out call is not stored, and the CLI twins keep a plain `SafeGit` (a command may change the tree between its own reads). A default-tier Stop over a changed tree went from 24 git spawns (`rev-parse HEAD^{tree}` and `ls-files --others` 5x each, `diff HEAD` 4x) to 11.

**Known cost.** `git add -A` writes loose blobs for modified and untracked non-excluded files into the object store, where `git gc` prunes them. See Q-D4. A `stat`-mode fallback fingerprint (sha256 over `git status --porcelain=v2 -z` plus per-path stat) is used when git is older than 2.26 or filter discovery fails. In that mode `unchanged_vs_head` is decided by an empty status, and the commit-policy cache key is unavailable.

#### §D.5.4 The combined reason (≤ 40 lines)

```
Playbook gate RED — fix before finishing (tree 1a2b3c4d, block 1/2):
[drift] ".continue/rules/10-x.md" differs from its source. Run: playbook validate && playbook sync
[lint] "src/x.py":12 F401 `os` imported but unused  (1 new; 14 pre-existing ignored)
[quality-metrics] "src/x.py"::parse cyclomatic_complexity 0.71 -> 0.42 (regression)
[gate-integrity] "src/y.py":40 added `# type: ignore` with no justification
[secrets] "config.py":3 aws-access-key (length 20): move it to env or the secret manager
Also: New public API without tests: "src/x.py"::foo
```

- **Line budget.** 1 header line plus at most 2 footer lines. Each red stage is guaranteed 3 lines; the remaining lines go to stages in order. A stage that overflows ends with `(+N more)`.
- **Ordering.** `warn` lines follow the red stages under `Also:`.
- **Advice targets.** Toolchain-missing advice is one line addressed to the user (`ruff not found on the pinned path; ask the user to run playbook sync`), not a command for the agent.

#### §D.5.5 Kill switch and plan mode

- **`PLAYBOOK_GATE=off`** in the hook process env skips the whole coordinator and `subagent_stop`. The decision log records `escape: PLAYBOOK_GATE` once per session, and the user gets one note. A `PLAYBOOK_GATE=off` prefix on a Bash command has no effect (§D.7).
- **`permission_mode == "plan"`** returns `NONE` silently, because no edits are possible.

#### §D.5.6 `subagent_stop` and OpenCode

- **`subagent_stop`** runs the same engine with:
  - `stages = [hooks.subagent-stop-verify].stages` (default `["lint"]`);
  - the scope set to the touched files, parsed read-only from `agent_transcript_path` tool inputs;
  - fingerprint and state keyed by `agent_id`, under the subagent's `cwd` worktree;
  - its own `max_blocks = 2` per `agent_id`.

  Execution stages need the same trust entry, and are serialized with `locks/exec-stage.lock` (§E).
- **On OpenCode**, `session.idle` cannot block. The coordinator runs with `can_block=False`, which only suppresses the block budget:
  - no block budget is consumed;
  - the combined result is **returned on stdout** (decision `deny` + the combined reason, prefixed `gate RED at <stage> — NOT verified`, or `context`), never stored as a deferred note;
  - the shim's `carry` map is the single carrier that injects it on the next turn (§C.3.6).

### §D.6 State and logs

#### §D.6.1 Location, permissions, concurrency

- **State root** = `<git_dir>/playbook-hooks`. This equals `git rev-parse --git-path playbook-hooks`, because `playbook-hooks` is not a common-dir path; the integration test asserts this. It is per worktree, never committed, outside the working tree (so it never shows up in repo search), and survives `git clean -x`.
- **Outside git:** there is no state root. Hooks are git-only in v1: without a git dir there is no interpreter pin, so the launcher and shim never start the dispatcher (§C.2.7, QC-9 resolved).
- **Permissions.** Directories are created with `os.makedirs(mode=0o700)`, followed by an explicit `chmod 0o700` (umask). Files are opened with `O_WRONLY|O_CREAT|O_APPEND|O_NOFOLLOW` and mode `0o600`. On POSIX the root is refused (stateless mode) if it is a symlink or not owned by `os.getuid()`.
- **Concurrency.** Claude runs parallel tool calls and subagents as concurrent processes.
  - JSONL appends are one `os.write` per line, each ≤ 4 KiB, with `O_APPEND`.
  - JSON state files are read-modify-written under `fcntl.flock(LOCK_EX)` (POSIX) or `msvcrt.locking(LK_NBLCK)` (Windows) on `locks/<name>.lock`, with a 200 ms acquisition limit. On timeout that one operation runs stateless. Writes are temp file + `os.replace`.

```
<git_dir>/playbook-hooks/            0700
  VERSION                            "1"
  sessions/<sha256(session_id)[:16]>/
    ledger.jsonl                     touched paths + verify runs (§D.6.3)
    session.json                     once-keys, flags (taint), asked tool_use_ids, deferred notes
    stop.json                        stop chain: turn_id, blocks, last_blocked_fp, last_stage
  stop/last_green                    fingerprint of the last all-green tree (worktree-level)
  stop/lint-baseline-<head_tree>.json
  coverage/<tree>.json               coverage measurement snapshots (paths owned by §F.1.2)
  suite/<tree>/                      shared SuiteRun junit + coverage XML, per fingerprint (§F.1.2)
  decisions-YYYY-MM.jsonl            guard-decision-log (§D.6.2)
  audit-YYYY-MM.jsonl                local-audit-log (opt-in / overlay)
  checkpoints/<session>.json         precompact-checkpoint (ids/offsets only, §E)
  interpreter                        engine-interpreter pin (§C.2.7; plain text, first writer wins)
  machine.json                       per-worktree tool pins and resolved resource roots (§D.8.3)
  cfg-digest.json                    cached guard_config digest from the lockfile (§D.8.1)
  launcher.log                       launcher failures (§C.2.7)
  cache/git-filters.json, cache/git-version
  locks/  tmp/
```

**TTL sweep.** It runs at `session_start`, and lazily from `stop` if the last sweep is more than 24 h old. It removes:
- `sessions/*` older than `[hooks] state_ttl_days` (§B.1; default 7);
- baselines for non-current `HEAD^{tree}` older than 7 days;
- `tmp/*` older than 1 day;
- decision logs older than `[hooks.guard-decision-log] retain_months` (default 6).

A month file over 5 MiB rotates to `decisions-YYYY-MM.<n>.jsonl`. Each sweep is bounded to 500 entries and 20 ms and resumes next time. SessionEnd is not relied on: it is not portable and does not fire on a crash.

#### §D.6.2 guard-decision-log format

There is one JSON line per decision event. `security/audit.py` defines two functions, cited identically everywhere: the generic `append_jsonl(path: Path, record: Mapping[str, object]) -> None` (one `O_APPEND` write ≤ 4 KiB, lock, rotation; shared with the SPEC §17.4 sync audit line and local-audit-log's `append_activity`) and the typed wrapper `append_decision(state_dir: Path, record: GuardDecisionRecord) -> None` that guard-decision-log uses (§E.5). Lines use `json.dumps(sort_keys=True, separators=(",", ":"))`.

```json
{"v":1,"ts":"2026-10-14T10:30:00.123Z","harness":"claude_code","session_id":"abc123","event":"pre_tool_use","hook_id":"destructive-command-guard","rule_id":"rm_root","decision":"deny","effective":"deny","tool_name":"Bash","tool_class":"shell","unattended":false,"degraded":false,"escape":null,"canary":false,"latency_ms":41}
```

**`decision` values:**
- `deny`, `ask`, `context` (from guard-class hooks only);
- `ask→deny`;
- `override`: a post-tool event for a `tool_use_id` in the session's asked set, meaning the user approved an ask;
- `degraded` (failure policy);
- `escape` (a kill switch, allow env var or `PLAYBOOK_HOOK_WRAPPER_PREFIXES` used, its name in `escape`; for a variable that was ignored, `rule_id` names it and `escape` says why: `escape_via_settings_env`, or `wrapper_prefix_rejected` for a refused wrapper entry);
- `untrusted` (an external handler or execution stage skipped);
- `contract_violation`;
- `canary` (doctor or heartbeat self-tests, also tagged `canary: true`).

**Never stored:** command text, paths, prompts, file contents, reason or context text, or environment values. Free-form Bash cannot be redacted reliably (`mysql -pS3cret`, `curl -u user:pass`), so it is not stored at all. `rule_id` and `hook_id` are static identifiers from code or config.

The log never blocks, never prints to the model, and never touches the network. `local-audit-log` (opt-in/overlay) uses the same writer with structure-only commands (§E).

#### §D.6.3 Session ledger

`ledger.jsonl` is appended on `post_tool_use` and `post_tool_use_failure`, and read by the Stop stages, `subagent_stop` and the source-changed branch:

```json
{"v":1,"ts":"…","ev":"post_tool_use","tc":"edit","tool":"Edit","paths":["src/x.py"],"cats":["py"]}
{"v":1,"ts":"…","ev":"post_tool_use","tc":"shell","writes":["build/out.txt"],"cats":["generated"]}
{"v":1,"ts":"…","ev":"post_tool_use","tc":"shell","verify":"lint","ok":true}
{"v":1,"ts":"…","ev":"post_tool_use_failure","tc":"shell","verify":"tests","ok":false,"exit":1}
```

- **Paths** are repo-relative. A path outside the repo is recorded as `"<outside>"`, and a path matching `secret_path_globs` as `"<secret-path>"`. Absolute paths and secret paths are never written.
- **`cats`** come from `guard_config.path_classes`: `canonical`, `detector_input`, `generated`, `control_plane`, `py`, `test`, `notebook`, `eval_fixture`, `secret`.
- **`verify`** is the `stop_gate.verify_commands` id matched against the segment's effective argv (§E verify-claim). The command and every row are unwrapped with `guard_config.shell`, the same unwrapping the guards judge a command by (§D.2.5: configured `wrapper_prefixes`, `runner_wrappers`, the built-in launcher table), then a leading `python -m` is dropped; so `proxy uv run pytest -q` counts as `pytest` once `proxy` is a wrapper, and a row written as `timeout 900 pytest -x` matches `pytest -x`. Green runs arrive on `post_tool_use`. Red runs arrive on `post_tool_use_failure`, whose Bash error begins `Exit code N`.
- **Caps.** At most 2,000 lines per session. Beyond that the ledger compacts to a path-set summary.

#### §D.6.4 Session flags and deferred notes

`SessionState` (`session.json`, locked read-modify-write) offers:

| Method | Purpose |
| --- | --- |
| `once(key) -> bool` | true only the first time per session; used for context dedupe and one-note-per-session |
| `flag(name)`, `set_flag(name)` | session flags, e.g. taint-escalation's `tainted` (§E); a flag clears only with a new session |
| `mark_asked(tool_use_id)`, `was_asked(tool_use_id)` | the asked set, max 64 ids; drives the `override` log |
| `push_note(text)`, `drain_notes() -> list[str]` | deferred notes, max 5 |

Deferred notes (e.g. quality-hook failure notes produced where no user-note channel exists) are drained per harness:
- **Claude:** into the `systemMessage` of the next `user_prompt_submit` (registered only while a hook binds it) or `session_start` dispatch for the same session. Notes are pushed only on `session_end` and `pre_compact`, and each is followed by a `session_start` (a new session, or `source: compact`), so the default tier delivers them without a `user_prompt_submit` registration.
- **OpenCode:** into the wire `notice` of **every** dispatch for the session (user_prompt_submit is not rendered and session_start is memoized by the shim, so neither could carry them); the shim pushes notices into the next model request (§C.3.2). OpenCode Stop results are not deferred notes: they are returned on stdout (§D.5.6).

### §D.7 Escape hatches, kill switches, pragmas

Escape hatches are read **only from the dispatcher process environment** (`os.environ` of the hook process, inherited from the harness). They are never read from a parsed segment's `env` prefix (a `PLAYBOOK_GATE=off git commit …` prefix is ignored, and control-plane-guard reports it, §E.1), from `guard_config`, or from anything a session-start hook appended to `CLAUDE_ENV_FILE`; the runtime never writes `CLAUDE_ENV_FILE`.

**Settings `env` keys reach `os.environ`.** Claude Code sets every `env` key from user, project, local and managed settings on the subprocesses it starts, hooks included, so `os.environ` alone cannot tell a launching-shell override from a settings-file one. Whenever any variable below is present, `escape.py` reads the `env` objects of the settings files Claude loads (repo `.claude/settings.json`; the effective `.claude/settings.local.json`, resolved as in §E.1; `${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json`) — about 1 ms, only on that rare path — and **ignores** a hatch defined there with the same value, logging `escape_via_settings_env` once per session and surfacing it in the next briefing. control-plane-guard's deny on `env` edits remains, labelled a speed bump. Values must match exactly:

| Variable | Exact value | Effect | Logged / noted |
| --- | --- | --- | --- |
| `PLAYBOOK_HOOKS` | `off` | step 1 of the pipeline: parse only `session_id`, write no output, exit 0 | `escape: PLAYBOOK_HOOKS` once per session; no note (there is no output channel by design) |
| `PLAYBOOK_GATE` | `off` | `stop` and `subagent_stop` skip all stages | once per session; user note `work NOT verified` |
| `PLAYBOOK_ALLOW_GENERATED_EDIT` | `1` | guard-generated-outputs returns `NONE` (§E.1) | once per session; user note |
| `PLAYBOOK_HOOKS_DISABLE` | comma-separated hook ids | step 4 of the pipeline skips the listed ids unless `mandatory` (§B.2) | once per session per id; user note |
| `PLAYBOOK_HOOK_WRAPPER_PREFIXES` | comma-separated prefixes, each one or more words (`proxy,proxy run`); spaces normalized | after the config loads, the accepted prefixes join `guard_config.shell.wrapper_prefixes` for this dispatch, so every shell guard and the verify-run tags (§D.6.3) see the launched command. An entry any token of which names a guarded command, launcher, runner or shell (`wrapper_policy.hidden_program`, the H21 rule) is never applied | `escape: PLAYBOOK_HOOK_WRAPPER_PREFIXES` once per session while a prefix is in effect; a refused entry: one `escape` line `rule_id: PLAYBOOK_HOOK_WRAPPER_PREFIXES`, `escape: wrapper_prefix_rejected` (never the value), and a `doctor` warning |

**Pragmas.** The pragmas are `playbook: allow-secret` and `playbook: trusted-artifact` (§E), found in a line comment. A pragma on line `L` of `path` is honored **only if present at HEAD**: `escape.pragma_at_head(git, repo_rel, line_text)` holds when `SafeGit` `cat-file -p HEAD:<path>` contains a line equal to `line_text` after whitespace strip.
- **Cost.** One 2 s-bounded git call, made only when a payload or diff contains a pragma.
- **New or moved pragmas.** A pragma added this session, or in a file absent at HEAD, is not honored. The guard returns `ASK` (`DENY` unattended), and the `gate-integrity` stage always lists it to the user (§E).

### §D.8 `guard_config.json`

#### §D.8.1 Envelope, digest, schema

- **Rendered at sync** by the engine. jinja2 is fine there; the runtime never imports it.
- **Location:** `.coding-agent-playbook/hooks/guard_config.json`, a sync-level committed output (§C.0, A-C4).
- **Canonical serialization:** `json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"`. The digest is therefore `sha256(file bytes)`. The file is ≤ 256 KiB (validate) and parses in ≤ 5 ms.
- **Integrity.** The file is a whole-file `LockEntry` (`kind = "runtime"`) in `.coding-agent-playbook.lock`, guarded by guard-generated-outputs and control-plane-guard. The expected digest is that lock entry's `sha256` — **not** an argv value, so registration bytes stay stable when only `guard_config.json` changes (§C.2.3). To keep `tomllib` off the hot path, the dispatcher caches `{lock_size, lock_mtime_ns, lock_ino, guard_config_sha256}` in `<state>/cfg-digest.json`: `session_start` (where `tomllib` is allowed) refreshes it, and any other event re-parses the lockfile (a branch-local `tomllib` import, §D.1) only when the lockfile's stat differs from the cache. The runtime hashes `guard_config.json` on load; a mismatch is a `ConfigFault` (§D.4).
- **No session snapshot.** Settings files are watched and hook edits apply to the running session (verified). The digest's value is that tampering needs **two** coordinated edits (`guard_config.json` and the lockfile), both guarded, and that removing a registration needs a `settings.json` edit, which control-plane-guard denies (§E.1).
- **`schema_version: 1`.** The runtime supports `[1, 1]`. Additive keys within a version are ignored by older runtimes. A breaking change bumps the version. A config newer than the runtime is a `ConfigFault` (`engine older than guard_config schema N`).
- **Why JSON.** The hot path avoids `tomllib` (about 19 ms) and every engine import. Hooks never read their commands or policies at run time from agent-editable repo files (catalog principle 12). The one exception is the `quality-metrics` `[metrics]` read (§E.0.2).

#### §D.8.2 Contents

§D owns the envelope and the runtime keys. §E.0.5 owns the pack tables, reproduced by name only.

| Key | Content | Rendered at sync from | Read by |
| --- | --- | --- | --- |
| `schema_version`, `engine_version` | int, str | engine | runtime |
| `hooks.<hook-id>` | exactly `ResolvedHook.to_json()` (§A.7): `id`, `source_package`, `events`, `priority`, `matcher`, `handlers.<event>` (`kind: builtin`\|`entry_point`\|`external`, name/target/argv, merged `config`), `decisions`, `timeout_ms`, `on_error.<event>`, `supports`, `mandatory`, `script_sha256` | `hook_policy.resolve_effective_hooks` (§A.7) after the layer merge and the consumer's `[hooks.<hook-id>]` layer (§B.1) | selection (§D.3.2), handlers |
| `deadlines_ms` | per-event watchdog deadlines | the §D.4 formula (derived, not configured) | watchdog; §C registration timeouts |
| `unattended_ask` | `"deny"` \| `"warn"` | `[hooks]` (§B.1) | §D.3.6 |
| `logging` | `{decisions: bool, audit: bool, audit_mode}` | guard-decision-log / local-audit-log enablement | §D.6.2 |
| `shell` | `{wrapper_prefixes[], runner_wrappers[]}` | engine defaults ∪ `[hooks]` ∪ overlays (add-only); at run time ∪ `PLAYBOOK_HOOK_WRAPPER_PREFIXES` (§D.7) | §D.2.5 |
| `path_classes` | `{canonical, detector_input, generated, control_plane, py, test, notebook, eval_fixture}` globs | detector facts + layout + `protected` | ledger `cats`, stage planning |
| `secret_path_globs` | list | `security/patterns.py::SECRET_PATH_GLOBS` ∪ overlay additions (add-only, L2) | path guards, fingerprint exclusions, ledger masking |
| `secret_rules` | engine ruleset id/version + overlay `extra_patterns` (compiled and ReDoS-checked at validate) | `security/patterns.py` + overlays | secret-content-guard, the `secrets` stage |
| `destructive` | engine table version + overlay rows (add-only) | the §E/§F source module + overlays | destructive-command-guard |
| `allowlists` | dependencies, egress hosts, MCP servers (overlay data) | overlays / `[hooks.<id>]` | §E safety guards |
| `sentinel`, `protected`, `control_plane`, `precommit`, `facts`, `applicability`, `stop_gate`, `prompts`, `eval` | §E.0.5 table. `protected.output_dirs` comes from each enabled adapter's `_output_directories(repo_root)` (`adapters/base.py:64`, `claude_code_adapter.py:155`, `continue_adapter.py:83`, `opencode_adapter.py:96`, `agent_harness_adapter.py:436`) made repo-relative, plus the singleton outputs in the written set (`.claude/CLAUDE.md`, `AGENTS.md`) | §E.0.5 | §E handlers, coordinator |

**Single sources.**
- `src/coding_agent_playbook/security/patterns.py` *(NEW, stdlib only)* defines `SECRET_PATH_GLOBS: Final[tuple[str, ...]]` and the secret content rules. It is imported by:
  - the sync-time `guard_config` renderer;
  - `detector.py`, which today skips only `_IGNORE_DIRS` (`detector.py:20`) and so does not honor SPEC §17.3's "never reads `.env*`, `*.pem`, `*.key`, `*credentials*`";
  - `playbook scan-secrets` (§E.4);
  - the `security/secrets.py::scan_text` scanner.

  The runtime receives the globs only through `guard_config`, so a guard and the detector can never disagree.
- The sentinel string comes from `renderer.SENTINEL` (`renderer.py:43`) at sync and is never hand-copied (the L7 wording reconciliation lands first).

#### §D.8.3 Per-machine pins (`machine.json`): never in `guard_config.json`

**Invariant (locked; closes Q-D8):** `guard_config.json` is committed and byte-compared by `sync --check` on every machine and in CI, so it carries **only machine-independent data**: logical tool names, args, timeouts, repo-relative globs and paths, and package-relative resource identifiers (e.g. `pkg:coding_agent_playbook/resources`). Every absolute path and stat signature lives in `<git_dir>/playbook-hooks/machine.json` *(shared name — proposed)*, rewritten by every write-mode `playbook sync`/`init` (never by `--check`). The engine interpreter is **not** in it — that is the separate `interpreter` pin file the launcher reads (§C.2.7):

```json
{"schema_version":1,"engine_version":"…",
 "tools":{"ruff":{"argv":["/abs/.venv/bin/ruff"],"sig":[31457280,1728900000000000000,1234567]},
          "cz":{"argv":["/abs/.venv/bin/cz"],"sig":[…]},
          "project_python":{"argv":["/abs/.venv/bin/python3.13"],"sig":[…]}},
 "resource_roots":{"pkg:coding_agent_playbook/resources":"/abs/site-packages/coding_agent_playbook/_catalog/core"}}
```

- `sig` is `[st_size, st_mtime_ns, st_ino]`, captured at sync. `project_python` is the project's interpreter for test/coverage stages (§F.1), distinct from the engine pin.
- At run time, a stage whose tool `sig` no longer matches is `skipped` (`tool_changed`): **NOT verified**, never green.
- A missing `machine.json` in a fresh worktree skips the tool-backed stages with one note. That note is addressed to the user: `run playbook sync in this worktree`.
- `stop_gate.stages[]` keeps only the machine-independent part: `name`, `owner`, `cost`, `tool` (a logical name), `args`, `timeout_s`, `needs_diff`, `mode` (§E.0.5 uses the same record). Test: `tests/unit/test_guard_config.py::test_render_is_machine_independent` renders `guard_config.json` under two different `sys.prefix` values and two home directories and asserts byte equality.

### §D.9 Testability

**Seams (dependency injection, no ad-hoc monkeypatching).** `RuntimeDeps` is passed into `run_event`. Every external effect has one seam:

| Seam | Real | Fake (in `tests/hook_runtime/fakes.py`, NEW) |
| --- | --- | --- |
| harness I/O | `harness/claude.py`, `harness/opencode.py` | `FakeHarness`: builds per-harness payloads from a canonical spec and decodes `WireOutput` back to `(decision, reason, context, notes, exit_code)` |
| git | `SafeGit` (`GitPort` Protocol) | `FakeGit`: scripted `head_tree`, `fingerprint`, `diff_added`, `cat_head`, `ls_untracked`; it records calls |
| processes | `proc.run` / `proc.which` | `FakeProc` (records argv; scripted results); stage tools via §E's `FakeStageRunner` |
| clock | `time.monotonic` / `time.time` | `FakeClock` |
| trust | `TrustStore` (user-local file) | `FakeTrustStore` |
| state | `StateStore(root=tmp_path)` | a real store in `tmp_path` |

**Autouse stubs** (repo memory: CI may lack binaries inside pytest). `tests/hook_runtime/conftest.py` has an autouse fixture, mirroring `tests/cli/conftest.py:23` `_stub_uv_sync_for_cli`, that relies on the DI seam rather than patching modules: every in-process `run_event` call gets `RuntimeDeps(proc=FakeProc())` by default, and an unscripted `FakeProc` call raises `AssertionError("unexpected subprocess: <argv0>")`. `proc.py` imports `subprocess` lazily, so the fixture never patches `…proc.subprocess.run` (that attribute does not exist at fixture time) nor the global `subprocess.run` (which would break the tests that legitimately spawn interpreters: `test_import_budget.py`, `test_claude_launcher.py`, the gated latency tests and `real_git` tests). Tests that need real subprocesses request the plain `real_proc` fixture (no new marker, as `--strict-markers` requires), and the `real_git` fixture skips when `shutil.which("git")` is `None`. Everything runs under `filterwarnings = ["error"]` (`pyproject.toml:178`), so the runtime must close every fd and temp file and leave no timer thread running.

**Golden payloads.**
- **Location (locked; closes Q-D7):** `tests/fixtures/hook_payloads/{claude_code,opencode,foreign}/<event>/<case>.json`, each with a `<case>.expected.json` holding the exact `WireOutput`. Runtime tests live in `tests/hook_runtime/`, pack and tool-hook tests in `tests/hooks/`, security-library tests in `tests/security/`; all read payloads through the root `hook_payload` fixture.
- **Provenance:** each payload carries `"_fixture": {"harness_version": "2.1.296" | "1.19.0", "source": "captured|docs"}`, which the parsers ignore as an unknown key. They are captured from the pinned harness versions by a documented manual recipe (a temporary `tee` registration), never in CI.
- **Coverage:** parser and renderer cases for every canonical event × harness, including Windows backslash paths, the OpenCode `apply_patch` envelope, absent `permission_mode`, absent `prompt_id`, the `stop_hook_active` chain, truncation, and a malformed payload.
- **Shared with §E/§F.** A root-level `tests/conftest.py` fixture `hook_payload(harness, event, case)` serves these files to `tests/hook_runtime/`, `tests/hooks/` and `tests/security/`. The `foreign` set holds VS Code Local, Copilot CLI and Cursor payloads for the §C.5.2 inert check.

**Parametrized red-team tables** (`tests/hook_runtime/test_shell.py`, `test_paths.py`, `test_combine.py`, `test_render_*.py`):
- **Shell parsing, mapping input to effective `argv`/`wrappers`/`dynamic`:**
  - `proxy git push --force origin main`;
  - `env FOO=1 sudo -u root timeout 5 rm -rf /`;
  - `bash -lc 'rm -rf ~'`;
  - `xargs rm -rf < list`;
  - `find . -name x -exec rm {} \;`;
  - `git commit -m "mentions -n" <<EOF …--no-verify… EOF` (heredoc not flagged);
  - `rm -rf "$(pwd)"/x` (dynamic);
  - an unbalanced quote (`parse_error`);
  - more than 256 segments (`limit`);
  - PowerShell `Remove-Item -Recurse -Force`.
- **Paths:**
  - `platform="darwin"`: `.ENV` matches `.env*`;
  - `platform="win32"`: `C:\\proj\\.CLAUDE\\settings.json` maps to `.claude/settings.json`;
  - a symlink into `.git/`;
  - a sibling linked-worktree path (`same_repo=True`);
  - a hard link (`nlink=2`).
- **Combination and rendering:**
  - deny + ask + context → deny with ≤ 4 lines and `(+N more)`;
  - ask unattended → deny with the prefix;
  - a Stop context-only result → `systemMessage` and **no** `additionalContext`;
  - a PreToolUse deny → exit 2 + JSON + stderr;
  - OpenCode deny → process exit 10 + wire result;
  - the closed-key allowlist (no `allow`, `updatedInput`, …) over a fuzzed set of handler results.
- **Failure policy:** a raising guard → ask (deny unattended); a raising quality hook → none + exactly one note per session; `ConfigFault` → ask once, then none; a decision outside the hook's `decisions` → `contract_violation`; a usage error in `dispatch` argv → failure policy, never exit 2; the watchdog, driven in-process by a synchronous fake timer and a fake `exit` that raises a sentinel, writes the decided output exactly once; one subprocess smoke test exercises the real `os._exit`.
- **Stop coordinator** (`FakeGit` + `FakeStageRunner`):
  - unchanged tree → zero stage calls;
  - three red stages → exactly one combined reason ≤ 40 lines;
  - second Stop on the same fingerprint → none + `NOT verified`;
  - `blocks == max_blocks` → none + note;
  - plan mode → none;
  - `PLAYBOOK_GATE=off` in hook env → none + note, while the same var in a Bash prefix has no effect;
  - untrusted repo → execution stages never invoked (`FakeProc` spy);
  - `tool_changed` → skipped, never green;
  - `output-contract` still runs on an unchanged tree.
- **`SafeGit` (`real_git`):** a repo whose `.gitattributes` and `.git/config` define a clean filter that touches a marker file → `fingerprint()`, `diff_added()` and `cat_head()` never create the marker; the fingerprint is stable across `git add`; an untracked `.env.prod` changes `aux` but its content is never read (fs spy).
- **State and log:**
  - two concurrent processes appending 200 decisions each → valid JSONL with 400 lines;
  - a decision line for `mysql -pS3cret …` contains neither `S3cret` nor the path;
  - dir mode `0o700`, file mode `0o600`;
  - a symlinked state root → stateless mode;
  - the TTL sweep is bounded.
- **Git-dir resolution:** `find_repo` equals `git rev-parse` (main and linked worktree); the state root equals `git rev-parse --git-path playbook-hooks`.

**Import-light test** (`test_import_budget.py`, deterministic, in the default run). In a fresh subprocess (`sys.executable -I -X importtime -m coding_agent_playbook.hook_runtime dispatch <event> …` with a canned payload and config), per hot-path branch — `pre_tool_use` for an Edit of a `.py` file and for a plain Bash command, and the python-edit branch of `post_tool_use` — assert that no forbidden module appears in the `importtime` stderr, and that `sys.modules` after dispatch contains no `jinja2`, `yaml`, `importlib.metadata`, `tomllib`, `packaging`, `argparse` or `coding_agent_playbook.{cli,renderer,orchestrator,adapters,sources,commands,evaluators,evals,detector}`. Each branch-local row of §D.1 gets its own case asserting that its module is imported **only** when its trigger holds. P-D1 is the precondition. A second assertion: zero `proc.run` calls on the `pre_tool_use` hot path for an Edit and for a non-git Bash command.

**Latency budget tests** (`test_latency_budget.py`) are **gated**: they run only with `PLAYBOOK_LATENCY_TESTS=1` (skipped otherwise, mirroring `PLAYBOOK_E2E_CLAUDE`), because wall-clock p95 over spawned interpreters is neither fast nor repeatable on shared runners. The default run keeps a single N = 3 smoke per path with a generous bound (10× the budget). Gated runs assert the **excess over bare interpreter start**: `p95(dispatch) − p95(python -I -c pass)` over N = 25 runs in a tmp git repo with the default pack's config:

| Path | Excess allowed in CI |
| --- | --- |
| `pre_tool_use` (Edit and Bash) | ≤ 60 ms (the 100 ms contract minus the interpreter floor) |
| `session_start` | ≤ 260 ms |
| `stop`, default stages with stubbed ruff and a one-file metrics run | ≤ 2.9 s |

The absolute contracts (p95 ≤ 100 ms / ≤ 300 ms / ≤ 3 s) are measured on the user's machine by `doctor`.

**`playbook-hook simulate`.** It runs the **identical** `run_event` pipeline:
- the environment is `os.environ` plus the `--env` overrides, so kill switches can be tested; for `--harness claude_code` it sets `CLAUDE_PROJECT_DIR` to `--repo` (default: the cwd) unless overridden, so the §D.2.2 foreign check does not make every simulation inert;
- state goes to an ephemeral tmp dir unless `--state` is given (the real decision log is never touched by default);
- `--unattended` forces ask degradation;
- `--format json` prints `{"exit_code", "stdout", "stderr", "decisions": [{hook_id, rule_id, decision, effective, degraded, latency_ms}], "combined", "latency_ms"}`.

The exit code is 0 for any completed simulation, whatever the decision, and 2 on usage errors.

**`playbook-hook doctor`** is human-run and read-only (it never syncs).
- **Registrations.**
  - It reads the managed hook entries of `.claude/settings.json`, identified via lockfile ownership (§C/L4), and the OpenCode plugin's embedded registration table (§C).
  - It executes **only** entries whose bytes match what sync rendered, because executing an agent-edited command string would itself be repo-controlled code.
  - It runs each **exact registered command string** the way the harness would: shell form via `sh -c` with `CLAUDE_PROJECT_DIR` set, or exec form with `args`. It feeds synthetic canary payloads: a benign `ls` → none; `rm -rf /` → exit 2 deny; an Edit of a protected file → deny; `session_start` → `PLAYBOOK-GUARDS: OK <n>`.
  - It measures each call's latency against the budgets.
- **Environment checks:**
  - the interpreter is ≥ 3.12 and `sys.flags.isolated` is set;
  - the `guard_config.json` sha256 matches its lockfile entry, and the registrations match their scoped lock entries;
  - `claude --version` ≥ 2.1.295 wherever a registration carries `onFailure` (QC-11); `opencode --version` ≥ 1.18.29 when `opencode` is on PATH (QC-14); a warning when `copilot` is on PATH (Windows deny-all risk, §C.5.2);
  - the state root is mode 0700 and owned by the user;
  - `machine.json` tool signatures match;
  - the trust-store status;
  - when `PLAYBOOK_HOOK_WRAPPER_PREFIXES` is set, a `wrappers` row: `ok` with the prefixes the dispatcher will strip, or a `warning` naming each refused entry and the command it would hide, or a value a settings-file `env` sets (ignored).
- **Decision-log summary** over `--since` days (default 30): per hook, deny/ask/override/degraded counts and the override rate. This is the evidence needed before promoting an opt-in hook or flipping an ask to a deny (§E.0.2).
- **Hygiene.** Canary runs use the session id `playbook-doctor-<pid>`, are logged `canary: true`, and their session dir is removed afterwards.
- **Exit codes:** 0 healthy, 1 degraded, 2 broken.

**CI smoke step** (with `.github/workflows/ci.yml`, ubuntu, 3.12/3.13; K2 adds the `--version` step and K8 the `simulate` step, §H): add `playbook-hook --version` and `playbook-hook simulate pre_tool_use --format json < tests/fixtures/hook_payloads/claude_code/pre_tool_use/bash_rm_root.json`, asserting `"exit_code": 2` (simulate reports the **harness-facing** wire exit code; the `dispatch` process itself would exit 10).

### §D.10 Locked decisions (§D)

1. **D-1.** Harness registrations run `"<pin>" -I -m coding_agent_playbook.hook_runtime …`. The `playbook-hook` console script is the human entry. Both reach `cli.main`.
2. **D-2.** On Claude, exit 0 + JSON everywhere, except a PreToolUse deny, which is **harness exit 2 + deny JSON + stderr reason**; the dispatch process signals it as `DENY_EXIT = 10` and the launcher/shim map it, so a raw 2 is never a deny. Stop and SubagentStop never use exit 2.
3. **D-3.** On Stop, context-only results render as `systemMessage`, never `additionalContext`, because the latter continues the turn.
4. **D-4.** Ask degrades when unattended (`PLAYBOOK_HOOK_UNATTENDED`, `CI`, OpenCode, `dontAsk`), defined once in `policy.is_unattended`: to deny by default, to context + user note under `[hooks] unattended_ask = "warn"`.
5. **D-5.** Guard internal error → ask (deny unattended). Quality → fail open with one note per session. `on_error: deny` is overlay-only. A `ConfigFault` asks once per session, never per call.
6. **D-6.** The hot path reads JSON only, and imports no jinja2, yaml, tomllib, `importlib.metadata` or non-runtime engine package (P-D1 is a prerequisite). It spawns no subprocess for non-git, non-pragma calls.
7. **D-7.** Every git call goes through `SafeGit`: filter drivers neutralized, `core.fsmonitor=false`, `--no-ext-diff --no-textconv`, a scrubbed `GIT_*` env, and bounded timeouts.
8. **D-8.** The fingerprint is a temp-index tree id, with secret-glob and over-cap paths excluded and folded in by stat. A `stat`-mode fallback exists.
9. **D-9.** State lives under `<git_dir>/playbook-hooks`, resolved without a subprocess: 0700 dirs, 0600 files, locked read-modify-write, a TTL sweep at session start.
10. **D-10.** The decision log records decisions only: no command, path, prompt, reason or env text.
11. **D-11.** Escape hatches come only from the hook process env, with exact values. Pragmas are honored only if present at HEAD.
12. **D-12.** Entry-point handlers are resolved at sync and never scanned at run time. Per §B.4: entry-point handlers run only when their package is in `allow_code_from`; external handlers additionally need a trust-store approval of (launcher, script sha256, args sha256).
13. **D-13.** Per-machine paths and stat signatures live in `machine.json` (state) and the `interpreter` pin, never in the committed `guard_config.json`, which carries only machine-independent data.
14. **D-14.** One `dispatch` argv (`dispatch <event> --harness H [--project-dir DIR]`); the config path is fixed and the digest comes from the lockfile.

### §D.11 Prerequisites surfaced by §D (add to the prerequisite track)

- **P-D1.** `coding_agent_playbook/__init__.py`: a lazy `__version__` in the exact shape of §D.1 (`TYPE_CHECKING` annotation + PEP 562 `__getattr__` caching in `globals()`; avoids ruff F822 on `__all__`). Measured: `importlib.metadata` costs 69–190 ms of a 106–249 ms package import.
- **P-D2.** `evals/claude_code_runner.py:107` and `evals/opencode_runner.py:108` pass `env={**os.environ, "PLAYBOOK_HOOK_UNATTENDED": "1"}`, so eval runs degrade ask to deny deterministically.
- **P-D3.** Owned by §F.0.3 (items 1 and 7): `evaluators/metrics_gate.py::run_metrics_gate` extracted from `commands/metrics.py:574` `run()`, plus the git timeouts. Listed here only as a §D dependency.
- **P-D4.** `security/audit.py::append_jsonl` / `append_decision` (§D.6.2), also used for the SPEC §17.4 sync audit line. The secret globs are P7's (`security/patterns.py`); this item does not duplicate that wiring.
- **P-D5.** `pyproject.toml`: the empty table `[project.entry-points."coding_agent_playbook.hook_handlers"]` (like metrics/checks/gates); `tests/unit/test_entry_points.py::_GROUPS` gains `"coding_agent_playbook.hook_handlers"`. That is all Track P lands (§H, "P-D5 is split"): the `[project.scripts] playbook-hook` line (`:44–46`) and the `playbook-hook --version` CI smoke step land with K2, and the `playbook-hook simulate` CI smoke step (§D.9) with K8, so no installed script ever points at a missing module.

### §D.12 Open questions (§D)

- **Q-D1. `ask` under `bypassPermissions` and `auto`.** It is unverified whether Claude Code shows a hook-requested ask prompt in `bypassPermissions` mode; verified: deny is honored there, and an ask floors at a prompt in `auto` for **unsandboxed Bash** (2.1.211). Verify against the real CLI before GA: `bypassPermissions`, and `auto` for file tools, MCP tools and sandboxed Bash. Proposed: treat them as attended; if an ask is dropped, render deny.
- **Q-D2. `onFailure: "block"` strict mode.** *Merged into QC-11 (§C.8), the single entry.*
- **Q-D3. Stop warn channel.** Under D-3, warn-only stage lines reach the user, but the agent sees them only alongside a block. The alternative, `additionalContext`, continues the turn on every warning and counts toward Claude's cap of 8. Confirm D-3. §E.0.3 says "one line in the combined Stop reason", which matches when a block exists.
- **Q-D4. Object-store side effect.** `git add -A` into a temp index writes loose blobs, which `gc` prunes. Accept this (proposed), or default to `stat` mode? `stat` mode loses the content-addressed key that git-commit-push-policy-guard consults.
- **Q-D5. Sibling worktrees.** With cwd in a sibling linked worktree, paths classify against their own worktree root (`same_repo=True`), and the `guard_config` of the registering repo applies. Confirm that a sibling worktree's own `guard_config` is never consulted. That is the proposal, because registrations come from `CLAUDE_PROJECT_DIR`'s settings.
- **Q-D6. Windows support level.** CI is ubuntu-only (`ci.yml`). `msvcrt` locking, `%LOCALAPPDATA%` state and PowerShell regex rows are specified but untested. Is v1 Windows support "best effort, documented"?
- **Q-D7. Fixture directory.** *Resolved* (§D.9): `tests/fixtures/hook_payloads/`, served by the root `hook_payload` fixture.
- **Q-D8. `stop_gate` argv and signatures.** *Resolved* (§D.8.3 invariant): machine-specific data lives only in `machine.json`; §E.0.5 and §F.1.2 follow it.
- **Q-D9. Snapshot claim.** *Resolved*: §E.1 now uses the hot-reload rationale.
- **Q-D10. Absolute latency on slow machines.** `python -I -c pass` alone measured 40–110 ms here under load. CI asserts the excess over the interpreter floor; is the absolute p95 ≤ 100 ms a hard contract (reported by `doctor`) or a target?

---

## §G — Locked decisions

The user's locks L1–L9 (selection) and addenda D-Q1–D-Q3 are final as resolved below. The spec-level locks K-1…K-16 each have one owning section; the other sections reference it. A proposed change to a user lock is an open question (§K), never a silent divergence. Two are open today: OQ-19 (one async audit registration, amends L3) and OQ-27 (child processes for jinja2-importing commands; consistent with L3, but a deviation from the catalog's "in-process lazy import").

### G.1 User locks, as resolved

| Lock | Final resolution | Specified in | Still open |
| --- | --- | --- | --- |
| **L1** canonical artifact | 4th emitted kind `Hook` (`Hook`, `HookFrontmatter`, `HookMatcher`, `HookHandler`, `HookSchemaError` in `types.py`), authored only as a directory `<id>/HOOK.md` or `HOOK.md.j2` (+ optional `scripts/`), found at any depth under `resources/hooks/` (engine, overlays) and `playbook/hooks/` (repo-local). Static YAML frontmatter binds `events`, per-event `matcher`, `handler` or per-event `handlers`, `decisions`, `timeout`, `on_error` (clamped per firing event), `applies_if`, `linked_rule`, `supports`, `tier`/`enabled`/`mandatory`/`priority`. Handlers are builtin (`@register_hook_handler` + the `coding_agent_playbook.hook_handlers` group) or external (`python`\|`bash`\|`sh`\|`node` launcher + a contained script + static args); external handlers come only from overlay or repo-local sources and run only behind `allow_code_from` + a user-local TOFU approval. The body degrades to one advisory `Rule` (`guardrail-<id>`, priority 30, `Rule \| None`) routed to AGENTS.md and Continue, and to CLAUDE.md only where Claude Code does not enforce the hook; every advisory says where it is enforced. | §A.1–§A.8, §B.4, §C.4 | OQ-9, OQ-17 |
| **L2** overlay merge | Merge by id engine → overlays (`overlays_enabled` order) → repo-local, through `OverlayResolver.resolve_hooks` + `hook_policy.merge_hook_layers` (not `_resolve`, which keeps only the winner). Overlays may only add: no handler swap, no dropped event, tool class, `deny` or `ask`, no weaker `on_error`, no tier demotion. `handler.config` keys merge as `extend` / `strictest` / `relax` / `replace`; the consumer's `[hooks.<hook-id>]` is the last layer. Overlay-only `mandatory` hooks cannot be disabled or shadowed (H15). Overlays are data-only by default. Engine overlay-tier mechanisms are activated only by an overlay promoting them to `tier: default` (K-11). | §A.6, §B.1, §B.5 (H12, H14, H15), §E.5 | OQ-8 |
| **L3** one dispatcher | One import-light dispatcher: console script `playbook-hook` (`dispatch` \| `simulate` \| `doctor`), module `coding_agent_playbook.hook_runtime`. Harnesses launch it as `<pin> -I -m coding_agent_playbook.hook_runtime dispatch <event> --harness H [--project-dir DIR]`. It never imports `cli.py`, jinja2, yaml, `importlib.metadata`, or `tomllib` outside §D.1's branch-local rows (test-enforced, after P-D1); work that needs jinja2 runs as a child process. One registration per harness event with in-process fan-out; `SessionStart` is registered whenever any registration exists (bootstrap plus the visible inactive notice). One Stop coordinator: stop-ci-parity-gate owns the policy, and every other Stop hook is a stage run in `STOP_STAGE_ORDER`. One accepted amendment (OQ-19): at most one extra `async`, non-deciding, output-free `PostToolUse` registration for `ASYNC_SAFE` handlers (local-audit-log). | §D.1, §D.5, §C.2.1, §E.0.4 | OQ-19, OQ-27 |
| **L4** Claude Code rendering | Managed merge into the `hooks` key of the committed `.claude/settings.json` (`adapters/claude_settings.py`): a strict JSON parse (no comments, duplicate keys or NaN), a plan on the parsed document, splices of managed spans only, a no-op short circuit, a self-check and a race re-read. Ownership is one lockfile v2 entry per managed element (`scope = json:/hooks/<Event>`, sha256 of the canonical JSON), never markers. User keys and user hook groups stay byte-stable; a hand-edited managed group is restored with a warning; a mixed group is an error; `sync --check` drifts only on the managed projection. **Interpreter path, design D (locked):** the committed, machine-independent launcher `.claude/hooks/playbook/launch.sh` (sentinel on line 1, no shebang, run as `sh launch.sh`, repo root derived from `$0`) reads the per-worktree pin `<git_dir>/playbook-hooks/interpreter` and runs `<pin> -I -m coding_agent_playbook.hook_runtime "$@"`. Write-mode `playbook sync`/`init` writes the pin from `sys.executable`, unresolved, first writer wins; `playbook-hook doctor --repin` rewrites it; it is never committed and never enters the lockfile. Tool pins live beside it in `machine.json`. The registration command is `sh "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null \|\| echo .)}/.claude/hooks/playbook/launch.sh" [--strict-launch] dispatch <event> --harness claude_code`. Rejected: an absolute interpreter in `settings.json` (drift on every other machine and in CI, `$HOME` paths committed), `settings.local.json` (no hooks on a fresh clone, one file shared by every worktree, rewritten by Claude Code), bare `playbook-hook` on `PATH` (silent fail-open in IDE launches, PATH hijack, no `-I`). Rationale: committed bytes are identical on every machine and in CI, and a fresh clone stays inert until someone syncs in that worktree, which is explicit and reported. `settings.local.json` is never written; `permissions.allow` remediation entries are opt-in. | §C.2, §D.0, §D.8.3 | OQ-14, OQ-15, OQ-16, OQ-18 |
| **L5** OpenCode rendering | **API target: OpenCode V1** (`opencode-ai` plugin API; floor **≥ 1.18.29**, where the `{id, server}` default-object export is documented; verified against 1.19.0). Exactly one generated file, `.opencode/plugins/playbook-hooks.js`: auto-discovered (so `opencode.json(c)` is never touched), plain `.js`, `node:` imports only, sentinel `// …` on line 1, one default export `{id: "playbook.hooks", server, setup}`. `server` is the V1 plugin. `setup()` is an inert stub, so OpenCode V2 (2.0.x, a separately installed pre-default channel whose docs state that V1 plugins do not run there) loads the file and logs that hooks are inactive. The shim spawns the pin asynchronously (`spawn`, argv list, its own timeout) with `dispatch <event> --harness opencode --project-dir ROOT` and a Claude-shaped payload (native args kept, plus the V1 snake_case alias table after PR #52765). It parses `playbook.hook.wire/1`, throws in `tool.execute.before` on exit 10, appends context in `tool.execute.after`, injects session context and notices through `experimental.chat.system.transform`, and fails open on spawn errors, timeouts and any other exit. Rendered events: `pre_tool_use`, `post_tool_use`, `session_start` (degraded: experimental API), `stop` (evidence-only through `session.idle` and the `carry` map). Not rendered: `user_prompt_submit`, `post_tool_use_failure`, `subagent_stop`, `session_end`, `pre_compact`. `ask` degrades to deny, because OpenCode has no ask primitive. | §C.3, §D.3.5, §D.5.6 | OQ-11, OQ-12, OQ-13, OQ-20, OQ-29 |
| **L6** trust contract | `playbook validate` enforces H1–H21 (`hook_policy.classify_hook` + `_check_hooks`). Decisions ⊆ `deny \| ask \| context \| none`, declared per hook and valid per event; never `allow`, `updatedInput`, or HTTP, async, prompt or agent handler types. Every hook declares `events`, `decisions`, `timeout` (≤ 30 s on tool and prompt events), `on_error` (`deny` is overlay-only) and `supports` (reachable through `Adapter.hook_support`). Runtime backstops: the closed-key renderers (§D.3.5) and the declared-decision check (`contract_violation`). One extension (§E.3): the builtin-only `mutates_edited_file` capability for post-edit-ruff-format. External handlers can never write. | §B.5, §D.3 | OQ-43 |
| **L7** prerequisites first | Track P lands first. P1: `SandboxedEnvironment` (`renderer.py:78`, plus `commands/validate.py:137`). P2: orphan-aware `sync --check` (`commands/sync.py:246`), a hygienic scratch copy and injected facts. P3: the code string `renderer.SENTINEL` is canonical, `_sentinel.py` is import-light, and SPEC §4.3 and CLAUDE.md quote it. P4: lockfile v2 (`kind`, `artifact_id`, `source`, `adapter`, `scope`, `executable`) with one `SyncResult`. P5: the SPEC §3 / §10.2 / §17.1 Continue correction. This spec adds P6–P9 and P-D1–P-D5 (§D.11) to the same track. | §P, §D.11 | OQ-4 |
| **L8** invariants | All honored; enumerated in §I. | §I | OQ-5 |
| **L9** commit naming | **Superseded by D-Q2/D-Q3.** The configurable convention is commitizen's own: `[tool.commitizen]` in the consumer's `pyproject.toml`, default `cz_conventional_commits`, with `cz_customize` / `schema_pattern` for a scoped or custom-regex convention. It is checked by `cz check` from the consumer toolchain. The engine adds only the committer-date `[hooks.commit_convention] cutover_date` filter for range checks. | §F.4, §B.1 | OQ-44, OQ-6 |
| **D-Q1** reuse tools | Quality: ruff C901, PLR0911, PLR0912, PLR0913, PLR0915 in the single post-edit call (PLR1702 is preview and per-invocation opt-in), the existing static metrics, NEW `ruff_violations` (subprocess, non-regression), and NEW radon-backed `file_sloc`. Docstrings: ruff D100–D107 (DOC* is preview and opt-in) and `ruff_violations` family `docstrings`. Coverage: the existing `coverage` metric plus NEW stdlib `diff_coverage` over `coverage_xml.py` + `git diff -U0`. Radon stays the only optional extra; no stdlib `function_length` / `nesting_depth`. | §F.0–§F.3 | OQ-38, OQ-39, OQ-42 |
| **D-Q2** commitizen | Commit names are checked by commitizen `cz check` (a subprocess pinned per worktree; fail-open plus the toolchain hint when missing). Twins: the `playbook-commit-msg` commit-msg entry and the `playbook ci` `commit-convention` step. No `playbook commit-lint`, no wrapper. | §F.4 | — |
| **D-Q3** cut-over date | `cutover_date` is a TOML string `YYYY-MM-DD` (unset ⇒ every commit is checked), filtered on **committer** date for range checks (the CI twin and the opt-in push scan, `check_push`). The `pre_tool_use` check and the commit-msg twin always check. | §F.4, §B.1 | OQ-6 |

### G.2 Spec-level locks

| # | Decision | Owner |
| --- | --- | --- |
| K-1 | One `ToolClass` vocabulary (`shell`, `edit`, `write`, `notebook_edit`, `read`, `search`, `web`, `subagent`, `mcp`; runtime-only `other`) | §A.2 |
| K-2 | Handler naming: snake_case, shareable, `<name>:<role>` companions bound through `handlers`; `on_error` clamped per firing event | §A.2 |
| K-3 | Advisory rule: `guardrail-<id>`, priority 30, scoped or always, `hook_advisory` body, `Rule \| None`; labels `enforced` / `degraded` / `advisory` / `—` | §A.8 |
| K-4 | Per-hook config in `[hooks.<hook-id>]` (the consumer layer of `handler.config`); one reserved sub-table, `[hooks.commit_convention]` | §B.1 |
| K-5 | Lockfile v2 with per-element scoped entries; one `_build_lockfile` signature; `SyncResult` | §B.6, P4, §C.1.4 |
| K-6 | `guard_config.json` at `.coding-agent-playbook/hooks/`, sync-level and machine-independent; absolute paths only in `machine.json` and the `interpreter` pin | §C.0, §D.8.3 |
| K-7 | One `dispatch` argv; dispatch exits 0 or `DENY_EXIT = 10`; the launcher and the shim map 10 to a deny; a raw 2 is never a deny | §D.1, §C.2.7 |
| K-8 | One timeout formula: `deadline_ms` derived per event; registration = deadline + 2 s | §D.4 |
| K-9 | OpenCode `playbook.hook.wire/1`; Stop results returned on stdout and carried by the shim; notices on every dispatch | §D.3.5, §C.3 |
| K-10 | Stop order = `STOP_STAGE_ORDER`; `priority` orders fan-out only | §D.5.2, §E.0.4 |
| K-11 | Overlay-tier mechanisms are activated only by an overlay promoting them to `tier: default` | §A.6, §E.5 |
| K-12 | Hooks are git-only in v1 | §C.2.7, §D.6.1 |
| K-13 | Escape hatches (and `PLAYBOOK_HOOK_WRAPPER_PREFIXES`) come from the hook process env only; hatches defined in settings `env` objects are ignored and reported | §B.2, §D.7 |
| K-14 | The trust store holds approvals only; the interpreter pin is not a trust approval | §B.4 |
| K-15 | Launcher design D (committed launcher + per-worktree pin) | §C.2.7 |
| K-16 | Runtime decisions D-1…D-14 | §D.10 |

## §H — Tracks

Each track is one subagent unit in the house style of `specs/prH-agent-harness.md`. It lands under the header's CI-parity gate, and its tests are hermetic: `FakeProc` (autouse, through `RuntimeDeps`), `FakeGit`, `FakeRuff`, `FakeCz`, `FakeStageRunner`, `FakeProjectHandle`, golden payloads, and never a real `claude`, `opencode`, `cz` or project `pytest` subprocess in CI. Real-harness tests are env-gated (`PLAYBOOK_E2E_CLAUDE=1`, `PLAYBOOK_E2E_OPENCODE=1`) and wall-clock tests are gated (`PLAYBOOK_LATENCY_TESTS=1`), all `# pragma: no cover` where they call out.

Phases: **P (Pa → Pb) → K1 → K2 → {K3 ∥ K4} → K5 → K6 → K7 → K8 → K9 → K10 → K11.** Track P lands as two PRs, Pa then Pb (Track P below); a K-track that needs a Pb item names it in "Depends on". K4 can run beside K3 once K3's ABC change (§C.1.1) has merged, and K5/K7 overlap in practice; the "Depends on" column is the hard ordering. The numbers below are production lines (Python, JS, shell and shipped markdown), tests excluded; tests add roughly as much again.

| Track | What | Depends on | ~LoC | Key files |
| --- | --- | --- | --- | --- |
| **P** | Prerequisites: P1–P9, P-D1–P-D5, landed as two PRs. **Pa** (this first PR): P1, P2, P3, P4, P5, P7 — P7 rides along because P2's hygienic scratch copy uses `SECRET_PATH_GLOBS`. **Pb** (follow-up): P6, P8, P9, P-D1–P-D5 | — (Pb after Pa) | ~1,000 | `renderer.py`, `commands/{sync,validate,init,check,metrics}.py`, `lockfile.py`, `_sentinel.py`, `config.py`, `_toml.py`, `security/{patterns,paths,audit}.py`, `evaluators/metrics_gate.py`, `pyproject.toml` |
| **K1** | Canonical `Hook` kind, sources, overlay merge, `[hooks]`/`[guardrails]`, trust store, validate H1–H21 | Pa, Pb (P6, P8) | ~1,100 | `types.py`, `sources/{base,filesystem}.py`, `orchestrator.py`, `hook_policy.py`, `config.py`, `security/trust.py`, `commands/validate.py` |
| **K2** | `hook_runtime` core: dispatcher, normalization, decisions, failure policy, state, pins, stage contract, `simulate`/`doctor` | Pa, Pb (P-D1, P-D4, P-D5), K1 | ~3,000 | `hook_runtime/**` (minus `handlers/*`, `stop/{coordinator,output}.py`), `pyproject.toml` |
| **K3** | Adapter contract, sync dispatch, `guard_config.json`, Claude Code managed merge + launcher, advisory degrade, agent_harness round trip | K1, K2 | ~1,700 | `adapters/{base,claude_code_adapter,claude_settings,agents_md_adapter,agent_harness_adapter}.py`, `hook_registrations.py`, `guard_config.py`, `commands/{sync,check,render,init,import_harness}.py`, `harness/manifest.py`, `resources/hook_shims/claude-launch.sh` |
| **K4** | OpenCode V1 shim | K2, K3 | ~350 | `adapters/opencode_adapter.py`, `hook_registrations.py`, `resources/hook_shims/opencode-plugin.js` |
| **K5** | Pack: protect (§E.1, 8 hooks) | K2, K3 | ~1,600 | `resources/hooks/protect/**`, `hook_runtime/protected.py`, `hook_runtime/handlers/*`, `lockfile.py` (`drift_entries`) |
| **K6** | Pack: verify (§E.2, 7 hooks) + Stop coordinator + `playbook ci` | Pa, Pb (P-D3, P9), K2, K3, K5 | ~2,200 | `hook_runtime/stop/{coordinator,output}.py`, `resources/hooks/verify/**`, `gate_scan.py`, `commands/ci.py` |
| **K7** | Pack: feedback (§E.3, 8 hooks) + the shared ruff call | Pb (P9), K2, K3 | ~1,550 | `hook_runtime/_ruff.py`, `hook_runtime/handlers/{ruff_feedback,deser,prompt_scope,toolchain,notebooks}.py`, `types.py`, `renderer.py`, rule/prompt resources |
| **K8** | Pack: secrets & risky actions (§E.4, 9 hooks) + native deny twins | K2, K3, K6, K7 | ~2,500 | `security/{paths,secrets,patterns}.py`, `hook_runtime/{_hosts,gitargv}.py`, `hook_runtime/handlers/*`, `_pep503.py`, `detector.py` |
| **K9** | Pack: audit + overlay mechanisms (§E.5, 6 hooks) | Pb (P-D4), K2, K3, K8 | ~1,250 | `security/{audit,pii}.py`, `hook_runtime/handlers/{compaction,network,sensitive_reads}.py`, `hook_registrations.py` |
| **K10** | New tools: coverage, quality metrics, docstrings, commit names (§F, 3 tool hooks) | Pa, Pb (P6, P-D3), K2, K6, K7, K8 | ~2,100 | `evaluators/{policy,types,metric}.py`, `evaluators/builtins/{ruff_violations,file_sloc}.py`, `evaluators/execution/{diff_coverage,git_diff}.py`, `hook_runtime/handlers/{coverage_diff_gate,docstring_nonregression,commit_convention}.py` |
| **K11** | Docs and rollout | all | prose | `SPEC.md`, `README.md`, `MIGRATION.md`, `CLAUDE.md`, `tests/unit/test_docs_check_rubric_refactor.py` |

**Track-level placement decisions** (they follow from the section contracts; none changes a design):

- **P-D3 (= §F.0.3 items 1 and 7) is in Track P (Pb)**, as §D.11 lists it. The `run_metrics_gate` extraction and the git timeouts are behavior-preserving CLI hardening, and K6's `quality-metrics` stage needs them before K10 exists.
- **P-D5 is split.** Track P (Pb) declares the empty `coding_agent_playbook.hook_handlers` entry-point table (and the `_GROUPS` test row). The `[project.scripts] playbook-hook` line and its `--version` CI smoke step land with K2, so no installed script ever points at a missing module; the `simulate` CI smoke step (§D.9) lands with K8.
- **P8(c) (`tolerate_hook_errors`) lands in K1**, because it needs `list_hooks`.
- **The Stop stage contract is runtime core (K2)**: `hook_runtime/stop/stages.py` with `STOP_STAGE_ORDER`, `StageCost`, `StageResult`, `Stage` and `StopPlan`. The coordinator policy (`stop/coordinator.py`, `stop/output.py`) is K6. This lets K5's `drift` stage be built and unit-tested before the coordinator.
- **`guard_config.json` has one sync-level renderer**, `src/coding_agent_playbook/guard_config.py` *(NEW; shared name — proposed)*: `render_guard_config(...) -> dict` and the script copies of §C.0. It keeps `commands/sync.py` under the 500-line budget. K3 creates it with the envelope, `hooks`, `deadlines_ms`, `unattended_ask`, `logging`, `shell`, `path_classes` and `secret_path_globs`; each pack track adds its own §E.0.5 tables.
- **`playbook ci` (§F.5) lands in K6**, its first consumer (block-precommit-bypass's mandatory twin), with the steps `sync-check`, `validate` and `gate-scan`. K8 appends `scan-secrets`, `check-deps`, `commit-trailers` (and the opt-in `scan-sinks` row for K7's tool); K10 appends `metrics`, `coverage` and `commit-convention`. `CI_STEPS` stays the single table.
- **The post-edit companions** `clean_code_metrics_nonregression:post_edit` and `docstring_nonregression:post_edit` land in K10. They are buckets in K7's D1 call, and their thresholds come from K10's `[metrics.ruff_violations] config`.

Integration: merge the tracks in dependency order, run the full cache-free CI-parity gate with no optional extras, then hold for the user gate. No `git push` and no `gh pr create` before the user approves the diff.

The Track P, K1–K4 and K11 subsections follow. The pack and tool tracks K5–K10 are specified in [part 2, §H (pack tracks)](prK-hook-pack.md#h-pack-tracks); the table above remains their single source for dependencies, sizes and key files.

### Track P — Prerequisites

- **What.** P1–P9 (§P) and P-D1–P-D5 (§D.11), each independently mergeable, with no hook shipped. Order inside the track: P3 → P4 → P2 (the lockfile-orphan half needs P4's provenance); P7 → P2(b) (the scratch-copy ignore globs).
- **Landed as two PRs.** **Pa** (this first PR): P1, P2, P3, P4, P5, P7 — P7 rides along because P2's hygienic scratch copy uses `SECRET_PATH_GLOBS`. **Pb** (follow-up): P6, P8, P9, P-D1–P-D5. Both orderings above fall inside Pa. The Files, Tests and Done-when lists below cover both PRs; each item's files and tests land with the PR that carries the item.
- **Files.**
  - **Modified:** `src/coding_agent_playbook/renderer.py` (P1 `:78`; P3 re-export), `commands/validate.py` (P1 `:137`; P8 `collect_validation_errors`, config-less context at `:377`), `commands/sync.py` (P2 `_run_check` `:219-276` and `:239`; P4 `SyncResult`, `_build_lockfile` `:93-118`, `_LOCKFILE_SCHEMA` `:35`; P8 validate gate in `execute` `:194-211`), `lockfile.py` (P4 fields + `Provenance`), `orchestrator.py` (P2 `from_repo(..., facts=)`), `adapters/{base,claude_code_adapter,opencode_adapter,agents_md_adapter}.py` (P3 `has_sentinel` in the cleanup scanners), `config.py` (P6 `extra_tables`), `_toml.py` (P6 float and date branches), `sources/filesystem.py` (P6 `load_primary_config`, inline tables in `_dump_toml`), `commands/{init,check}.py` (P6 primary-only save), `detector.py` (P7), `__init__.py` (P-D1), `evals/{claude_code_runner,opencode_runner}.py` (P-D2), `commands/metrics.py` (P-D3: thin CLI over the extracted gate, plus git timeouts), `pyproject.toml` (P9 `extend-exclude` + `force-exclude`; P-D5 empty `coding_agent_playbook.hook_handlers` table), `SPEC.md` (P3 §4.3 and the four examples, P4 §14.4, P5 §3/§10.2/§17.1 — doc fixes ride with their code fix, no version bump), CLAUDE.md:73 (P3; local edit only, never committed — harness-files policy, OQ-5).
  - **New:** `src/coding_agent_playbook/_sentinel.py`, `security/__init__.py`, `security/patterns.py` (P7), `security/paths.py` (`is_secret_path` only; `PathPolicy` lands in K8), `security/audit.py` (P-D4 `append_jsonl`, `append_decision`), `evaluators/metrics_gate.py` (P-D3).
- **Tests.** As listed per item: `tests/unit/test_renderer.py`, `tests/unit/test_sentinel.py` (NEW), `tests/unit/test_docs_sentinel.py` (NEW), `tests/adapters/test_cleanup.py` (NEW), `tests/unit/test_lockfile.py`, `tests/cli/test_sync.py`, `tests/unit/test_config.py`, `tests/unit/test_toml.py`, `tests/unit/test_sources_filesystem.py`, `tests/cli/test_init.py`, `tests/cli/test_check.py`, `tests/security/test_patterns.py` and `tests/security/test_audit.py` (NEW dir), `tests/unit/test_detector.py`, `tests/cli/test_validate.py`, `tests/integration/test_ruff_scope.py` (NEW), `tests/unit/test_package_init.py` (NEW), `tests/unit/test_entry_points.py` (`_GROUPS` gains `coding_agent_playbook.hook_handlers`), `tests/evaluators/test_{claude_code,opencode}_runner.py` (child env carries `PLAYBOOK_HOOK_UNATTENDED=1`), `tests/cli/test_metrics.py` (JSON and text byte-identical after the extraction).
- **Done when.** Every shipped `.md.j2` renders byte-identically under the sandbox (adapter goldens unchanged); `sync --check` exits 1 on an orphan; a v1 lockfile loads and the first sync writes v2; `import coding_agent_playbook` leaves `importlib.metadata` unloaded; `playbook metrics` output is byte-identical; `init` re-runs keep `[metrics]` floats; the gate is green cache-free without radon.

### Track K1 — Canonical Hook artifact, sources, overlay merge, config, validate

- **What.** The `Hook` kind up to resolution and validation, with no rendering: dataclasses and the markdown round trip (§A.3, §A.4), discovery (§A.5), `resolve_hooks` + `merge_hook_layers` with the additive key policies (§A.6), `resolve_effective_hooks` + `ResolvedHook.to_json()` as the single `guard_config.json` hook record (§A.7), `[hooks]`/`[guardrails]` parsing with the `.local.toml` exclusion (§B.1, §B.3), `TrustStore` (§B.4), and H1–H21 (§B.5). The registry half of H6 and the `CONFIG_SCHEMA` half of H21 close in K2. P8(c) `tolerate_hook_errors` lands here.
- **Files.**
  - **Modified:** `src/coding_agent_playbook/types.py`, `_typing.py` (`:19-28`), `sources/base.py` (concrete `list_hooks` default), `sources/filesystem.py` (`_find_primary_md`, `_iter_hooks`, `list_hooks`), `orchestrator.py` (`resolve_hooks`, `Collision(kind="hook")`, `hook_violations`, `SyncContext.hooks_resolved`, `tolerate_hook_errors`, `hook_load_errors`), `config.py` (`HooksConfig`, `GuardrailsConfig`, `parse_hooks_config`, `parse_guardrails_config`), `commands/validate.py` (`_check_hooks`, `"hooks"` in `_LINK_CHECKED_SUBDIRS` `:241`, the OK count `:394`).
  - **New:** `src/coding_agent_playbook/hook_policy.py` (sync-time only: `merge_hook_layers`, `resolve_effective_hooks`, `ResolvedHook`, `SkippedHook`, `classify_hook`, `HOOK_EVENTS`, `TOOL_CLASS_NAMES`, `HOOK_SUPPORT`), `security/trust.py`.
- **Tests.** `tests/unit/test_types.py` (extend: `from_mapping` errors name field and value; `Hook.from_dict(h.to_dict()) == h`; the deep empty-value drop), `tests/unit/test_sources_filesystem.py` (extend: recursive `HOOK.md` discovery, dot-dir skip, nested-hook rejection), `tests/unit/test_sources_base.py` (default `[]`; `_DummyArtifactSource` unchanged), `tests/unit/test_orchestrator.py` (extend: every layer's definition reaches `merge_hook_layers`), `tests/unit/test_hook_policy.py` (NEW: `extend`/`strictest`/`relax`/`replace`; H14 violations; the on-formula; `linked_rule` inheritance; `to_json` field names), `tests/unit/test_config.py` (extend: `parse_hooks_config`, unknown keys, `.local.toml` exclusion), `tests/security/test_trust.py` (NEW: modes 0700/0600, `repo_key` shared across worktrees, refusal of an in-repo path), `tests/cli/test_validate.py` (extend: one case per H-rule; `::test_malformed_hook_reports_fail_line_not_traceback`).
- **Done when.** A repo-local `playbook/hooks/<id>/HOOK.md` is discovered, merged, gated and validated with field-precise messages; `playbook validate` counts hooks; `playbook sync` refuses to render while an H-rule fails; a repo without hooks syncs byte-identically.

### Track K2 — `hook_runtime` core

- **What.** The dispatcher process and its library (§D.0–§D.4, §D.6–§D.9): `python -I -m` launch, the fixed `dispatch` argv, `CanonicalEvent` and the per-harness parsers (including the §C.5.2 foreign-payload check), path normalization, shell and git-argv parsing, the decision model with `combine`, caps and the closed-key renderers, `playbook.hook.wire/1`, `DENY_EXIT = 10`, the failure policy and watchdog, ask degradation, the handler registry (static module map; entry-point handlers resolved at sync into `{"kind": "entry_point", …}`), the `guard_config.json` loader with the lockfile digest cache, `pin.py`, state, session, ledger, escape hatches and pragmas, `proc.py`, `SafeGit` + fingerprint, decision-log writes (pipeline step 8, through P-D4's writer), `canary.py`, the Stop **stage contract** (`stop/stages.py`), `simulate` and `doctor`. It closes K1's deferred H6/H21 halves (registered name, `CONFIG_SCHEMA`, declared decisions, `MUTATES_INPUT = False`).
- **Files.**
  - **New:** `src/coding_agent_playbook/hook_runtime/{__init__,__main__,cli,dispatch,deps,event,paths,shell,gitargv,decision,caps,policy,registry,config,pin,state,session,ledger,escape,proc,git,watchdog,canary,simulate,doctor}.py`, `hook_runtime/harness/{__init__,claude,opencode}.py`, `hook_runtime/stop/{__init__,stages}.py`, `hook_runtime/handlers/__init__.py`.
  - **Modified:** `pyproject.toml` (`[project.scripts] playbook-hook = "coding_agent_playbook.hook_runtime.cli:main"`), `.github/workflows/ci.yml` (`playbook-hook --version` smoke step), `hook_policy.py` (H6/H21 registry halves; sync-time entry-point resolution), `commands/validate.py`.
- **Tests.** `tests/hook_runtime/{fakes,conftest}.py` (NEW: `FakeHarness`, `FakeGit`, `FakeProc` autouse through `RuntimeDeps`, `FakeClock`, `FakeTrustStore`; the plain `real_proc` and `real_git` fixtures), `tests/fixtures/hook_payloads/{claude_code,opencode,foreign}/<event>/<case>.json` + `.expected.json` (NEW), the root `tests/conftest.py` `hook_payload` fixture, and `tests/hook_runtime/test_{cli_argv,event,shell,paths,combine,render_claude,render_opencode,failure_policy,watchdog,state,safegit,registry,import_budget}.py` (NEW), plus the gated `test_latency_budget.py`. The `ToolClass` set-equality test (`types.ToolClass` vs `event.ToolClass`) lives in `test_event.py`.
- **Done when.** `test_import_budget.py` proves no forbidden import on any hot-path branch and each branch-local row loads only on its trigger; `dispatch` never exits 2; the watchdog writes exactly one decided output; `simulate` reproduces the golden wire output for every event × harness with a stub handler; `doctor` runs against a canned config; the registry's static map equals the decorator registry.

### Track K3 — Adapter contract, Claude Code rendering, advisory degrade

- **What.** The ABC additions (§C.1.1) and the built-in overrides (§C.1.2); sync dispatch (§C.1.3: `resolve_effective_hooks`, body rendering, `begin_sync`, `write_hook`, `managed_lock_entries`, scoped lock entries, pin writes); the sync-level `guard_config.json` and copied external scripts, with the interactive TOFU approval prompt (§B.4, §C.0); `claude_settings.py` with the span-preserving merge and the generic managed-array operation (§C.2.4); `hook_registrations.py` (`plan_registrations`, `to_claude_group`, the matcher union, the timeout-formula assertion); the launcher template; the `ClaudeCodeAdapter.finalize` split; `playbook check` (Hooks block, labels, scoped drift) and the sync summary lines (§C.1.5); the advisory degrade into AGENTS.md (Guardrails section), Continue (`30-guardrail-<id>.md`) and CLAUDE.md (non-enforced hooks and the heartbeat line), with the `hook_advisory` / `hook_claude_settings` formats and `playbook render <hook-id>` (§C.4); the agent_harness emit, manifest kind `"hook"` and import (§C.6); `playbook init`'s hooks prompt and `--no-hooks` (§B.1).
- **Files.**
  - **Modified:** `adapters/base.py`, `adapters/claude_code_adapter.py` (`finalize` `:131-153` split; `.claude/hooks/playbook` in `_output_directories` `:155-159`), `adapters/agents_md_adapter.py` (`finalize` `:75-94`), `adapters/agent_harness_adapter.py`, `harness/manifest.py`, `commands/import_harness.py`, `commands/sync.py`, `commands/check.py` (`:140-155`), `commands/render.py`, `commands/init.py`, `renderer.py` (`BUILTIN_FORMATS` `:31-40`, dispatch before `:177-180`).
  - **New:** `adapters/claude_settings.py`, `hook_registrations.py`, `guard_config.py` *(shared name — proposed)*, `resources/hook_shims/claude-launch.sh`.
- **Tests.** The §C.7 list: `tests/unit/test_claude_settings.py`, `tests/unit/test_hook_registrations.py`, `tests/unit/test_lockfile.py`, `tests/adapters/test_claude_code.py`, `tests/adapters/test_claude_launcher.py` (POSIX-only), `tests/adapters/test_agents_md.py`, `tests/adapters/test_continue.py` (including P5's `::test_hooks_never_write_continue_hook_config`), `tests/adapters/test_agent_harness.py`, `tests/harness/test_manifest_roundtrip.py`, `tests/harness/test_import_roundtrip.py`, `tests/cli/test_sync.py`, `tests/cli/test_check.py`, and `tests/unit/test_guard_config.py` (NEW: `::test_render_is_machine_independent`).
- **Done when.** With `[hooks]` absent, every output is byte-identical to before; with `[hooks] enabled = true`, a second sync writes nothing; user keys and user hook groups in `settings.json` stay byte-stable; every §C.2.6 drift row behaves as tabled; the rendered launcher maps 10 → 2, a raw 2 → 0, and a missing pin → 0 (1 only under `--strict-launch`).

### Track K4 — OpenCode V1 shim

- **What.** §C.3: the rendered shim (one file, one export, `node:` imports only, line-1 sentinel), `REG` construction without a `pre_compact` key, the payload translation and alias table, the wire parse, deferred context, the `carry` and `notes` maps, spawn mechanics with the shim's own timeout, the restart notice, and the `doctor` floor check (≥ 1.18.29).
- **Files.** **Modified:** `adapters/opencode_adapter.py` (`write_hook`, a `finalize` override, `hook_support`, `.opencode/plugins` in `_output_directories` `:96-104`, deletion of the duplicate `_default_cleanup` `:106-131`), `hook_registrations.py` (`to_opencode_reg`), `hook_runtime/doctor.py` (version floor). **New:** `resources/hook_shims/opencode-plugin.js`, plus the line-for-line Python port of `parse()` kept beside the template for the wire test (§C.7).
- **Tests.** `tests/adapters/test_opencode.py` (golden shim; line-1 sentinel; exactly one export; no non-`node:` import; deterministic `REG`; stale shim removed; `node --check` when node is present), `tests/hook_runtime/test_wire_contract.py` (NEW; cross-section golden for deny, context and notice; a raw 2 is `inactive`); the env-gated end-to-end test that pins the `tool.execute.before` throw semantics (`PLAYBOOK_E2E_OPENCODE=1`, never in CI).
- **Done when.** The wire-contract golden passes under node or the port; a `guard_config.json`-only change needs no OpenCode restart, while a `REG` change prints the restart notice.

### Track K11 — Docs and rollout

- **What.** Apply every §J row, bump SPEC to `0.15 (draft)` with a `### v0.15` changelog entry; README ("Pre-commit hooks" vs "Assistant lifecycle hooks", the architecture overview updated with the dispatcher, the §C.2.9 launch-directory caveat, the §C.5.2 "do not `gemini hooks migrate` playbook entries" warning, OpenCode ≥ 1.18.29, the metrics table and the Clean Code preset, commitizen setup with `cutover_date`, `playbook ci`); CLAUDE.md (status paragraph and the §I invariants; local edit only, never committed — OQ-5); MIGRATION.md (lockfile v2; validate-gated sync; `[hooks]` opt-in through `init`; `--no-run-tests`; the `CoverageCheck` fix; new opt-in metrics; the PEP 503 `detector_cache` churn, OQ-36; the one-time heartbeat drift, OQ-30); the dogfooding change per OQ-6.
- **Files.** `SPEC.md`, `README.md`, `MIGRATION.md`, `CLAUDE.md`, `tests/unit/test_docs_check_rubric_refactor.py` (`:114-115` asserts `| Version | 0.15 (draft) |` and `### v0.15`, keeping the v0.14/v0.13/v0.12 assertions); per OQ-6, `.coding-agent-playbook.toml` and `pyproject.toml` `[tool.commitizen]`.
- **Tests.** The docs tests in the CI-parity gate; §21 amendments mention no deleted R6 symbol bare (the same test scans the §21 body).
- **Done when.** Every §J row is applied, the docs tests are green, and every open question in §K has a recorded answer or an explicit deferral.

## §I — Invariants this PR must honor

**Carried from CLAUDE.md and SPEC §4.3, now applied to hooks:**

- **Copies, not symlinks.** External-handler scripts are byte-copied (`shutil.copy2`) to `.coding-agent-playbook/hooks/scripts/<hook-id>/`, with the git-style `executable` bit in the lockfile and the sidecar; P2's scratch copy never follows a symlink out of the repo.
- **Jinja sparingly, `StrictUndefined`, sandboxed (P1).** Only `HOOK.md.j2` bodies render, with `is_prompt_context=False`. Frontmatter, handler commands, scripts, the launcher and the shim never pass through Jinja; the launcher and the shim are one-placeholder `str.replace` templates.
- **Frontmatter is static YAML,** parsed before Jinja (`HookFrontmatter.from_mapping`).
- **Sentinel on every generated file,** with the code string `renderer.SENTINEL` canonical (P3): `<!-- … -->` in markdown, `# …` on line 1 of the launcher, `// …` on line 1 of the shim, and the one documented second position (the first body line after frontmatter: agent_harness output, Claude commands with frontmatter). Files that cannot carry one are owned through the lockfile: the managed elements of `.claude/settings.json`, `guard_config.json`, byte-copied scripts, `SKILL.md`. Engine-generated files carry no shebang.
- **`AGENTS.md` is always generated,** including in a hooks-only repo; its Guardrails section exists only when hooks are on.
- **Rules cannot include other rules,** and hook bodies cannot call `rule()` (H19).
- **No HTTP-handler hooks, no telemetry, air-gapped.** No HTTP handler type (H8); guards never resolve or connect to hosts; tools are never downloaded (gitleaks is used only if already present); decision and audit logs stay local.
- **Self-contained markdown links (PR L).** `"hooks"` joins `_LINK_CHECKED_SUBDIRS` (H19).
- **Extension points through entry points** (`coding_agent_playbook.hook_handlers`; adapters, sources, runners and judges unchanged); never instantiate them directly. In-tree handlers register through a decorator plus a static module map, so the dispatcher never scans.
- **Stdlib-default core; radon is the only optional extra.** ruff, `cz`, pytest and mypy are consumer-toolchain subprocesses, never engine imports (D-Q1, D-Q2).
- **Execution is opt-in.** Execution metrics stay out of the default pre-commit hook (both metrics entries gain `--no-run-tests`), and the execution Stop stages require an enabled stage list plus a user-local trust entry.
- **Never `uv run` without `--frozen --no-sync`;** stage commands prefer per-worktree pinned paths.
- **Hermetic tests:** named fakes injected through `RuntimeDeps`; real harness CLIs, runners and judges never in CI.
- **CI-parity gate:** `ruff check .`, `ruff format --check .`, `mypy`, `pytest -q` from the repo root with no path args, cache-free and without radon.
- **Commit policy:** commits authored solely by `msobroza`; no `Co-Authored-By`, no `--author`, no signing, no `git config` edits; no push or PR before the user gate.

**New, introduced by this PR:**

- **Hook outputs are only `deny | ask | context | none`** (L6, H5, H8, the §D.3.5 closed-key allowlist); only builtins may hold `mutates_edited_file`.
- **One registration per harness event** (L3), plus at most the one async, non-deciding audit registration (OQ-19).
- **The hot path imports nothing outside `hook_runtime.*`, `security.*` and the stdlib,** branch-local imports are exactly §D.1's rows, and no subprocess runs for a non-git, non-pragma call.
- **Exit codes:** the launcher exits 0 or 2 (1 only under `--strict-launch`); `dispatch` exits 0 or 10; a raw 2 is never a deny; the shim throws only on exit 10 or a `deny` decision.
- **Committed outputs are machine-independent:** no absolute path, stat signature or `$HOME` path in any committed file (§D.8.3); pins live under the git dir.
- **Engine upgrades never inject executable hooks:** an absent `[hooks]` table (or one without `enabled = true`) means zero byte change.
- **`.local.toml` never carries policy:** `[hooks]`, `[guardrails]`, `[metrics]` and `[hooks.commit_convention]` from it are ignored.
- **No repo- or overlay-controlled code runs without a user-local trust entry;** the interpreter pin is not trust (K-14).
- **Escape hatches come only from the hook process env** with exact values; hatches set through settings-file `env` objects are ignored and reported; pragmas count only when present at HEAD.
- **Every git call goes through `SafeGit`** (filter drivers neutralized, `core.fsmonitor=false`, no ext-diff or textconv, scrubbed env, bounded timeouts).
- **The decision log stores no content:** no command text, paths, prompts, reasons or env values.
- **A stage never reports green on an error, and red is never presented as green;** one combined Stop reason per fingerprint, at most `max_blocks` blocks per stop chain.
- **Every speed bump has an off-workstation twin,** and every guard is labelled honestly as a boundary, a speed bump or detective.
- **User-owned settings are never modified:** user keys, user hook groups and user permission entries are untouched; `settings.local.json` is never written; managed elements are identified only by lockfile hash.
- **Overlays only add;** mandatory overlay hooks cannot be disabled by `[hooks] disable` or a repo-local override.
- **Tool policy has one source** shared by the hook and its twins: `[metrics]`, `[tool.commitizen]`, `[hooks.commit_convention]`.
- **Hooks are git-only in v1.**

## §J — SPEC amendment table

K11 applies every row; rows marked P ride with their Track P code fix.

| SPEC section | Change | Source |
| --- | --- | --- |
| Changelog (the "§0" entries) | v0.15 entry; header `0.15 (draft)`, with the docs-test update | header, K11 |
| §2.2 / §2.3 | The engine owns exactly one generated OpenCode plugin; plugin generation is delivered | header, §C.3.1 |
| §3 | Hook: the 4th emitted kind, Continue claim corrected (P); Plugin (OpenCode): one generated shim under `.opencode/plugins/` | P5, §C.3.1 |
| §4.1 / §4.2 | The component diagram and data flow gain `resolve_effective_hooks`, `write_hook`, the sync-level `guard_config.json` and the `playbook-hook` runtime | §A.7, §C.1.3, §D |
| §4.3 | Sentinel quoted from `renderer.SENTINEL`; second position after frontmatter; the exception list (P) | P3 |
| §5.1 / §5.3 | Engine layout gains `hook_runtime/`, `security/`, `hook_policy.py`, `hook_registrations.py`, `guard_config.py`, `_sentinel.py`, `_pep503.py`, `gate_scan.py`, `resources/hooks/`, `resources/hook_shims/`; consumer layout gains `playbook/hooks/`, `.coding-agent-playbook/hooks/`, `.claude/hooks/playbook/launch.sh`, `.opencode/plugins/playbook-hooks.js` | §A.1, §C.0, §D.1 |
| §6.2 / §6.6 | `PromptFrontmatter.write_scope` and `output_contract`; `RuleFrontmatter.lint_codes`; the `Hook` canonical types and their round trip, including the sidecar | §A.3, §A.4, §A.7, §E.2, §E.3 |
| §6.4 | `has_dev_dependency` | §F.1.2 |
| §7.1 / §7.2 | `[hooks]`, `[guardrails]`, `[hooks.<hook-id>]`, `[hooks.commit_convention]`, the new `[metrics]` keys; the `.local.toml` exclusion | §B.1, §B.3, §F |
| §8.2 | Facts injected into the `sync --check` scratch run (P) | P2 |
| §9.3 | `SandboxedEnvironment` (P) | P1 |
| §9.7 | The `hook_advisory` and `hook_claude_settings` formats; Claude command frontmatter for `write_scope` | §C.4.1, §C.4.3 |
| §10.1 | `hook_support`, `begin_sync`, `write_hook`, `managed_lock_entries`; the stale `finalize` sentence fixed | §C.1.1 |
| §10.2 | Continue: advisory degrade only (P) | P5 |
| §10.3 (new §10.3.2) | settings.json managed merge, launcher, pin, heartbeat line, command frontmatter | §C.2, §C.4 |
| §10.4 | Guardrails section | §C.4.2 |
| §10.6 / §10.6.1 / §10.6.2 / §10.6.4 | `agent: plan` for read-only prompts; the shim exception; OpenCode ≥ 1.18.29 | §E.3, §C.3, QC-14 |
| §10.7.2 / §10.7.3 | Hooks advisory and the `.playbook/hooks/` sidecar | §C.6 |
| §11 | Hook layer merge policies; `mandatory` | §A.6 |
| §12.1 | `init` asks to enable hooks; `--no-hooks` | §B.1 |
| §12.2 / §12.3 / §12.4 | Sync summary, orphans, scoped drift, the Hooks block | P2, §C.1.5, §C.2.6 |
| §12.6 | Config-less validate; validate-gated sync; H1–H21 | P8, §B.5 |
| §12.7 | `playbook render <hook-id>` | §C.4.1 |
| §12.11 / §12.12 | `playbook ci`; a pointer to §21.5 | §F.5 |
| §12.13 ff. (new) | `playbook-hook dispatch \| simulate \| doctor`; `gate-scan`, `scan-secrets`, `scan-sinks`, `check-deps`, `check-commit-trailers`, `check-notebooks` | §D.1, §D.9, §E.2–§E.4 |
| §13.1 / §13.2 | New pre-commit ids, `default_install_hook_types`, `--no-run-tests` | §E.4, §F |
| §13.2 / §16.4 / §17.3 | `playbook-secrets` replaces the unshipped gitleaks promise; the detector skips secret paths (P7) | §E.4, P7 |
| §14.4 | Lockfile v2 `[[entries]]` with provenance and scoped entries (P) | P4, §B.6 |
| §16 | Hook test strategy: `tests/hook_runtime/`, `tests/hooks/`, `tests/security/`, golden payloads, gated latency and e2e tests | §D.9, §E.0.7 |
| §17.1 | HTTP hook handlers are rejected by validate (P) | P5 |
| §17.4 | The audit-line writer is `security/audit.py` | P-D4, §D.6.2 |
| §19 | Q8 resolved; Q1 partially answered | header |
| §20.2 | `ArtifactSource.list_hooks` (concrete default) | §A.5 |
| §20.10 | Manifest kind `"hook"`; the new sidecar fields | §C.6, §A.7 |
| §21.2.1 / §21.2.2 / §21.3 / §21.5 / §21.7 / §21.8 | New metrics, selection, flags, invariants, caveats | §F.7 |
| Implementation order (recap) | Track P → K1 … K11 | §H |

## §K — Open questions for the user (all resolved)

Each question has one owner; the per-section lists (§B.7, §C.8, §D.12, the §E lists, §F.9) point here. The proposed default applies unless the user decides otherwise.

**Status (2026-10-14).** The user accepted the proposed default for all 45 questions; every default below is now a decision, and the body text reflects them (OQ-19, OQ-43, OQ-45 and OQ-5 edited in place). No question remains open. The commitizen start-up figure below is explicitly deferred (K11), and the note after it records how OQ-6 was applied.

| ID | Question | Proposed default | Source | Status |
| --- | --- | --- | --- | --- |
| OQ-1 | `[guardrails]` as a second top-level table, or fold its domains into `[hooks.<domain>]`? | Keep `[guardrails]`: twins and permission rendering read policy even with hooks disabled. | §B.7 Q1 | Accepted |
| OQ-2 | Ignore `[hooks]` / `[guardrails]` in `.local.toml` (no local *enable* of an opt-in hook)? | Accept; per-developer deviation is runtime-only (`PLAYBOOK_HOOKS_DISABLE`; a developer's own command launchers through `PLAYBOOK_HOOK_WRAPPER_PREFIXES`, §D.7, read like the escape hatches and never able to hide a guarded command). | §B.7 Q2 | Accepted |
| OQ-3 | Absent `[hooks]` ⇒ off, or on for every consumer on upgrade? | Off; `playbook init` asks (default yes), `--no-hooks` opts out, and sync prints one notice line. | §B.7 Q3 | Accepted |
| OQ-4 | Keep P6–P9 in Track P? P8's validate-gated sync may break consumers whose content fails `playbook validate` today. | Keep in P; gate sync on the full validate set, with a MIGRATION note to run `playbook validate` before upgrading. | §B.7 Q4 | Accepted |
| OQ-5 | Commit the CLAUDE.md edits, or keep them local under the harness-files policy? | Keep them local (the harness-files policy); SPEC §4.3 and the README carry the sentinel wording and the invariants. | §B.7 Q5 | Accepted |
| OQ-6 | **Dogfooding.** D-Q3 says this repo sets `cutover_date` to the date the hooks PR lands, which needs a committed `.coding-agent-playbook.toml`; that flips the engine repo out of config-less validate (H16/H21 apply) and puts `sync --check` and `playbook ci` into its CI. Commit it, or keep the settings in the user's untracked setup? | Honor D-Q3 minimally: commit only `[hooks.commit_convention] cutover_date` (and `[tool.commitizen]` in `pyproject.toml`) and add the `playbook ci` job; keep the developer's own wrapper prefixes (`PLAYBOOK_HOOK_WRAPPER_PREFIXES` in the launching shell, §D.7), the command-convention rows and the trailer rows in the user's untracked setup. `.local.toml` cannot hold `[hooks]` (§B.1). | §F.4.1, §F.5, §E.4 | Accepted |
| OQ-7 | TTY-only trust approvals acceptable for scripted machine bootstrap? | Accept; document "one interactive `playbook sync` per machine". | §B.7 Q7 | Accepted |
| OQ-8 | TOFU on (distribution, version) for entry-point handlers? | Not in v1: `allow_code_from` plus the consumer's dependency lock; revisit when an overlay ships one. | §B.7 Q8, §D.3.1 | Accepted |
| OQ-9 | Align skills to recursive marker discovery? | Keep the difference; align skills in a separate PR if wanted. | §B.7 Q9 | Accepted |
| OQ-10 | In-memory `sync --check` (no scratch copy)? | Defer; P2's hardening suffices for v1. | §B.7 Q11, P2 | Accepted |
| OQ-11 | **OpenCode V1 vs V2.** Keep the inert V2 `setup()` stub, or port the shim to V2 now (`ctx.tool.hook("execute.before")`, `ctx.permission.hook("evaluate")`, the tool and arg renames)? | V1 target with the inert stub (L5); port when V2 becomes OpenCode's default installer. | QC-1 | Accepted |
| OQ-12 | Render `user_prompt_submit` on OpenCode (`chat.message` blocking is undocumented)? | Not in v1; only after an env-gated e2e test proves a throw blocks. | QC-2 | Accepted |
| OQ-13 | OpenCode Stop: evidence-only, or a bounded SDK re-prompt? | Evidence-only (locked for v1). | QC-3 | Accepted |
| OQ-14 | Windows without Git Bash: accept fail-open, or a per-machine PowerShell launcher? | Accept fail-open, documented; a per-machine launcher would commit machine-specific bytes. | QC-4 | Accepted |
| OQ-15 | Incidental reach under Copilot CLI (fail-closed `preToolUse`; Windows deny-all risk). | Inert on foreign payloads (locked); a **release blocker for repos used with Copilot CLI** until verified against a real CLI (env-gated, never in CI); `doctor` warns when `copilot` is on PATH. | QC-7 | Accepted |
| OQ-16 | **`permissions.allow` rendering:** render the remediation commands by default, as the catalog wants? | Opt-in through `[hooks] render_remediation_allow` (off); never `pytest` or `mypy`. | QC-8 | Accepted |
| OQ-17 | Advisory degrade (L1) vs the codemap's no-op `write_hook`? | Keep L1's degrade, with explicit enforcement labels. | QC-10 | Accepted |
| OQ-18 | Overlay strict mode: the `onFailure` trigger and `--strict-launch`. | Render `"onFailure": "block"` + `--strict-launch` on a registration iff an enabled member on that event has `on_error: deny`, never on `pre_tool_use` unless the overlay opts in explicitly; no separate `[hooks] harness_failure` key. | QC-11 | Accepted |
| OQ-19 | One async, non-deciding, output-free `PostToolUse` registration for local-audit-log (amends L3). | Sign off, limited to `ASYNC_SAFE` handlers; if rejected, local-audit-log rides the synchronous registration without `Read`/`Grep`/`Glob` coverage. | QC-13 | Accepted |
| OQ-20 | OpenCode version floor ≥ 1.18.29. | State it in SPEC §10.6 and the README; `doctor` warns below it. | QC-14 | Accepted |
| OQ-21 | `ask` under `bypassPermissions`, and under `auto` for non-Bash tools and sandboxed Bash. | Treat both as attended; verify against the real CLI before GA; if an ask is dropped there, render deny. | Q-D1 | Accepted |
| OQ-22 | Stop warn channel: `systemMessage` only (D-3)? | Confirm D-3. | Q-D3 | Accepted |
| OQ-23 | The temp-index fingerprint writes loose blobs: accept, or default to `stat` mode? | Accept (`git gc` prunes them); `stat` mode stays the fallback. | Q-D4 | Accepted |
| OQ-24 | Sibling worktrees never consult their own `guard_config.json`? | Confirm: the registering repo's config applies. | Q-D5 | Accepted |
| OQ-25 | Windows support level? | "Best effort, documented"; CI stays ubuntu-only. | Q-D6 | Accepted |
| OQ-26 | Absolute p95 ≤ 100 ms: a hard contract or a target? | A target reported by `doctor`; CI asserts only the excess over the interpreter floor (gated). | Q-D10 | Accepted |
| OQ-27 | Child processes for jinja2-importing commands (vs relaxing L3 to "never on the hot path"). | Keep child processes (+0.4–0.7 s on rare canonical edits). | §E OQ1 | Accepted |
| OQ-28 | `subagent_start` as a Claude-only canonical event, or compare against the `session_start` snapshot? | Option B: no new event; compare against the `session_start` snapshot. | §E OQ2 | Accepted |
| OQ-29 | Stop on OpenCode depends on an `experimental.*` API. | Accept; the AGENTS.md advisory remains the instruction; revisit with V2. | §E OQ3 | Accepted |
| OQ-30 | The heartbeat line changes CLAUDE.md once per opted-in repo. | Accept; MIGRATION note. | §E OQ6 | Accepted |
| OQ-31 | SPEC.md:141 ("avoid `{% if %}` inside rule bodies") vs shipped `.md.j2` rules that use it. | Out of scope for PR K; no validate rule; settle in a separate SPEC/content PR. | §E OQ7 | Accepted |
| OQ-32 | Eval fixture-integrity mechanism: a per-task hash in `task.toml`, or a CI diff? | A CI diff of `eval_tasks/*/setup/**` against the merge base, as a `playbook ci` step (no schema change). | §E OQ8 | Accepted |
| OQ-33 | A Claude `ConfigChange` hook to stop settings edits from applying in-session. | Defer; control-plane-guard's PreToolUse deny is the in-session control; revisit as a Claude-only adapter-level registration. | §E OQ12 | Accepted |
| OQ-34 | Add "do not modify the code" to the `security-review` and `find-injected-vulnerability` prompt bodies? | Yes, in K7, so the advisory text matches `write_scope`. | E-Q4 | Accepted |
| OQ-35 | Ticket key: a trailer here, the subject through commitizen `schema_pattern`? | Confirm the split. | E-Q5 | Accepted |
| OQ-36 | PEP 503 rewiring of `detector._parse_dep_name` changes `detector_cache` keys once. | Accept; changelog and MIGRATION note. | E-Q8 | Accepted |
| OQ-37 | A fallback for a pinned ruff without `ruff rule --all --output-format json`. | One `ruff rule <code>` per code at sync, never at hook time. | E-Q9 | Accepted |
| OQ-38 | Default selection of the new metrics. | Opt-in, so consumers' `playbook-metrics` results stay byte-stable on upgrade. | Q-F3 | Accepted |
| OQ-39 | `ruff_violations` regression tolerance. | Keep the exact compare (`max_worsening = 0`, the §21.7 invariant). | Q-F4 | Accepted |
| OQ-40 | The live `[metrics]` read for the `docstrings` and `coverage` stages. | Accept, for parity with the twins. | Q-F5 | Accepted |
| OQ-41 | `coverage` forces the `tests` stage to a full-suite run. | Accept: one shared `SuiteRun` per fingerprint. | Q-F6 | Accepted |
| OQ-42 | Keep the strict `docstring_example` check at all? | Keep it, opt-in and off by default (about 40 stdlib lines): it encodes the user's "intent + one usage example" docstring convention. | Q-F7 | Accepted |
| OQ-43 | **(new)** H11 requires every declared event to be reachable on every listed adapter, so toolchain-missing-hint (`post_tool_use_failure`) and local-audit-log (`session_end`, `user_prompt_submit`) cannot list `opencode` although their entries describe OpenCode behaviour. Relax H11? | Yes: require at least one reachable event per listed adapter; an unreachable event on a listed adapter is a validate warning plus a `degraded` label, and is simply not registered there. | §B.5 H11 vs §E.3, §E.5 | Accepted |
| OQ-44 | **(new) L9 commit convention.** Confirm that D-Q2/D-Q3 close L9: commitizen's default `cz_conventional_commits`, a `cz_customize` `schema_pattern` for scoped or custom conventions, and the committer-date cut-over, with no engine-side `conventional \| scoped \| regex` setting. | Confirm; ship no preset beyond commitizen's default. | L9, D-Q2, D-Q3 | Accepted |
| OQ-45 | **(new)** The `user_prompt_submit` active-prompt record is bound only as prompt-write-scope-guard's `prompt_scope_guard:ledger` companion, so disabling that guard silently makes the prompt-output-contract-on-stop stage inert. | Make the record a dispatcher branch, active whenever either hook is enabled. Amended by review finding #6: no `user_prompt_submit` registration for it; each consumer resolves the turn's prompt from the transcript (once per turn), and only the `Skill` record stays a dispatcher branch. | §E.0.4, §E.2, §E.3 | Accepted |

**Deferred figure (measure before GA):** the commitizen start-up cost on `git commit` / `git push` segments (0.1–0.3 s, an estimate in F.4.2) is still unmeasured. K10 found no `cz` on the implementation machine, and installing one needs the package index, so neither K10 nor K11 has a number. The measurement is ready to run: `tests/hooks/test_commit_message_convention.py::test_cz_startup_latency`, gated on `PLAYBOOK_LATENCY_TESTS=1` with `cz` on PATH, prints the median of five `cz check --message` runs and asserts that it stays under the hook's 3 s `cz` timeout. Until it has run, F.4.2's figure remains an estimate. The cost lands only on `git commit` / `git push` segments, and the hook fails open on a timeout.

**OQ-6 as applied (K11).**
- **The committed `.coding-agent-playbook.toml`.** It carries `[hooks.commit_convention] cutover_date` as a quoted string, plus the `schema_version` / `[engine]` / `[project]` identity that every loadable config needs. `Config.from_dict` requires that identity: with a hooks-only file, `playbook validate` at the engine root fails with a `KeyError`. With it, validate leaves config-less mode and runs H15/H16/H21. The file has no `[hooks]` key besides the cut-over, so hooks stay off.
- **`pyproject.toml`** gains `[tool.commitizen] name = "cz_conventional_commits"` with no version or bump keys.
- **`.github/workflows/ci.yml`** gains a pull-request-only `playbook-ci` job. It checks out with `fetch-depth: 0`, installs `-e .` plus `commitizen>=3`, and runs `playbook ci --steps commit-convention --base origin/main`, with `PLAYBOOK_PR_TITLE` set only in `env:`. The test matrix and its `.[dev]` install are unchanged.
- **`tests/integration/test_dogfood_config.py`** pins all three.
- **The cut-over date.** `cutover_date` is `"2026-10-15"`: set it to the merge date before landing. The hooks PR's title must itself pass `cz check`, because the job also checks `PLAYBOOK_PR_TITLE`.

**Resolved during editing (kept for traceability):** QC-5, QC-6, QC-9, QC-12, Q-D2 (→ OQ-18), Q-D7, Q-D8, Q-D9, E-Q1 (→ OQ-19), E-Q2, E-Q3, E-Q6 (→ OQ-18), E-Q7, E-Q10, §B.7 Q6 (D-Q3), §B.7 Q10, §E OQ4/OQ5/OQ9/OQ11 (§E OQ10 is a citation note, not a question), Q-F1, Q-F2, Q-F8.
