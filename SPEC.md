# SPEC.md — coding-agent-playbook
| Field | Value |
| --- | --- |
| Version | 0.18 (draft) |
| Status | Proposed |
| Last updated | 2026-10-14 |
| Authors | Max Pereira, with Claude |
| Audience | Implementers, reviewers, future contributors |
| License | Apache-2.0 (engine); organization overlays may be private |

**Changelog**
- **0.18** — No command writes local overrides into the committed config: an `init` re-run and `playbook check --refresh` now rewrite `.coding-agent-playbook.toml` from the committed file alone (new `FileSystemStateSource.read_committed_config_table`, shared through `commands/_committed_config.py`), not from the `.local.toml` merge `load_config` returns. Both used to save that merge, which wrote one engineer's `adapters_enabled` (reordered), `overlays_enabled`, `[user_choices]` and `[output]` into the team's file (an `init` re-run also swapped the committed hooks to match a personal `[output] commit`), and both deleted every key `Config` does not read — `[links]`, `[metrics]`, a future table, `[project] homepage`. Now an `init` re-run replaces, not merges, the keys `Config` owns (`config_entries.CONFIG_MANAGED_KEYS`; inside `[project]`/`[engine]`/`[storage]`/`[output]` only the keys it reads, `config_entries.CONFIG_MANAGED_TABLE_KEYS`) with the updated config and writes everything else back with the same parsed values; `check --refresh` replaces `[detector_cache]` alone and writes every other entry back as parsed, not through `Config` (whose round trip dropped explicit empty lists and filled defaults). `FileSystemStateSource.save_config_table` is the committed file's one writer and `commands/_committed_config.ConfigRewrite.save` its one caller, built only by that module's `plan_*` functions — an AST test pins it. Before writing, both commands check that the result still loads with the local file merged on top (`preview_config`; a first `init` too), and a committed file missing a required key only the local file supplies exits 2 with nothing written, where it used to be completed with that personal value. Each config file is checked whole on its own, naming it, in every command: a file `tomllib` cannot read (syntax, not UTF-8, nested too deeply), a `project`/`engine`/`storage`/`output`/`detector_cache`/`user_choices` that is not a table, and a malformed `[output]` are `ConfigError`s (exit 2) where they were tracebacks or were reported against the wrong file, and a committed non-table is refused even when a local table hides it. A missing required key (`schema_version`, `[project] name`/`kind`, `[engine] version`) is a `ConfigError` (exit 2) in every command, no longer a `KeyError` traceback. `init` checks `--overlays` even when a local `overlays_enabled` replaces it for its own sync, since that list is what gets committed. The TOML writer (`_toml.dump_toml`, moved from `sources/filesystem.py::_dump_toml`, + `_toml.format_scalar`) now writes anything `tomllib` parses — floats (a NaN's sign included), dates/times, tables, arrays of tables and inline values at any depth (both walks are iterative: no `RecursionError`), keys that need quoting — and fixes four latent writer bugs: a non-ASCII bare key and a raw U+007F made the file unparseable; an integer past Python's int-to-str limit (which `tomllib` reads from `0x`/`0o`/`0b` literals) raised `ValueError`, and is now written in hex; and keys and header parts were written unquoted, so a dotted `[detector_cache]` dependency name (`ruamel.yaml`) or a `[user_choices]` key such as `"docs.style"` was re-read as a nested table. Config/lockfile/manifest bytes change only where the old writer crashed or its output was refused or misread; the `agent_harness` manifest now also carries float and date frontmatter values, which used to stop `sync` with a `TypeError` (§7.1, §7.2, §12.1, §12.4, §12.5, §20.3, §20.10).
- **0.17** — Bundled opt-in packs: the engine wheel now ships **packs**, importable subpackages under `coding_agent_playbook.packs.*` layered exactly like overlay packages but needing no extra install, **off by default** and enabled by listing the pack's dotted name in the top-level `overlays_enabled` key. The first pack, `coding_agent_playbook.packs.superpowers`, is a near-verbatim, self-contained port of the Superpowers skills library (v7.0.0, MIT): 15 skills rendered like any canonical skill — natively and byte-identically to `.claude/skills/<id>/`, `.opencode/skills/<id>/` and the `shared_skills/<id>/` hub through the shared `SkillWriter` (`SKILL.md` with the sentinel as its first body line), degraded to Continue prompts, and to `skills/<id>/` under the opt-in `agent_harness` — with only the self-containment edits applied (supporting files moved under `references/`/`scripts/`, an `id` frontmatter key, plain skill names instead of `superpowers:<skill>`, no external URLs, upstream-plugin coupling removed). Dropped: the brainstorming visual companion, the SessionStart bootstrap hook, and diagnosing-superpowers' upstream issue filing. MIT notice in the pack's `LICENSE` + `ATTRIBUTIONS.md`, and as `references/LICENSE` in every skill so it travels with each synced copy. No rendering behaviour changes: opting out of the pack or overriding one of its skills is settled by the v0.16 lockfile leftover policy (§4.2 step 9). **Config hardening (same release):** the enabled lists are the top-level `overlays_enabled` / `adapters_enabled` keys only, above the first `[table]` header — an `[overlays]`/`[adapters]` table (incl. the dotted `overlays.enabled` key), an enabled key nested in any table (what applying the fix-it hint in place, or appending the key to the end of the file, produces), a close misspelling such as `overlay_enabled`, or a value that is not a list of non-empty strings is a new `config.ConfigError` naming the file (`.toml` and `.local.toml` are checked separately, before the merge) and showing the line to write and where, and every command that loads the config (`sync`, `check`, `validate`, `render`, `eval`, `init`) prints `error: …` and exits 2 before writing anything (each of these shapes used to read as an empty list, so `sync` rendered only `AGENTS.md` and deleted the rest as leftovers); `[output]` value errors are `ConfigError`s too (they were a traceback). An unusable overlay — its import fails (missing, or raising at import time, which used to be a traceback and is now reported with its error), or it imports with no `resources/` directory — is caught by the one shared preflight check in every command, one line per overlay: `sync` refuses (exit 1), `validate` fails (exit 1), `check` flags it and no longer reports a clean state (exit 0), `init` refuses before writing (exit 2; it checks the overlays its sync will use — `--overlays`, or the local file's list that replaces it); a pack-like typo lists the bundled packs (discovered with `pkgutil`). Every config example uses the top-level keys, and §7.1 shows the `detector_cache` table the code reads and writes (§4.2, §7.1, §7.2, §10.7, §10.8, §11.1, §11.5, §12.1–§12.6). `[tool.ruff] extend-exclude` keeps the vendored text byte-faithful; `tests/packs/` gates it (§5.1, §6.3, §11.5).
- **0.16** — Generated output is **local-only by default**: everything `playbook sync` renders into a consumer repo (`AGENTS.md`, `.claude/`, `.continue/`, `.opencode/`, skill directories, the lockfile) is gitignored and never committed. New `[output] commit = <bool>` toggle in `.coding-agent-playbook.toml` (default `false`; `playbook init` writes it explicitly; `true` restores the legacy committed-output policy). With `commit = false`, write-mode `sync` keeps an engine-owned **managed block** in the consumer's `.gitignore` current (root-anchored, escaped entries — one per generated file, skill directories collapsed to `/<dir>/`; byte-preserving, atomic, idempotent; malformed markers fail loudly) and warns on stderr about generated paths git still tracks, printing the exact `git rm -r --cached -- …` to run (it never changes git state). Leftovers of an earlier sync stay owned through the previous lockfile: deleted only when pristine, untracked and every enabled adapter is installed, else kept (and, for `commit = false`, kept ignored). This **lockfile leftover policy is the one deletion policy for stale native-skill output**, under both `commit` settings: adapters' `cleanup_stale` never deletes inside a skill directory, and a file the engine never wrote — even one dropped into an engine-owned skill dir — is never deleted (it replaces the v0.15 `SkillWriter` cleanup, which deleted every unwritten file in an engine-owned dir). It deletes only inside the `output_locations` installed adapters declare (§10.1) — never under `.git/`, never through a symlink the user put on the path — prunes emptied directories no higher than the skills root (never a symlinked root's target), and fails closed when git cannot say whether a leftover is tracked (asked case-insensitively, matched in NFC or by file identity); a file/folder swap inside a skill dir displaces only what the same policy would delete, and the pre-v0.15 lockfile claim needs unchanged `SKILL.md` bytes. Stale-vs-written comparisons use file identity (the `agent_harness` cleanup too), so a case-only skill-id rename on a case-insensitive filesystem never deletes fresh output; `sync --check`/`--check-staged` render into an empty scratch dir but decide skill-dir ownership against the real tree, so they skip exactly the skill dirs write mode skips. A missing overlay package makes every `sync` mode refuse to run. `sync --check` reports a stale/missing block as drift; the new **`sync --check-staged`** fails a commit that stages generated output. New hooks: `playbook-sync` (`post-checkout`/`post-merge` auto-sync) and `playbook-no-generated-output` (pre-commit guard); `playbook-sync-check` is kept as the legacy hook for `commit = true`. New stdlib modules `gitignore.py` + `git_client.py` (an injectable read-only `GitClient`) and `commands/_sync_output.py` (§4.2, §5.3, §6.3, §7.1, §10.8, §12.1–§12.3, §13, §14.4).
- **0.15** — Native skills for every Agent-Skills harness + the `shared_skills/` hub: a new shared `SkillWriter` (`adapters/_skill_writer.py`) is the single source of truth for a native skill directory (`<root>/<id>/SKILL.md` + byte-copied `scripts/`/`references/`), byte-identical across roots. `claude_code` writes `.claude/skills/`, `opencode` now writes **`.opencode/skills/`** natively (no longer relying on `claude_code`), and the new **`shared_skills`** adapter (on by default, not force-enabled) writes the cross-agent hub `shared_skills/`. Two bug fixes: `SKILL.md` frontmatter `name` is now the skill id (= directory name, the Agent Skills rule OpenCode enforces), and `SKILL.md` carries the sentinel as its first body line, so a skill directory is recognisably engine-owned (user-authored skill dirs are never touched; since v0.16 a deleted skill's unchanged, untracked files are removed by the lockfile leftover policy, §4.2 step 9, and edited or user-added files are kept). New `playbook validate` rule for the Agent Skills `id`/`name`/`description` constraints (id-less skills included). Ownership is decided before writing: a colliding hand-written skill dir is skipped with a warning, never overwritten (§6.3, §10.3, §10.6, §10.8, §12.6).
- **0.14** — Self-contained markdown links (PR L): every markdown link in every canonical artifact (rules, prompts, skills incl. `references/`) must be **self-contained** — relative targets resolve to a file inside the artifact's source layer (the package `resources/` or repo-local `playbook/`; `..`-escapes, absolute paths, and non-`http(s)` schemes are violations), and `http(s)` links pass only through the new `[links] allowed_domains` allowlist (default empty = fully strict). Deterministic (stdlib-only, no network), extraction masks frontmatter/code fences/inline code. New `links.py` + `config.parse_links_config` + a `playbook validate` rule (§12.6, §7.1); the engine's own artifacts are gated on CI by a pytest integration test. Design: `specs/prL-markdown-links.md`.
- **0.13** — Eval task-config redesign ("2b refined", Tracks C1–C8): the `[expected]`/`[metrics]`/`[rubric]` triple is replaced by a **layered** task config. Three layers share one `[<layer>.bind]` + `[<layer>].expr` shape — **`[gate]`** (deterministic boolean), **`[rubric]`** (llm-judge weighted), and an optional cross-trial **`[aggregate]`** — composed by a tiny boolean-expression DSL; `[verdict].trial` is a boolean expression over the layers, and the **verdict is *derived*** from the layer results (not re-run). There is **no `[expected]` block** — file predicates are gate `check`s (`file_exists`/`file_contains`/`file_unchanged`/`file_forbidden`). Thresholds are now **0–1 normalized**: every `Metric` owns a `Normalizer` (`evaluators/normalizer.py`: `RampNormalizer`/`PercentNormalizer`/`Identity`) mapping raw→0–1 goodness (higher = better), and `higher_is_worse` is **deleted** — `warn`/`fail`/`max_worsening` are 0–1 cutoffs. A check is `(type) × (metric|judge) × kwargs`: `check = "threshold"|"non_regression"` over a registered `metric=` **or** a `judge=` criterion (a `JudgeMetric` — an llm-judge criterion **is a metric**). New registries: checks via `@register_check` + `coding_agent_playbook.checks`, gates via `@register_gate` + the new **`coding_agent_playbook.gates`**; `{ref="name"}` resolves a registered composed **gate** or **rubric**. The `[aggregate]` layer is the same bind+expr shape over `pass_at_k`/`pass_pow_k` (`k` kwarg, `over ∈ {gate,rubric,verdict}`); the runner runs `N=max(k)` trials. Deleted from the prior model: the `[expected]`/`[metrics]`-triple authoring, `higher_is_worse`, `rubric_for_task`, `ExpectedOutcome`. Authoritative design: `specs/pr2b-task-config.md`; migration: `MIGRATION.md` (§6.5, §15.2/§15.3/§15.3.1, §21).
- **0.12** — Evaluator subsystem refactor (PR R6 — clean-slate): the fused `Evaluator` ABC + free `grade()` are replaced by three single-responsibility abstractions — **`Metric`** (`measure(ctx) -> list[Measurement]`), **`Check`** (`grade(ctx, measurements) -> CheckResult`, a boolean gate + optional partial-credit score), and **`Rubric`** (a weighted set of checks; `evaluate(ctx, measurements) -> EvaluationReport`). `Rubric` **is also a `Metric`** (it surfaces its composite via `measure()`), so a rubric thresholds into a check and nests into a Composite tree. A cost-tiered (`CostTier` DETERMINISTIC < EXECUTION < JUDGED) `scheduler` runs checks cheapest-tier-first with short-circuit, so a failing deterministic check **never invokes the LLM judge** (`playbook eval --run --full-scoring` forces every check). Entry-point groups are renamed/split: out-of-tree metrics register under **`coding_agent_playbook.metrics`** (was `…​.evaluators`), custom graders under the new **`coding_agent_playbook.checks`**. `grade()` is replaced by `Rubric.evaluate`; the `extra_evaluators` side-channel, `value_kind`/`to_score`, the weight-0/fail-floor `[expected]` hack, and `evaluators_for_task` are deleted. The authored `[expected]`/`[metrics]`/`[rubric]` task TOML is **unchanged** (zero authoring migration). Authoritative design: `specs/prR6-check-rubric.md`; migration guide: `MIGRATION.md` (§15.3/§15.3.1, §21).
- **0.11** — Judged scoring + `[expected]` unification + a second real runner (PR R2/R3): the judge is **live**. `Judge.score_criterion(criterion, artifact, n)` is the canonical per-criterion primitive (Option A; batch `score()` wraps it), with the opt-in `LLMJudge` (`name="llm"`, shells out to the `claude` CLI, `available()`-gated, never in CI) via the `coding_agent_playbook.judges` group. There is **no `ProgrammaticOnlyJudge`** — deterministic-only is simply no judge configured (`ctx.judge is None`). `[expected]` file checks are now **unified** into `evaluators_for_task` as real BOOL deterministic `Evaluator`s (`evaluators/expected.py`); the R1 interim inline compile is removed, so `[expected]` + `[metrics]` + (with a judge) `[rubric]` all flow through one `grade(…, extra_evaluators=…)` call. New opt-in **`OpenCodeRunner`** (`name="opencode"`, `available()`-gated, never in CI) joins `FakeRunner`/`ClaudeCodeRunner`. CLI: `playbook eval <id> --run [--judge llm] [--samples N]` (default no judge ⇒ deterministic-only). The §21.2.3 `Judge.score` signature debt is closed (§15.3/§15.3.1, §12.8, §21.2.3).
- **0.10** — Eval runner activation (PR R1): `HarnessRunner` becomes a concrete **template method** (materialize → render_prompt → `_invoke_agent` → capture → score) so an eval task runs end-to-end and is scored through the unified PR-M `Evaluator`/`grade()` model — the deterministic layers (`[expected]` file checks + `[metrics]` static/execution non-regression vs the `setup/` baseline) are **live**. Concrete runners: hermetic `FakeRunner` (default test driver) + opt-in `ClaudeCodeRunner` (`available()`-gated, never in CI), via the `coding_agent_playbook.runners` entry-point group. Result model evolved to **Option B** (`TaskResult.report: EvaluationReport`; `programmatic_checks`/`rubric_scores`/`CheckResult` retired). New `playbook eval <id> --run [--runner …] [--format …]` (no `--run-tests` — intent is in the task's `[metrics]`). Judged `[rubric]` scoring stays deferred to R2 (§15).
- **0.9** — Code-quality evaluator subsystem (PR M): one `Evaluator` abstraction with three families — static metrics (CC/WMC/LCOM4/DIT/CBO≈ via `ast`, MI via the optional `radon` extra), execution metrics (`test_pass_rate`/`coverage`, shelling out to the target's `pytest`), and judged criteria (the rubric, generalized; dormant until v1.1) — plus the standalone `playbook metrics` gate + a `repo: local` static pre-commit hook, and dormant eval `[metrics]` wiring (§21).
- **0.8** — Agent Harness round-trip support (PR H): the opt-in `agent_harness` output adapter (§10.7), the `playbook import-harness` / `playbook validate-harness` subcommands (§12.9, §12.10), and the `.playbook/manifest.toml` round-trip sidecar (§20.10).
- **0.7** — Storage source abstraction (§20), ML serialization-security guideline, air-gapped pre-commit.
---
## 1. Context
AI coding assistants — Continue, Claude Code, Codex CLI, Cursor — have each converged on their own way of loading context: rules, prompts, skills, hooks, and harness-specific config files. Teams that want a single source of truth for their conventions are forced to either (a) pick one assistant and accept lock-in, (b) maintain N copies of the same rules in N different formats, or (c) settle for `AGENTS.md` as a lowest common denominator and lose the richer features each assistant offers.
`coding-agent-playbook` provides a single canonical source for organizational coding context and renders it into whatever shape each assistant expects. It is opinionated, Python-first, and designed to be reusable across teams and organizations. The core engine is open-source and organization-agnostic. Organization-specific content (rules, prompts) ships as separate overlay packages that depend on the engine.
Prior art that shaped this design:
- **LinkedIn's CAPT** (Contextual Agent Playbooks and Tools) — established the playbook pattern at enterprise scale, validated the "playbook as executable institutional knowledge" concept.
- **The `rules` CLI from rules.so** — render-from-canonical model, the operational pattern this spec extends.
- **continuedev/awesome-rules** — community catalogue of rule shapes; informs the rule taxonomy.
- **The convergence on `AGENTS.md`** (Codex, GitHub Copilot, Cursor, and now Continue) as the universal baseline.
- **The ACE paper (Agentic Context Engineering)** — argues for contexts as evolving playbooks; influences the versioning and incremental-update semantics here.
## 2. Goals and non-goals
### 2.1 v1 goals
**G1 — One canonical source, multi-harness output.** A team writes a rule once. The tool renders it to `.continue/rules/`, `CLAUDE.md`, `.opencode/command/`, and `AGENTS.md` automatically, using each harness's native features (frontmatter, globs, sections). v1 primary adapters: Continue, Claude Code, OpenCode. Universal fallback: AGENTS.md.
**G2 — Detect-and-condition.** Rules and prompts are gated by what's actually in the repo: Python version, installed frameworks, presence of notebooks, etc. A FastAPI rule does not ship to a non-FastAPI repo.
**G3 — Three-layer overlay model.** Engine package ships generic content. Organization-specific packages (e.g. `playbook-rules-bnp`) ship overlay content. Consumer repos can override locally.
**G4 — Pre-commit-native distribution.** Installation produces pre-commit-managed sync hooks. By default (`[output] commit = false`, §7.1) generated output is **local-only**: it is gitignored, re-rendered automatically after every checkout and merge, and a commit that stages any of it fails. Repos that opt into committed output (`commit = true`) keep the legacy guarantee instead: drift between the canonical source and what is checked into the repo fails the commit and CI.
**G5 — Air-gapped friendly.** No required network calls at sync time. Internal PyPI distribution. No HTTP-based hooks shipped by default. No telemetry.
**G6 — Eval task authoring (Tier 0).** v1 ships the schema, loader, validator, and read-only CLI for prompt-associated eval tasks (Section 6.5). The runner, programmatic checks, and LLM-as-judge are deferred to v1.1 (Tier 1) and v2 (Tier 2) respectively. Authors write tasks alongside prompts from day one; the corpus accumulates as documentation and is ready when the runner lands.
### 2.2 v1 non-goals (named so people stop asking)
- Skills are first-class only for harnesses that implement the Agent Skills layout (`<root>/<name>/SKILL.md`): Claude Code (`.claude/skills/`) and OpenCode (`.opencode/skills/`), plus the agent-neutral `shared_skills/` hub (§10.8) — and, in its own tree, the opt-in `agent_harness` adapter (`skills/<id>/SKILL.md`, §10.7). Adapters that keep the ABC default (Continue) degrade skills to prompts; the rules-only `agents_md` adapter does not emit skills at all.
- No MCP server configuration management. (v2.)
- No Cursor dedicated adapter beyond the universal AGENTS.md fallback. (v2.)
- No Codex CLI dedicated adapter — Codex reads AGENTS.md natively, so the universal adapter is sufficient.
- No OpenCode agents (custom modes in `.opencode/agent/`) — users author these by hand. (v2; see open question 9.)
- No OpenCode plugins (`.opencode/plugin/`) — users author lifecycle hooks by hand. (v2; see open question 8.)
- No `opencode.json` management — MCP servers, permissions, model selection are owned by the user.
- No eval runner — `playbook eval` prints a deferred-implementation message; task authoring + validation is v1, execution is v1.1 / v2.
- No LLM-as-judge — rubric scoring is human-only until v2.
- No web UI for browsing or authoring rules.
- No telemetry of any kind.
- No automatic generation of rules from PR review comments.
### 2.3 v2+ aspirations
- MCP server registry and per-harness MCP config generation (including OpenCode's `opencode.json` mcp block)
- Cursor dedicated adapter with `.cursor/rules/*.mdc` output
- OpenCode plugin generation from canonical hook descriptions (highest-ROI v2 feature for banking-compliance contexts)
- OpenCode agent definitions as a fifth canonical artifact category
- Eval runner (Tier 1) — programmatic checks against agent output, per-harness comparison
- LLM-as-judge for rubrics (Tier 2) with calibration tooling
- Per-team overlay packages discoverable via internal registry
- Rule provenance and changelogs
## 3. Glossary
- **Rule** — a unit of always-on or context-scoped guidance loaded into the assistant's system prompt. Example: *"Use ruff for linting, never black or flake8."* Rendered as `.continue/rules/*.md`, or as sections of `CLAUDE.md` / `AGENTS.md`. OpenCode reads `AGENTS.md` natively, so rules reach OpenCode via the AGENTS.md adapter rather than a dedicated path.
- **Prompt** — a reusable, named instruction the user invokes explicitly. Example: `/refactor` or `/generate-tests`. Rendered as `.continue/prompts/*.md` with `invokable: true`, `.claude/commands/*.md`, or `.opencode/command/*.md`.
- **Skill** — a richer prompt with bundled scripts and progressive disclosure, in the Agent Skills layout (`<name>/SKILL.md` + `scripts/` + `references/`). Written natively to `.claude/skills/` (Claude Code), `.opencode/skills/` (OpenCode) and the cross-agent `shared_skills/` hub by one shared `SkillWriter`, so every copy is byte-identical (the opt-in `agent_harness` adapter also writes it natively, in its own `skills/` tree). Degraded to a prompt only by adapters that keep the ABC default (Continue); not emitted by the rules-only `agents_md` adapter.
- **Hook** — overloaded term. Two distinct meanings:
  - **Git pre-commit hook**: a shell command run before a commit lands (via pre-commit.com framework).
  - **Assistant lifecycle hook**: PreToolUse / PostToolUse / SessionStart etc., supported by Claude Code and Continue CLI. The engine ships configuration for both kinds and keeps them visually separate in source.
- **Plugin (OpenCode)** — JS/TS module under `.opencode/plugin/` that subscribes to OpenCode's runtime events (`tool.execute.before`, `session.idle`, etc.). The OpenCode equivalent of Claude Code's declarative hooks. v1 does not generate plugins; users author them by hand. See open question 8.
- **Agent (OpenCode)** — a named mode with its own model, permissions, and system prompt, defined in `.opencode/agent/<name>.md`. OpenCode ships built-in `build` and `plan` agents and supports user-defined custom agents. Out of scope for the canonical artifact model in v1; users author custom agents directly. See open question 9.
- **Eval task** — a reproducible test case associated with a prompt: a starting state (`setup/` files + mock detector facts), an invocation (`prompt_args`, `input_variables`), and a notion of success (programmatic checks + human-readable rubric). v1 ships the authoring format and validator; the runner that executes tasks against a real agent lands in v1.1 / v2. See Section 6.5.
- **Harness** — a coding assistant runtime (Continue, Claude Code, OpenCode, Codex, Cursor).
- **Adapter** — a module that translates canonical artifacts into a specific harness's native format and writes them to that harness's expected location.
- **Detector** — a module that inspects the consumer repo and produces a facts dictionary used as the Jinja rendering context.
- **Renderer** — a module that applies Jinja2 to canonical templates with the facts dictionary, producing final output text.
- **Engine** — the `coding-agent-playbook` Python package: detector + renderer + adapters + CLI.
- **Overlay** — an organization-specific package (e.g. `playbook-rules-bnp`) shipping additional rules and prompts that ride on top of the engine's content.
- **Consumer repo** — the user's ML / data science / application repo into which the playbook is installed.
## 4. Architecture overview
### 4.1 Component diagram
```
                                    ┌──────────────────────────────────┐
                                    │      coding-agent-playbook       │
                                    │            (engine)              │
                                    │                                  │
                                    │  ┌────────────────────────────┐  │
                                    │  │  resources/   (canonical)  │  │
                                    │  │   ├── rules/*.md|*.md.j2   │  │
                                    │  │   ├── prompts/*.md|*.md.j2 │  │
                                    │  │   └── skills/*/SKILL.md    │  │
                                    │  └─────────────┬──────────────┘  │
                                    │                │                 │
                                    │                ▼                 │
                                    │  ┌────────────────────────────┐  │
                                    │  │  renderer (Jinja2)         │  │
                                    │  └─────────────┬──────────────┘  │
                                    │                │                 │
                                    │                ▼                 │
                                    │  ┌────────────────────────────┐  │
                                    │  │  adapters (one per harness)│  │
                                    │  │   ├── continue             │  │
                                    │  │   ├── claude_code          │  │
                                    │  │   ├── opencode             │  │
                                    │  │   ├── shared_skills        │  │
                                    │  │   └── agents_md            │  │
                                    │  └────────────────────────────┘  │
                                    └──────────────────────────────────┘
                                                    │
                              ┌─────────────────────┴─────────────────────┐
                              │                                           │
                              ▼                                           ▼
              ┌──────────────────────────────┐         ┌──────────────────────────────┐
              │  playbook-rules-bnp          │         │      consumer repo           │
              │     (overlay)                │         │                              │
              │                              │         │  .coding-agent-playbook.toml │
              │  Adds:                       │         │                              │
              │   - banking-security rules   │         │  Generated (gitignored):     │
              │   - PII redaction prompts    │         │   .continue/rules/*.md       │
              │   - LiteLLM-aware config     │         │   .continue/prompts/*.md     │
              │                              │         │   .claude/CLAUDE.md          │
              └──────────────┬───────────────┘         │   .claude/commands/*.md      │
                             │                         │   .claude/skills/*/          │
                             │                         │   .opencode/command/*.md     │
                             │                         │   .opencode/skills/*/        │
                             │                         │   shared_skills/*/           │
                             │                         │   AGENTS.md                  │
                             │                         │                              │
                             │                         │  Merged by init (committed): │
                             └─────── merges ─────────►│   .pre-commit-config.yaml    │
                                                       │                              │
                                                       │  Personal overrides:         │
                                                       │   .coding-agent-playbook.    │
                                                       │       local.toml (gitignored)│
                                                       └──────────────────────────────┘
```
### 4.2 Data flow
The end-to-end flow of `playbook sync` in a consumer repo:
1. **Load configuration.** Read `.coding-agent-playbook.toml` (committed), merge `.coding-agent-playbook.local.toml` (gitignored, personal overrides) on top. The read goes through the configured `StateSource` (filesystem in v1; see Section 20); a config the engine would misread — an `[overlays]`/`[adapters]` table, an enabled key nested in a table or misspelled, a `*_enabled` value that is not a list of non-empty strings, a non-boolean `[output] commit` — is a `ConfigError` and `sync` exits 2 before anything else runs (§7.1). **Preflight:** every package in `overlays_enabled` must import without error in the running environment and ship a `resources/` directory, else `sync` (every mode) exits 1 naming it with the reason and writes nothing — rendering without an overlay would silently drop its rules and un-ignore its output (the classic case is a pre-commit hook venv, §13.1). The check is `_sync_preflight.unusable_overlays`, shared with `validate` (§12.6), `check` (§12.4) and `init --overlays` (§12.1). An enabled adapter with no installed entry point is only warned about (its earlier output is kept, step 9).
2. **Run detector.** Inspect `pyproject.toml`, lockfiles, filesystem. Produce a facts dictionary.
3. **Resolve overlays.** Query the configured `ArtifactSource` (filesystem in v1; see Section 20) for rules, prompts, skills, and eval tasks across the engine package, each declared overlay package, and the consumer's `playbook/` directory. Build a unified artifact list, with later layers overriding earlier ones by ID.
4. **Filter.** For each artifact, evaluate its `applies_if` predicate against the facts dictionary. Drop non-matching artifacts.
5. **Render.** Apply Jinja2 to each surviving artifact's template with `facts | config` as context.
6. **Dispatch to adapters.** For each enabled adapter (`continue`, `claude_code`, `opencode`, `shared_skills`, `agents_md`), pass the rendered artifacts; the adapter writes to its harness-specific locations.
7. **Write `AGENTS.md`** as the universal fallback regardless of which adapters are enabled.
8. **Stamp.** Write a `.coding-agent-playbook.lock` file containing the rendered file hashes via the configured `StateSource`; used by `playbook sync --check` to detect drift.
9. **Settle leftovers, then apply the output policy** (`[output] commit`, §7.1). Under **both** `commit` settings, first settle **orphans** — paths the *previous* lockfile lists that this run did not rewrite but that are still on disk (a removed skill's `SKILL.md` + scripts, a script dropped from a skill that still exists, everything a since-disabled adapter wrote). "Did not rewrite" compares file identity (`st_dev`/`st_ino`), not path spelling: after a case-only skill-id rename on a case-insensitive filesystem the old entry names the very file just written, so it is no orphan (and two entries naming one file yield one orphan, so no duplicate block entries). This is the **only** deletion policy for stale native-skill output — adapters' `cleanup_stale` never deletes inside a skill directory (`agent_harness`'s `skills/<id>/` included), and a file/folder swap inside a skill dir displaces only files this same policy would delete (§10.8) — and a path the previous lockfile does not list is a user file, never an orphan, even inside an engine-owned skill directory (with no readable previous lockfile nothing there is deleted). An entry is **released** — never deleted, no longer owned — when it leaves the repo, names a user/state file, has a `.git` segment, or reaches its file through a symlink (lockfile paths are recorded resolved, so a symlink on the way means the user re-pointed the path since — e.g. moved a skill dir into their own tree and linked it back — and git cannot see through it either), and, unless an adapter is missing, when it lies outside every installed adapter's declared `output_locations` (§10.1), so a hand-edited or merged lockfile can never aim `sync` at `.git/HEAD` or a source file. An orphan inside a declared location whose bytes still hash to its old lockfile entry and that git does not track is deleted, and the directories it leaves empty are pruned bottom-up: never above the declared directory that holds it, the declared directory itself (an emptied skills root such as `.claude/skills/`) only when it is a real directory as spelled — so the target of a symlinked root (`.claude/skills -> ../.agents/skills`) is never removed — never the repo root, never a directory with anything left in it. Directories emptied by `cleanup_stale`, or by a kept leftover the user later deleted, are pruned within the same bounds. If an enabled adapter is missing from the environment, all orphans are kept. "Git does not track it" is asked with case-insensitive literal pathspecs (`:(literal,icase)`; plain pathspecs are case-sensitive even under `core.ignorecase`) and a match is confirmed by NFC spelling (git on macOS reports precomposed names) or file identity (the index's `Demo/x` *is* `demo/x` on a case-insensitive filesystem); when git cannot answer (missing, timeout, "dubious ownership", non-zero exit) inside a git work tree (a `.git` at or above the repo root) every orphan is kept — the check fails closed. Every other orphan stays engine-owned: carried into the lockfile stamped in step 8 (orphans are settled just before stamping). With `commit = false` (the default) kept orphans are also listed in the managed block until they are gone, so leftover output never becomes committable: write the root-anchored paths of everything rendered plus the kept orphans into the managed block of the consumer's `.gitignore`, and ask git (read-only) whether any of them is still tracked and, if so, warn with the exact `git rm -r --cached -- …` to run. With `commit = true` remove the managed block and list the kept orphans on stderr — committed output is normally tracked, so a removed skill's committed files stay until the user deletes them (`git rm`). `.gitignore` is a user file: it is never hashed into the lockfile and never part of the written set.
Eval tasks (Section 6.5) are intentionally **not** part of the sync flow. They live in engine and overlay packages, are read at validation time (`playbook validate`) and enumeration time (`playbook eval --list`), and v2 will read them at runner time — but they never produce files in the consumer repo. They are authoring-side artifacts, not deliverables.
### 4.3 Key design choices, recapped
- **Copies, not symlinks.** Cross-platform, banking-friendly, git-friendly.
- **Jinja sparingly.** Variable substitution and conditional file selection only. Avoid `{% if %}` inside rule bodies — makes templates unreadable.
- **Sentinel headers.** Every generated file begins with `# AUTOGENERATED — edit in coding-agent-playbook, run 'playbook sync'`.
- **Detector facts are cached.** Written into `.coding-agent-playbook.toml` at init. Refreshed automatically when `pyproject.toml` mtime changes, or manually via `playbook check --refresh`.
- **`AGENTS.md` is always generated.** Even if no adapters are enabled. It is the lowest-common-denominator output and costs nothing.
- **Generated output is local-only by default.** Rendered files are build products of the installed engine + overlays + `playbook/`, so (with `[output] commit = false`) they are gitignored through an engine-owned managed block and regenerated on each machine by the `post-checkout`/`post-merge` hook — the committed source of truth is the config and `playbook/`, not the rendered copies.
## 5. Repository layout
### 5.1 The engine repo (`coding-agent-playbook`)
```
coding-agent-playbook/
├── pyproject.toml
├── README.md
├── SPEC.md                                 # this file
├── CHANGELOG.md
├── .pre-commit-hooks.yaml                  # exposes hooks to consumers
├── src/coding_agent_playbook/
│   ├── __init__.py
│   ├── cli.py                              # `playbook` entrypoint
│   ├── types.py                            # Rule, Prompt, Skill dataclasses (Section 6.6)
│   ├── config.py                           # .toml loading + merge
│   ├── detector.py                         # facts dictionary
│   ├── renderer.py                         # Jinja2 environment
│   ├── overlays.py                         # overlay resolution
│   ├── lockfile.py                         # .coding-agent-playbook.lock
│   ├── gitignore.py                        # managed .gitignore block ([output] commit = false)
│   ├── git_client.py                       # GitClient protocol: read-only tracked/staged queries
│   ├── _file_identity.py                   # FileSet: stale-vs-written by file identity (§4.2 step 9)
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py                         # Adapter ABC
│   │   ├── _skill_writer.py                # shared native SkillWriter (Section 10.8)
│   │   ├── _prior_output.py                # previous lockfile as proof of engine-written files
│   │   ├── continue_adapter.py
│   │   ├── claude_code_adapter.py
│   │   ├── opencode_adapter.py
│   │   ├── shared_skills_adapter.py        # cross-agent shared_skills/ hub
│   │   └── agents_md_adapter.py
│   ├── sources/                            # storage abstraction (see Section 20)
│   │   ├── __init__.py
│   │   ├── base.py                         # ArtifactSource + StateSource ABCs
│   │   └── filesystem.py                   # v1: filesystem implementations (active)
│   ├── evals/                              # v1: task schema active; v2: runner placeholder
│   │   ├── __init__.py
│   │   ├── task.py                         # v1: EvalTask + dataclasses (active)
│   │   ├── loader.py                       # v1: walks resources/eval_tasks/ (active)
│   │   ├── validator.py                    # v1: cross-reference checks (active)
│   │   ├── runner.py                       # v2: HarnessRunner ABC (placeholder)
│   │   └── judge.py                        # v2: Judge ABC (placeholder)
│   ├── packs/                              # bundled opt-in content packs (Section 11.5)
│   │   ├── __init__.py
│   │   └── superpowers/                    # vendored Superpowers skills; off by default
│   │       ├── __init__.py                 # PACK_NAME = "coding_agent_playbook.packs.superpowers"
│   │       ├── LICENSE                     # upstream MIT notice (ships with every copy)
│   │       ├── ATTRIBUTIONS.md             # source, version, indication of changes
│   │       └── resources/skills/<id>/      # 15 skills: SKILL.md + scripts/ + references/
│   └── resources/
│       ├── rules/
│       │   ├── always/
│       │   │   ├── 00-project-context.md.j2    # uses {{ project_name }}
│       │   │   ├── 10-python-house-style.md    # plain markdown, no vars
│       │   │   └── 20-tooling-baseline.md.j2   # branches on dev_tools
│       │   ├── languages/python/
│       │   │   ├── typing.md.j2                # branches on python_version
│       │   │   ├── error-handling.md           # plain markdown
│       │   │   └── logging.md                  # plain markdown
│       │   ├── frameworks/
│       │   │   ├── fastapi.md                  # plain markdown
│       │   │   ├── pydantic-v2.md              # plain markdown
│       │   │   ├── sqlalchemy-v2.md            # plain markdown
│       │   │   └── pytest.md.j2                # branches on pytest-asyncio
│       │   └── ml/
│       │       ├── notebooks.md                # plain markdown
│       │       └── data-validation.md          # plain markdown
│       ├── prompts/
│       │   ├── refactor.md                     # plain markdown
│       │   ├── generate-tests.md.j2            # branches + includes_rules
│       │   ├── tdd-cycle.md.j2                 # includes_rules
│       │   ├── review.md.j2                    # includes_rules
│       │   ├── docstrings.md.j2                # uses {{ docstring_style }}
│       │   ├── explain.md                      # plain markdown
│       │   └── spec.md                         # plain markdown
│       ├── skills/
│       │   └── (empty in v1; native via the skill adapters)
│       ├── eval_tasks/
│       │   ├── generate-tests-happy-path/
│       │   │   ├── task.toml
│       │   │   ├── setup/
│       │   │   │   └── src/calculator.py
│       │   │   └── expected/
│       │   ├── generate-tests-edge-cases/
│       │   │   └── ...
│       │   └── refactor-extract-helper/
│       │       └── ...
│       └── precommit/
│           └── config.yaml.j2              # starter .pre-commit-config.yaml (air-gapped: repo: local)
├── tests/
│   ├── unit/
│   │   ├── test_detector.py
│   │   ├── test_renderer.py
│   │   ├── test_overlays.py
│   │   ├── test_eval_tasks.py
│   │   ├── test_sources.py
│   │   ├── test_types.py
│   │   └── test_lockfile.py
│   ├── adapters/
│   │   ├── test_continue.py
│   │   ├── test_claude_code.py
│   │   ├── test_opencode.py
│   │   └── test_agents_md.py
│   ├── integration/
│   │   └── test_end_to_end.py              # fake consumer repo, full sync
│   └── fixtures/
│       ├── repos/                          # synthetic consumer repos
│       └── golden/                         # expected adapter outputs
└── docs/
    ├── getting-started.md
    ├── authoring-rules.md
    ├── authoring-overlays.md
    └── adapter-contract.md
```
### 5.2 An overlay repo (`playbook-rules-bnp`)
Overlays are minimal — they ship only their additional content. They depend on the engine for the renderer, adapters, and CLI.
```
playbook-rules-bnp/
├── pyproject.toml                          # depends on coding-agent-playbook>=0.4
├── README.md
└── src/playbook_rules_bnp/
    ├── __init__.py                         # registers entry point
    └── resources/
        ├── rules/
        │   ├── always/
        │   │   └── 30-bnp-banking.md       # plain markdown
        │   ├── compliance/
        │   │   ├── pii-handling.md         # plain markdown
        │   │   ├── dependency-allowlist.md.j2  # iterates allowlist from config
        │   │   └── audit-logging.md        # plain markdown
        │   └── infra/
        │       ├── litellm-routing.md.j2   # uses {{ litellm_base_url }}
        │       └── air-gapped-net.md       # plain markdown
        └── prompts/
            ├── pii-scan.md.j2              # includes_rules: [pii-handling]
            └── compliance-review.md.j2     # includes_rules: [...]
```
The overlay registers itself via an entry point in its `pyproject.toml`:
```toml
[project.entry-points."coding_agent_playbook.overlays"]
bnp = "playbook_rules_bnp:OVERLAY"
```
The engine discovers all installed overlays via `importlib.metadata.entry_points`.
### 5.3 A consumer repo after `playbook init`
```
risk-models/                                # the user's project
├── pyproject.toml                          # already there; deps added by init
├── .coding-agent-playbook.toml             # committed ([output] commit = false)
├── .coding-agent-playbook.local.toml       # gitignored
├── .coding-agent-playbook.lock             # gitignored (managed block); drift detection
├── .pre-commit-config.yaml                 # committed; auto-sync + staged-output guard
├── .gitignore                              # committed; .local.toml + the managed block
├── AGENTS.md                               # AUTOGENERATED, gitignored
├── .continue/
│   ├── rules/
│   │   ├── 00-project-context.md           # AUTOGENERATED
│   │   ├── 10-python-house-style.md
│   │   ├── 20-tooling-baseline.md
│   │   ├── 30-bnp-banking.md               # from overlay
│   │   ├── 50-python-typing.md
│   │   ├── 60-fastapi.md                   # only because fastapi detected
│   │   └── 70-pydantic-v2.md
│   └── prompts/
│       ├── refactor.md
│       ├── generate-tests.md
│       ├── review.md
│       └── explain.md
├── .claude/
│   ├── CLAUDE.md                           # AUTOGENERATED
│   ├── commands/
│   │   ├── refactor.md
│   │   ├── generate-tests.md
│   │   ├── review.md
│   │   └── explain.md
│   └── skills/                             # AUTOGENERATED — Claude Code native skills
│       └── query-db/
│           ├── SKILL.md
│           └── scripts/run.py
├── .opencode/
│   ├── command/                            # AUTOGENERATED — OpenCode slash commands
│   │   ├── refactor.md
│   │   ├── generate-tests.md
│   │   ├── review.md
│   │   └── explain.md
│   └── skills/                             # AUTOGENERATED — OpenCode native skills
│       └── query-db/                       #   (byte-identical to .claude/skills/query-db/)
├── shared_skills/                          # AUTOGENERATED — cross-agent skills hub (Section 10.8)
│   └── query-db/                           #   (byte-identical to .claude/skills/query-db/)
└── playbook/                               # OPTIONAL: per-repo customizations
    ├── rules/
    │   └── risk-models-specific.md.j2
    └── skills/
        └── query-db/                       # canonical skill source (SKILL.md with `id: query-db` + scripts/)
```
Everything marked AUTOGENERATED carries the sentinel and is owned by `playbook sync` (a `SKILL.md` carries it as its first body line, since its frontmatter must stay on line 1; the files the engine writes into a skill directory are owned through that `SKILL.md` and the lockfile — a file a user adds to a generated skill directory stays the user's and is never deleted, §4.2 step 9). The user owns `.coding-agent-playbook.toml`, `.coding-agent-playbook.local.toml`, anything under `playbook/`, their own source code, and any hand-written skill directory (no sentinel) under the three skill roots — a canonical skill whose `id` collides with one is skipped for that root with a warning (Section 10.8). The output directory name is the skill's `id:` frontmatter value, not the source folder name (Section 6.3).
**Generated output is local-only (default `[output] commit = false`, §7.1).** `AGENTS.md`, `.continue/`, `.claude/CLAUDE.md`, `.claude/commands/`, `.claude/skills/<id>/`, `.opencode/command/`, `.opencode/skills/<id>/`, `shared_skills/<id>/` and the lockfile are **not committed**: `playbook sync` lists them in an engine-owned block of the repo's `.gitignore`, and every clone regenerates them locally (the `post-checkout`/`post-merge` hook runs `playbook sync`; run it once by hand right after cloning). The `.gitignore` itself, including that block, *is* committed so every checkout ignores the same paths:
```gitignore
.coding-agent-playbook.local.toml

# >>> coding-agent-playbook (managed — do not edit) >>>
/.claude/CLAUDE.md
/.claude/commands/refactor.md
/.claude/skills/review/
/.coding-agent-playbook.lock
/.continue/rules/50-python-typing.md
/.opencode/skills/review/
/AGENTS.md
/shared_skills/review/
# <<< coding-agent-playbook <<<
```
Block rules: entries are root-anchored (relative to the playbook repo root, where the `.gitignore` lives), sorted and de-duplicated, one per generated **file** — except that every file inside a generated skill directory (any directory holding a written `SKILL.md`, whatever adapter root it sits under) collapses to one `/<dir>/` entry. Glob metacharacters (`*`, `?`, `[`, `!`, `#`, `\`, leading/trailing spaces) are backslash-escaped so names match literally. Entries are Unicode-NFC-normalised (git on macOS reports precomposed paths and never normalises patterns); a name written in another form (NFD) gets a second entry in that form for Linux checkouts. Leftover output from an earlier sync that is still engine-owned (§4.2 step 9) stays in the block. The block is replaced in place (or appended after one blank line, creating `.gitignore` if needed); every byte outside it — CRLF endings, a missing final newline, a UTF-8 BOM before a first-line block — is preserved, the write is atomic (a uniquely named temp file + `os.replace`, never a fixed name that could clobber a user file), and re-running is a no-op. A start marker without an end marker, an orphan end marker, or a duplicated block is an error naming the file and line; the engine never guesses and never clobbers. With `[output] commit = true` the block is removed and the generated files are committed as before v0.16.
Note one deliberate non-duplication for OpenCode, and one deliberate duplication:
- **No `.opencode/rules/` directory.** OpenCode reads `AGENTS.md` natively as its primary rules source, walking up the directory tree. The universal AGENTS.md adapter is OpenCode's rule-delivery path. Writing a separate `.opencode/rules/` would just duplicate content OpenCode is already reading from `AGENTS.md`.
- **`.opencode/skills/` is written natively.** The OpenCode adapter emits its own skill tree so OpenCode works without the Claude Code adapter enabled. OpenCode also scans `.claude/skills/`; the duplicate is harmless because OpenCode keys discovered skills by name in a map (last wins) and both copies are byte-identical (§10.6).
The user's own `.opencode/agent/` (custom agents) and `.opencode/plugin/` (lifecycle hooks) directories, plus `opencode.json` (MCP servers, permissions, model selection), are owned by the user and not touched by the engine. See Section 10.6 for the OpenCode adapter's boundaries.
## 6. Canonical artifact model
### 6.0 File formats: `.md` and `.md.j2`
Every artifact — rules, prompts, skills — is a markdown file with YAML frontmatter. The file extension chooses between two processing paths:
- **`.md`** — plain markdown. No Jinja processing. The file is loaded, the frontmatter is parsed, and the body is used verbatim. Use this for the majority of artifacts.
- **`.md.j2`** — Jinja template. The file is loaded, the frontmatter is parsed, and the body is rendered through Jinja2 against the rendering context (facts + user_choices + project metadata). Use this only when the body needs variable substitution, conditionals, or rule inclusion.
The choice is made by the author per file. The renderer dispatches on extension:
```python
def render_artifact_body(template_path: Path, context: dict) -> str:
    if template_path.suffix == ".j2":
        return jinja_env.get_template(str(template_path)).render(**context)
    return template_path.read_text(encoding="utf-8")
```
**Important: frontmatter is always static YAML.** It is parsed by the engine *before* any Jinja rendering happens, because the engine needs to evaluate `applies_if` to decide whether to render the artifact at all. Putting Jinja inside frontmatter would create a chicken-and-egg problem and is rejected by the validator.
**When to use which:**
| Use `.md` when | Use `.md.j2` when |
| --- | --- |
| No variables, no conditionals | You substitute project facts (`{{ project_name }}`, `{{ python_version }}`) |
| The rule is generic across all projects | You branch on detected state (`{% if has_framework("fastapi") %}`) |
| You want the source to be readable as-is in a GitHub preview | You include other rules via `{{ rule("python-typing") }}` |
| Authors prefer not to learn Jinja | You loop over a list (`{% for dep in dependencies %}`) |
A realistic split from the engine's resources:
- `rules/frameworks/fastapi.md` — plain markdown. FastAPI conventions don't depend on project facts.
- `rules/always/00-project-context.md.j2` — needs `{{ project_name }}` and `{{ project_description }}`.
- `rules/languages/python/typing.md.j2` — branches on Python version for PEP 695 syntax.
- `prompts/refactor.md` — plain instructions, no variation needed.
- `prompts/generate-tests.md.j2` — branches on `pytest-asyncio` and project layout choice.
The `.j2` suffix is the author's explicit signal to readers: *"this file has logic in it."* Without it, the file is just markdown.
**Validation.** `playbook validate` checks `.j2` files for Jinja syntax errors and undefined variables. It does not run Jinja against `.md` files — they're treated as static content. This means renaming a file from `.md` to `.md.j2` triggers a stricter check on next validate.
### 6.1 Rules
A canonical rule is a Markdown file (with or without Jinja templating, per Section 6.0) and YAML frontmatter. The frontmatter declares metadata used by the adapters to render harness-specific output; the body is the rule content.
For OpenCode, rules are not written to a separate location — OpenCode reads the universal `AGENTS.md` natively (walking up the directory tree), with `CLAUDE.md` accepted as a fallback. The AGENTS.md adapter is OpenCode's rule-delivery path. No dedicated OpenCode rule directory is generated.
#### 6.1.1 Frontmatter schema
```yaml
id: python-typing                    # required, unique across all overlays
name: Python typing standards        # required, human-readable
description: Type hints everywhere   # required, used by Continue for agentic pull-in
version: 1                           # bump on breaking content change
scope: scoped                        # one of: always | scoped
globs:                               # optional, list. When scope=scoped, these gate inclusion in Continue
  - "**/*.py"
applies_if:                          # optional Python expression evaluated against facts dict
  python_version: ">=3.11"
  has_framework: ["pydantic"]
priority: 50                         # optional, lower = earlier in lex order; default 50
tags: [language, python]             # optional, for filtering
```
#### 6.1.2 Example: `resources/rules/languages/python/typing.md.j2`
```markdown
---
id: python-typing
name: Python typing standards
description: Apply when writing or reviewing Python code with type hints
version: 1
scope: scoped
globs:
  - "**/*.py"
applies_if:
  python_version: ">=3.11"
priority: 50
tags: [language, python]
---
# Python typing standards
Target Python version: {{ python_version }}.
## Always
- All public functions and methods have full type annotations on parameters and return value.
- Use `from __future__ import annotations` at the top of every module that uses forward references.
- Prefer built-in generics over `typing` aliases: `list[int]` not `List[int]`, `dict[str, Any]` not `Dict[str, Any]`.
{%- if python_version >= "3.12" %}
## Python 3.12+ specific
- Use PEP 695 generic syntax for new code: `def first[T](xs: list[T]) -> T: ...`.
- Use the `type` statement for aliases, not `TypeAlias`.
{%- else %}
## Python 3.11
- Use `TypeVar` for generics, `TypeAlias` for aliases.
- Note: PEP 695 generic syntax is not yet available.
{%- endif %}
## Never
- Never use `Any` without a `# type: ignore[misc]` and a comment explaining why.
- Never use bare `Optional[X]` — write `X | None`.
- Never use string forward references unless the cycle is genuinely unavoidable.
## Examples
✅ Good:
```python
from __future__ import annotations
def parse_response(payload: dict[str, object]) -> Response | None:
    ...
```
❌ Bad:
```python
from typing import Dict, Optional


def parse_response(payload: Dict) -> Optional["Response"]: ...
```
```
#### 6.1.3 Rendered output for Continue: `.continue/rules/50-python-typing.md`
```markdown
<!-- AUTOGENERATED by coding-agent-playbook v0.4.0 — edit in source, run 'playbook sync' -->
---
name: Python typing standards
description: Apply when writing or reviewing Python code with type hints
globs:
  - "**/*.py"
alwaysApply: false
---
# Python typing standards
Target Python version: 3.12.
## Always
- All public functions and methods have full type annotations...
[body, fully rendered with Jinja substitutions]
```
#### 6.1.4 Rendered output for Claude Code: section of `.claude/CLAUDE.md`
```markdown
## Python typing standards
*Applies to: `**/*.py`*
Target Python version: 3.12.
### Always
- All public functions and methods have full type annotations...
[body]
---
```
The Claude Code adapter concatenates all rules into a single `CLAUDE.md`, prefacing scoped rules with their globs in italics since CLAUDE.md has no native scoping.
#### 6.1.5 Rendered output for AGENTS.md: section
Same shape as CLAUDE.md but in `AGENTS.md`. Identical content; identical headers.
### 6.2 Prompts
A prompt is a named, invokable instruction. In Continue it becomes a slash command; in Claude Code it lives under `.claude/commands/`.
Prompts can pull rules into their body — this is important enough to warrant a dedicated subsection (6.2.5). The mechanism lets a prompt declare "always include the Python typing rule and the pytest rule in my context when I'm invoked", so the assistant sees those rules even if its globs wouldn't have triggered them.
#### 6.2.1 Frontmatter schema
```yaml
id: generate-tests                   # required
name: Generate tests                 # required
description: Generate pytest tests   # required
version: 1
slash: generate-tests                # the slash command name (Continue, Claude Code, OpenCode)
applies_if:                          # optional
  has_framework: ["pytest"]
input_variables:                     # optional, declared variables filled at invocation
  - name: target
    description: file or function to test
    required: true
includes_rules:                      # optional, rule IDs to inline into the prompt body
  - python-typing
  - pytest
  - python-error-handling
eval_tasks:                          # optional, task IDs that test this prompt (see Section 6.5)
  - generate-tests-happy-path
  - generate-tests-edge-cases
  - generate-tests-async-code
```
#### 6.2.2 Example: `resources/prompts/generate-tests.md.j2`
```markdown
---
id: generate-tests
name: Generate tests
description: Generate pytest tests for the provided code, following the project's testing conventions
version: 1
slash: generate-tests
applies_if:
  has_framework: ["pytest"]
input_variables:
  - name: target
    description: File or function to test
    required: false
includes_rules:
  - python-typing
  - pytest
---
# Task: generate tests
You are writing tests for {{ project_name }}, a {{ project_kind }} project.
## Conventions
- Test framework: pytest{% if "pytest-asyncio" in dev_dependencies %} (with pytest-asyncio for async code){% endif %}.
- Test files live in `tests/`, mirroring the source layout under `src/`.
- One test file per source module: `src/foo/bar.py` → `tests/foo/test_bar.py`.
- Use `parametrize` for table-driven tests. Avoid loops inside test functions.
- Mock external services with `pytest-mock`'s `mocker` fixture. Do not patch globals directly.
{%- if "pydantic" in dependencies %}
- For Pydantic models, prefer constructing real instances over mocking.
{%- endif %}
## Workflow
1. Read the target code carefully. List the branches, edge cases, and error paths.
2. Identify the public surface — only test public functions/methods. Private helpers are tested through their public callers.
3. For each public function, draft tests covering:
   - happy path
   - each branch identified above
   - each error path
   - boundary values (empty input, max size, None where allowed)
4. Run the tests. If any fail because the code has bugs, **report them; do not silently fix the code**. The user decides whether to fix the code or adjust the test.
5. Report coverage of the public surface.
## Output format
Produce one or more test files in the correct location. After writing, run `pytest -q tests/<path>` and report the result.
## Reference rules
The following project rules apply to anything you write. Follow them strictly.
{{ rule("python-typing") }}
{{ rule("pytest") }}
```
Two mechanisms are at play here:
1. The `includes_rules:` frontmatter declares the prompt's rule dependencies *for tooling purposes* — `playbook check` can show them, `playbook validate` errors if a referenced rule doesn't exist, and adapters use the list to decide what to render where.
2. The `{{ rule("python-typing") }}` Jinja call inlines the rule's body at a specific point in the prompt. The author controls exactly where the rule content appears.
The two are complementary — `includes_rules:` is the declaration, `{{ rule() }}` is the placement. They are validated against each other: every rule referenced by `{{ rule() }}` must also be listed in `includes_rules:`, and vice versa, or `playbook validate` fails. This is a deliberate guardrail — implicit imports cause invisible coupling.
#### 6.2.3 Rendered output for Continue: `.continue/prompts/generate-tests.md`
```markdown
<!-- AUTOGENERATED by coding-agent-playbook v0.4.0 — edit in source, run 'playbook sync' -->
---
name: Generate tests
description: Generate pytest tests for the provided code, following the project's testing conventions
invokable: true
---
# Task: generate tests
You are writing tests for risk-models, a python-application project.
[rest of body, fully rendered]
## Reference rules
The following project rules apply to anything you write. Follow them strictly.
### Python typing standards
Target Python version: 3.12.
[full body of python-typing rule, inlined verbatim]
### Pytest conventions
[full body of pytest rule, inlined verbatim]
```
The user types `/generate-tests` in the Continue panel and the rendered prompt — including the inlined rule bodies — becomes the system instruction for the turn.
#### 6.2.4 Rendered output for Claude Code: `.claude/commands/generate-tests.md`
Same body, no top-level frontmatter — Claude Code commands are pure markdown. Invoked via `/generate-tests`. The inlined rules appear in the command body just like in Continue.
#### 6.2.5 Rule inclusion in prompts — full design
Why this exists. Continue's `alwaysApply: false` rules rely on the agent reading rule descriptions and *deciding* to pull them in. That works for some rules, but for an authoritative slash command like `/generate-tests`, the team usually wants stronger guarantees: *"every time this is invoked, the typing rule and the pytest rule are in context, no matter what."* `includes_rules:` provides that guarantee.
Three APIs are available to the prompt author:
**1. Frontmatter declaration: `includes_rules:`**
Lists rule IDs the prompt depends on. Required if `{{ rule() }}` is used in the body. Validated against the rule registry — references to missing or filtered-out rules error at `playbook validate` time.
```yaml
includes_rules:
  - python-typing
  - pytest
```
**2. Inline reference: `{{ rule("rule-id") }}`**
A Jinja helper that expands to the body of the named rule, with the rule's own frontmatter stripped and a `### {rule.name}` header prepended. Used to place rule content at a specific point in the prompt body. Only available in `.md.j2` files (since it requires Jinja).
```markdown
## Reference rules
{{ rule("python-typing") }}
{{ rule("pytest") }}
```
**3. Implicit appendix (when `{{ rule() }}` is not used)**
If a prompt declares `includes_rules:` but the body never calls `{{ rule() }}`, the adapter automatically appends a "Reference rules" section to the rendered output, listing each rule. This is the path for `.md` (plain markdown) prompts that want to declare dependencies without learning Jinja:
```markdown
---
id: refactor
includes_rules:
  - python-typing
---
# Task: refactor
[plain markdown body, no Jinja]
```
Rendered output gets a generated appendix:
```markdown
# Task: refactor
[body]
## Reference rules
### Python typing standards
[full body]
```
This means plain `.md` prompts can still benefit from rule inclusion without templating — the appendix is generated by the adapter, not by Jinja. Authors who want fine-grained control over rule placement use `.md.j2` with `{{ rule() }}`.
**Resolution semantics.**
Rule inclusion happens after overlay resolution. If `python-typing` is overridden by the BNP overlay, the prompt gets the *overridden* version. This is intentional — prompts depend on rule IDs, not on the original engine content. An overlay author who improves a rule automatically improves every prompt that includes it.
**Filtered rules.**
If a referenced rule has an `applies_if` that evaluates to false for the current repo (e.g., `pydantic` rule, but no pydantic installed), the rule is silently omitted from the prompt's appendix. The prompt itself can still be applicable — only the referenced rule drops out. `playbook validate` does NOT error here, because the omission is a feature, not a misconfiguration.
**Recursive inclusion is forbidden.**
A rule cannot itself reference other rules via `includes_rules:`. Only prompts have `includes_rules:`. This keeps the dependency graph one level deep and trivially analyzable. If a rule needs to reference content from another rule, the author should either (a) duplicate the relevant fragment, or (b) refactor both rules to share a common third rule, kept in `rules/shared/`. The validator enforces this.
**Tooling support.**
- `playbook check` shows, for each prompt, which rules it includes.
- `playbook render <prompt-id> --show-rules` prints the resolved rule list.
- `playbook validate` errors if `{{ rule("X") }}` references a rule not in `includes_rules:`, or if `includes_rules:` lists a rule never referenced via `{{ rule() }}` (only in `.md.j2` files — plain `.md` prompts don't need to call `{{ rule() }}`).
**Why not let rules be included by globs too?**
A natural follow-on idea: a prompt declares `includes_rules_matching: { tags: ["python", "testing"] }` and the engine picks up all matching rules. Rejected for v1 because it makes the rendered prompt non-deterministic from a glance at the source — you need to mentally execute the matcher against the current rule registry. Explicit lists are uglier but trivially readable. Revisit in v2 if the explicit lists become unwieldy.
### 6.3 Skills
Skills follow the **Agent Skills** layout that Claude Code and OpenCode both read natively. The engine's default `resources/` ships none; the engine wheel bundles skills only in the opt-in `superpowers` pack, which is off unless a consumer enables it (Section 11.5). Overlay packages and repo-local `playbook/skills/<id>/` may ship them today. They are written natively by the `claude_code` (`.claude/skills/`), `opencode` (`.opencode/skills/`) and `shared_skills` (`shared_skills/`) adapters through one shared `SkillWriter` (§10.8), so every copy is byte-identical; the opt-in `agent_harness` adapter writes them natively in its own tree (`skills/<id>/SKILL.md`, §10.7). Adapters that keep the ABC default `write_skill` (Continue) degrade a skill to a prompt (§6.3.2); the rules-only `agents_md` adapter does not emit skills at all.

**Every canonical skill must declare `id:` in its `SKILL.md` frontmatter.** The `id` — not the source folder name — is the overlay merge key (§11), the output directory name (`<root>/<id>/`) and the emitted `name`. A skill without `id:` falls back to the id `skill`, so several id-less skills collapse into one and all but the last are silently dropped; `playbook validate` reports every id-less (or non-string-id) skill (§12.6).

Emitted `SKILL.md` contract (enforced by the `SkillWriter`):
- **`name` = the skill id = the output directory name.** The Agent Skills standard requires `name` to equal the directory name and match `^[a-z0-9]+(-[a-z0-9]+)*$` (1–64 chars); OpenCode silently drops a skill that fails it. The writer always sets `name` to the canonical `id` (an authored display `name` is replaced); every other frontmatter key, including `id`, is kept. A `description` of 1–1024 chars is required. `playbook validate` flags ids that break the pattern and skills without a description (§12.6).
- **Path-safe ids only.** An id containing a path separator, `..`/`.`, NUL, or a drive/absolute prefix is rejected with a `ValueError` naming it — the writer never writes outside its root (and never writes through a symlink that escapes it).
- **Sentinel as the first body line.** Frontmatter must start on line 1 (`^---`) for agent parsers, so the `SENTINEL` is an HTML comment right after the closing fence (the §10.7.3 pattern). A skill directory is engine-owned iff its `SKILL.md` carries the sentinel. Stale files in it are removed only by the lockfile leftover policy (§4.2 step 9) — a file the previous sync wrote that is still pristine and untracked; an edited copy, a tracked file, or a file the user added is kept.
- **Ownership is decided before writing.** If `<root>/<id>/` already exists and is not engine-owned — a hand-written skill dir with a colliding id, a symlink, or a plain file — the writer leaves it untouched and prints a warning instead of overwriting `SKILL.md` (which would turn the user's directory into engine output). Exceptions: an empty directory, and a sentinel-less directory whose `SKILL.md` the previous sync's lockfile lists (the pre-v0.15 `.claude/skills/` output had no sentinel), are claimed.
#### 6.3.1 Schema
A skill is a directory:
```
any-folder-name/                     # the output dir comes from `id:`, not this name
├── SKILL.md.j2                      # the prompt body, with frontmatter (must declare `id:`)
├── scripts/                         # optional, bundled scripts the skill can call
│   └── helper.py
└── references/                      # optional, additional context
    └── reference.md
```
#### 6.3.2 Degradation rule
When the Continue adapter encounters a skill, it:
1. Renders `SKILL.md.j2` as a prompt with `invokable: true`.
2. Copies the `scripts/` directory to `.coding-agent-playbook/skills/<skill-id>/scripts/` (a known location the prompt body can reference).
3. Inlines a note in the prompt: *"Helper scripts are available at `.coding-agent-playbook/skills/<skill-id>/scripts/`. You can read them if useful."*
This is graceful — the user loses the auto-discovery of skills but keeps the content and the scripts.
As implemented, only step 1 happens: `Adapter.write_skill` degrades through `Skill.to_prompt`, so neither `scripts/` nor `references/` reaches Continue, and no note is added (Section 11.5.1).
### 6.4 The `applies_if` predicate
`applies_if` is a small DSL that gates artifact inclusion. It is intentionally restricted to a handful of operators to keep it auditable; arbitrary Python is not allowed.
```yaml
applies_if:
  python_version: ">=3.11"           # comparison against detector facts
  has_framework: ["fastapi"]         # all of these must be present in facts["frameworks"]
  any_framework: ["pytest", "unittest"]  # at least one must be present in facts["frameworks"]
  has_ml_stack: ["torch", "numpy"]   # all of these must be present in facts["ml_stack"]
  any_ml_stack: ["torch", "tensorflow"]  # at least one must be present in facts["ml_stack"]
  has_file: ["Dockerfile"]           # file must exist in repo root
  banking_mode: true                 # boolean facts
```
Multiple keys are ANDed together. The evaluator lives in `coding_agent_playbook.detector.evaluate_predicate(predicate, facts) -> bool`.
The framework operators (`has_framework`, `any_framework`) read `facts["frameworks"]`; the ML-stack operators (`has_ml_stack`, `any_ml_stack`) read the separate `facts["ml_stack"]` fact (torch, tensorflow, scikit-learn, … — see Section 8.2). Use the ML-stack operators to gate ML-specific rules and prompts, since ML libraries never appear in `frameworks`.
Note that `has_framework` appears in two distinct places with different shapes — once as a predicate key here (taking a list of required framework names), and once as a Jinja helper in the rendering context (taking a single framework name and returning a bool, see Section 9.4). The same split applies to the ML stack: `has_ml_stack`/`any_ml_stack` are `applies_if:` predicate keys (lists), while `has_ml_dep("torch")` is the Jinja callable (single name) used inside `{% if %}`. They share concepts but live at different evaluation layers (frontmatter is parsed before Jinja runs). When reading or writing artifacts, the rule is: lists in `applies_if:`, callables inside `{% if %}`.
### 6.5 Eval tasks (Tier 0: schema only, no runner)
Eval tasks are reproducible test cases associated with prompts. Each task captures: *"given this starting state and this invocation, here's what success looks like for this prompt."* In v1 only the **schema and validation** ship — there is no `playbook eval` runner, no LLM-as-judge, no scoring. Authors write tasks alongside the prompts they create; the tasks accumulate as institutional knowledge and become the input to the runner in v2.
This is what the spec means by "forward-compatible eval abstractions" (G6). Section 15 gives the runtime-side ABCs that v2 will implement; this section defines the authoring-side artifact format that v1 ships.
#### 6.5.1 Why ship the schema before the runner
Three reasons:
1. **Tasks are documentation.** A well-written task tells future authors what the prompt is for, what good output looks like, and what edge cases the prompt is expected to handle. That value exists with zero tooling — it lives in source review.
2. **Lock the format early.** If the schema lands in v1, every prompt added in v1 ships with eval tasks from day one. When v2's runner arrives, there's a corpus to run against. If the schema lands in v2, prompts written in v1 retroactively need tasks added, which never happens.
3. **`playbook validate` can already enforce hygiene.** Even without a runner, the engine can check that every `eval_tasks:` reference resolves, that no orphan tasks exist, and that task `setup/` files are present. This catches breakage at commit time.
#### 6.5.2 Directory layout
Eval tasks live alongside rules and prompts in the engine resources, with the same overlay semantics:
```
src/coding_agent_playbook/resources/
├── rules/
├── prompts/
└── eval_tasks/
    ├── generate-tests-happy-path/
    │   ├── task.toml                 # task metadata + the gate/rubric/verdict layers
    │   └── setup/                    # files written to scratch repo before invocation
    │       └── src/calculator.py
    ├── generate-tests-edge-cases/
    │   └── ...
    └── refactor-extract-helper/
        └── ...
```
Each task is a directory, not a single file, because tasks need fixture files (the `setup/` tree). The success criteria live inline in `task.toml` (the `[gate]`/`[rubric]` layers), not as separate golden-file fragments. Mirrors the skills pattern (Section 6.3).
Overlay packages can ship their own `eval_tasks/` directory and the merge semantics are the same as for rules and prompts — later layers override earlier ones by task ID. A BNP overlay can override `generate-tests-happy-path` with a banking-flavored variant that includes the BNP rule pack.
#### 6.5.3 The `task.toml` schema
```toml
# resources/eval_tasks/generate-tests-happy-path/task.toml
id = "generate-tests-happy-path"
prompt_id = "generate-tests"            # required; back-reference to the prompt
description = "Generate tests for a simple pure function with no edge cases"
version = 1
[setup]
# Files in the setup/ subdirectory that get copied into the scratch repo
# before invocation. Listed for documentation; the runner walks setup/ itself.
files = ["src/calculator.py"]
# Mock project facts the detector should report for this task.
# Lets framework-conditional prompts be evaluated without depending on
# the eval-runner's own environment.
project_kind = "python-application"
python_version = "3.12"
frameworks = ["pytest", "pytest-asyncio"]
[invocation]
# The arguments / free text the user "types" after the slash command.
prompt_args = "for the add function in src/calculator.py"
# Values for the prompt's declared input_variables.
input_variables = { target = "src/calculator.py::add" }

# --- The DETERMINISTIC layer: a boolean expression over named handles. ---
[gate]
expr = "test_created and names_test and parametrized and src_unchanged"
[gate.bind]
# A handle is a group | a standalone check | a {ref="<gate>"}. File predicates,
# metric thresholds, and non-regression checks all live here. Thresholds are 0-1.
test_created  = { check = "file_exists",    path = "tests/test_calculator.py" }
names_test    = { check = "file_contains",  path = "tests/test_calculator.py", pattern = "def test_add" }
parametrized  = { check = "file_contains",  path = "tests/test_calculator.py", pattern = "parametrize" }
src_unchanged = { check = "file_unchanged", path = "src/calculator.py" }
# A metric threshold/non-regression handle (0-1 normalized cutoffs):
#   cc  = { check = "threshold",      metric = "cyclomatic_complexity", fail = 0.5 }
#   cov = { check = "non_regression", metric = "coverage",              max_worsening = 0.0 }

# --- The LLM-JUDGE layer: a weighted rubric, thresholded to a boolean. ---
[rubric]
expr = "quality"
[rubric.bind]
# A `rubric` group is a weighted set of judge criteria (weights sum to 1.0),
# thresholded into a boolean by `fail` (a 0-1 cutoff on the rubric composite).
quality = { fail = 0.5, rubric = [
  { judge = "Tests use pytest.parametrize for table-driven cases", weight = 0.2 },
  { judge = "Test file lives at tests/test_calculator.py (mirror layout)", weight = 0.2 },
  { judge = "All public branches of `add` are covered", weight = 0.4 },
  { judge = "No mocking is used (the function is pure)", weight = 0.2 },
] }
# A standalone judged non-regression handle is also valid (a judge criterion IS a metric):
#   no_drop = { check = "non_regression", judge = "overall quality", max_worsening = 0.1 }

# --- The trial verdict: a boolean expression over the two layers (default below). ---
[verdict]
trial = "gate and rubric"

# --- OPTIONAL cross-trial reliability layer; omit ⇒ a single trial. ---
# [aggregate]
# expr = "reliable"
# [aggregate.bind]
# reliable = { metric = "pass_at_k", k = 5, over = "verdict", fail = 0.9 }
```
Field-by-field:
| Field | Required | Purpose |
| --- | --- | --- |
| `id` | yes | Unique across all overlays. |
| `prompt_id` | yes | Back-reference to the prompt this task tests. Must appear in that prompt's `eval_tasks:` list. |
| `description` | yes | One-sentence summary, shown in `playbook eval --list`. |
| `version` | no | Bump on breaking changes to setup/checks. |
| `[setup]` | yes | Mock facts and `setup/` directory listing. |
| `[invocation]` | yes | What the user "types" — prompt arguments and variable bindings. |
| `[gate]` | no¹ | Deterministic boolean layer: `bind` (named handles) + `expr` (a boolean expression over them). Handles are file/metric `check`s, composed boolean groups, or a `{ref="<gate>"}`. |
| `[rubric]` | no¹ | LLM-judge weighted layer: same `bind`+`expr` shape; a `rubric` group is a weighted set of judge criteria thresholded to a boolean. |
| `[verdict]` | no | `trial` is a boolean expression over `gate`/`rubric` (default `"gate and rubric"`) deriving the per-trial verdict. |
| `[aggregate]` | no | Cross-trial reliability: same `bind`+`expr` shape over `pass_at_k`/`pass_pow_k`. Omit ⇒ a single trial. |

¹ A task must declare **at least one** of `[gate]` / `[rubric]` (a task with neither does not measure anything). All thresholds are **0–1 normalized** (every metric owns a `Normalizer`, §21); there is **no `[expected]` block** — file predicates are gate `check`s (`file_exists`/`file_contains`/`file_unchanged`/`file_forbidden`). The compiler (`evals/_compile.py`) turns the layer blocks into one per-trial `Rubric` of checks + a derived-verdict AST; the validator only enforces structural correctness (it trial-compiles the blocks).
#### 6.5.4 Authoring discipline
Recommended (not enforced, since this is conventions over rules):
- **Three tasks per prompt minimum.** One happy-path, one edge-case, one regression target. Adding a fourth means the prompt is genuinely complex; if you can't find a fourth, the prompt is probably fine.
- **Task IDs follow `<prompt-id>-<scenario>`.** Predictable, sortable, makes `playbook eval --list` readable.
- **Gate checks are cheap, rubric criteria are precious.** Every `[gate]` file/metric check is deterministic and free to run forever. `[rubric]` judge criteria cost LLM tokens, so reserve them for things that genuinely can't be checked deterministically. *"Tests use parametrize"* → a `[gate]` `file_contains` check. *"Tests cover all public branches"* → a `[rubric]` judge criterion.
- **Don't test the model; test the prompt.** If a task fails because Claude 4.6 is dumber than Claude 4.7, that's not your prompt regressing. Tasks should target things the prompt itself controls: layout, conventions, what gets imported, what doesn't.
#### 6.5.5 `eval_tasks:` validation in `playbook validate`
Two new validation rules ship in v1:
1. **Every `eval_tasks:` reference resolves to a real task.** If a prompt declares `eval_tasks: [foo, bar]` but `eval_tasks/bar/` doesn't exist, error.
2. **Every task's `prompt_id` points back to a prompt that lists it.** Bi-directional check, same shape as `includes_rules` / `{{ rule() }}` symmetry. Catches orphan tasks where someone deleted the prompt but left the task behind, or where a task was renamed and a prompt's frontmatter wasn't updated.
`playbook validate` does **not** run the agent — it only trial-compiles the layer blocks and checks cross-references, so a malformed `[gate]`/`[rubric]` handle or an `expr` referencing an unknown handle is caught at commit time, but whether the gate checks *hold* against real agent output requires `playbook eval --run`.
#### 6.5.6 What runs at validate-time vs run-time
| Capability | `playbook validate` | `playbook eval --run` |
| --- | --- | --- |
| Author `eval_tasks/` directories | yes | yes |
| `task.toml` schema + trial-compile validation | yes | yes |
| `playbook validate` cross-reference checks | yes | — |
| `playbook eval --list` (read-only enumeration) | yes | yes |
| Run the agent + grade the `[gate]` checks against its output | no | yes |
| LLM-as-judge for the `[rubric]` layer | no | yes (opt-in via `--judge`) |
| Per-runner eval (`--runner claude_code` / `opencode`) | no | yes |
Validation stays cheap: it ships as schema + trial-compile + cross-reference checks, with the actual execution behind `--run`. Section 15 carries the matching execution abstractions (`HarnessRunner`, `EvaluationReport`, and the `Metric`/`Check`/`Rubric` scoring model of §21), live since v1.1.
### 6.6 Canonical types and serialization
This section codifies a distinction that has been implicit throughout the spec and makes it explicit: there are **two** formats in this system, and they serve different audiences.
**The authoring format** is markdown + YAML frontmatter (`.md` or `.md.j2`). It is what humans write, what gets reviewed in PRs, what lives in `resources/` directories. It never changes. Authors at every level — engine maintainers, overlay authors, repo-local customizers — write exclusively in this format.
**The canonical internal format** is a set of typed Python dataclasses: `Rule`, `Prompt`, `Skill`, `EvalTask`. These are what the engine operates on internally between parse-time and adapter-time. Adapters consume these objects, not markdown. The renderer produces these objects. The validator type-checks these objects.
The two formats round-trip exactly: `Rule.from_markdown(rule.to_markdown())` is the identity. The dataclasses also serialize to JSON via `to_dict()` / `from_dict()` for alternative storage and transport.
#### 6.6.1 Why this distinction matters
Three reasons to make the canonical types a first-class concern, even though v1's authoring story doesn't need them:
**1. Validation gets precise error locations.** Today's `playbook validate` parses YAML into a dict and conditionally checks fields. With typed dataclasses, validation errors point at the exact field that's wrong — "field `priority` must be int, got 'high'" instead of "something wrong in priority". Pydantic-style messages for free.
**2. Tests get cleaner.** Unit tests for adapters and the renderer can construct `Rule(...)` objects inline instead of writing markdown fixtures to disk and parsing them back. Combined with `InMemoryArtifactSource` (Section 20), the entire engine becomes testable without any filesystem activity.
**3. Alternative deployments get a stable interchange format.** A future hosted product can store rules as JSON in a database or transmit them over HTTP as JSON payloads — operating on the *same* canonical type the OSS engine uses internally. The markdown authoring format is the lossless serialization for humans; the JSON serialization is the lossless serialization for machines. Both produce identical `Rule` objects when parsed.
#### 6.6.2 The canonical types
```python
# coding_agent_playbook/types.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass
class RuleFrontmatter:
    id: str
    name: str
    description: str
    scope: Literal["always", "scoped"]
    version: int = 1
    globs: list[str] = field(default_factory=list)
    applies_if: dict[str, Any] = field(default_factory=dict)
    priority: int = 50
    tags: list[str] = field(default_factory=list)


@dataclass
class Rule:
    frontmatter: RuleFrontmatter
    body: str  # post-Jinja markdown body
    template_body: str  # pre-Jinja source, if needed for re-render
    is_templated: bool  # True if source was .md.j2
    source_path: Path | None  # filesystem origin; None for non-filesystem sources
    source_package: str  # e.g. "coding_agent_playbook", "playbook_rules_bnp"

    @classmethod
    def from_markdown(cls, path: Path, context: dict, source_package: str) -> "Rule": ...
    def to_markdown(self) -> str: ...
    def to_dict(self) -> dict: ...  # JSON-serializable
    @classmethod
    def from_dict(cls, data: dict) -> "Rule": ...


@dataclass
class PromptFrontmatter:
    id: str
    name: str
    description: str
    slash: str
    version: int = 1
    applies_if: dict[str, Any] = field(default_factory=dict)
    input_variables: list[dict] = field(default_factory=list)
    includes_rules: list[str] = field(default_factory=list)
    eval_tasks: list[str] = field(default_factory=list)


@dataclass
class Prompt:
    frontmatter: PromptFrontmatter
    body: str
    template_body: str
    is_templated: bool
    source_path: Path | None
    source_package: str
    # Same from_markdown / to_markdown / to_dict / from_dict shape as Rule.
    ...


@dataclass
class Skill:
    # Agent Skills directory, see Section 6.3
    frontmatter: dict  # SKILL.md frontmatter (open mapping)
    body: str
    scripts_dir: Path | None  # if the skill bundles scripts
    references_dir: Path | None
    source_package: str
    ...


# EvalTask is already defined in Section 15.2 with the same to_dict / from_dict pattern.
```
The fields capture three things every artifact needs:
- **Frontmatter** as a nested dataclass — typed, validated, the "metadata" half.
- **Body content** — both post-Jinja (the final text) and pre-Jinja (the template, for re-rendering with different contexts).
- **Provenance** — where the artifact came from. `source_package` lets the engine answer "is this from the engine, an overlay, or repo-local?" without filesystem inspection. `source_path` is optional because alternative sources (database, HTTP) have no path.
#### 6.6.3 The round-trip contract
```python
# These two are identity transforms:
rule == Rule.from_markdown(Path("rule.md"), context, "pkg").to_markdown_then_back()
rule == Rule.from_dict(rule.to_dict())
# These two produce equivalent rules from different inputs:
Rule.from_markdown(some_path, context, "pkg")
Rule.from_dict(some_dict)
```
Round-trip is **lossless for both directions** for static (`.md`) artifacts. For templated (`.md.j2`) artifacts, the round-trip preserves `template_body` so re-rendering with a new context produces correct output.
The pre-Jinja `template_body` is kept because some operations need it. The OSS engine's `playbook sync` re-renders templates on every run, so it needs the template, not just the last rendered output. The commercial version's hosted registry might store the template once and render per-customer at fetch time — same pattern.
#### 6.6.4 What does NOT live on the canonical type
Equally important is what's deliberately absent:
- **No harness-specific rendering** lives on the type. `Rule.to_continue_rule()` doesn't exist. That logic lives in the Continue adapter. The `Rule` type is harness-neutral.
- **No source-specific data** beyond `source_package` and the optional `source_path`. A `Rule` from a database row should be indistinguishable in behavior from a `Rule` from a markdown file.
- **No render context** (the Jinja variables). The render context is supplied at parse-time and consumed; the resulting `Rule` carries only the rendered `body` and (for templated rules) the `template_body`. Two different contexts produce two different `Rule` objects.
#### 6.6.5 What v1 ships
The dataclasses themselves: `coding_agent_playbook/types.py` with the full type definitions and the `from_markdown` / `to_markdown` / `to_dict` / `from_dict` methods. The existing loader becomes a thin wrapper that calls `Rule.from_markdown` per file. Adapters' signatures explicitly typed as taking `Rule`, `Prompt`, `Skill`. The renderer produces these typed objects.
v1 does **not** ship:
- Any non-markdown source of canonical types (no `from_database`, no `from_http`).
- Any non-markdown serialization (the JSON `to_dict` is available, but the OSS engine never writes it to disk — that's a commercial-version concern).
- Any schema versioning beyond the `version: int` field already in frontmatter (per-artifact). Schema evolution at the type level is a v2 concern; v1 commits to the type as defined.
This means v1's `playbook sync` flow is *exactly* what it was before introducing this section — markdown in, markdown out, no JSON anywhere. The types are an internal refactor for clarity and testability. The dual-format story matters for the commercial path; it doesn't change anything user-visible in v1.
#### 6.6.6 The contract for alternative deployments
For implementations beyond the OSS engine, the contract is:
1. **The authoring format never changes.** Any product accepting user-authored rules accepts markdown + YAML frontmatter, byte-compatible with the OSS engine. Customers can paste a rule from OSS into the commercial product and have it work.
2. **The canonical type is the interchange format.** Commercial versions may store, transmit, and operate on `Rule` / `Prompt` / `EvalTask` objects in any serialization (JSON, MessagePack, database rows). The dataclass definition is the schema.
3. **Round-trip remains lossless.** A rule that goes markdown → `Rule` → JSON → `Rule` → markdown produces a markdown file byte-identical to the original (modulo whitespace normalization in the frontmatter YAML).
These three guarantees are what make the OSS engine and a future commercial product *compatible*, not *competitors*. A customer using both should never have to convert formats.
## 7. Configuration files
### 7.1 `.coding-agent-playbook.toml` (committed)
The project's playbook config. Committed to git, reviewed in PRs.
```toml
# .coding-agent-playbook.toml
schema_version = 1
# Top-level keys: TOML puts any key written after a [table] header inside that table.
# Ordered list of overlay packages to merge in.
# Earlier overlays are overridden by later ones on ID collision.
overlays_enabled = ["playbook_rules_bnp"]
# Which adapters render output. AGENTS.md is always generated.
# shared_skills (the cross-agent skills hub, Section 10.8) is on by default; drop it to opt out.
adapters_enabled = ["continue", "claude_code", "opencode", "shared_skills"]
[project]
name = "risk-models"
kind = "python-application"          # or "python-library", "ml-research", "notebook"
description = "Counterparty risk scoring service"
[engine]
version = "0.4.0"                    # engine version this config was generated against
[storage]
# Where artifacts and state come from / go to. See Section 20.
# v1 ships only "filesystem"; future deployments can add others.
artifact_source = "filesystem"
state_source = "filesystem"
[links]
# External-link allowlist for the self-contained-markdown-links rule
# (Section 12.6). Default: [] — no external links in artifacts at all.
# Subdomains of an entry are allowed too.
allowed_domains = ["agentharnesses.io"]
[output]
# Is generated output committed? Default false: everything `playbook sync`
# renders is local-only — gitignored via a managed .gitignore block and
# refused at commit time by `playbook sync --check-staged`. true = legacy:
# output is committed and `playbook sync --check` fails a commit on drift.
commit = false
[detector_cache]
# Cached detector output. Refreshed on pyproject.toml change or `playbook check --refresh`.
python_version = "3.12"
package_manager = "uv"
has_notebooks = false
has_dockerfile = true
[detector_cache.frameworks]
fastapi = "0.115.0"
pydantic = "2.9.2"
sqlalchemy = "2.0.35"
pytest = "8.3.3"
[user_choices]
# Answered during `playbook init`.
docstring_style = "numpy"            # numpy | google | none
test_layout = "tests-mirror"         # tests-mirror | tests-flat | inline
```
**`overlays_enabled` / `adapters_enabled`** are top-level keys holding lists of non-empty strings; they are the only place `Config` reads the enabled overlays and adapters (`playbook init` writes them there). Being top-level, they must sit **above the first `[table]` header**: TOML puts every key written after a header inside that table. Each of the following shapes used to be ignored without a word — read as an empty list, so `playbook sync` exited 0, rendered with only `agents_md`, and settled every other adapter's earlier output as leftovers (§4.2 step 9) — and is now refused with a `config.ConfigError` (a `ValueError`) rather than loaded:
- an `[overlays]` or `[adapters]` table — including the dotted `overlays.enabled = [...]` key, which TOML parses as that table — or any other top-level `overlays`/`adapters` key. The message names the file, quotes the value, and shows the line to write and where, e.g. `.coding-agent-playbook.toml: the [overlays] table is not read (found {'enabled': ['playbook_rules_bnp']}); use the top-level key instead, at the top of the file, above the first [table] header: overlays_enabled = ["playbook_rules_bnp"]`;
- an `overlays_enabled`/`adapters_enabled` key inside any table, at any depth — what replacing an `[overlays]` table with the key *in place* produces (it nests under the table above), as does appending the key to a file that ends with a table (the file `playbook init` writes ends with `[detector_cache.frameworks]`; the local file it writes is `[user_choices]` only). Likewise a nested `overlays`/`adapters` table that holds an `enabled` key (`[engine]` followed by `overlays.enabled = …`). E.g. `.coding-agent-playbook.toml: 'overlays_enabled' in the [detector_cache.frameworks] table is not read (found ['…']) (TOML puts every key written after a [table] header in that table); use the top-level key instead, at the top of the file, above the first [table] header: overlays_enabled = ["…"]`;
- a close misspelling of either key, at any level (`overlay_enabled`, `adapters-enabled`, `enabled_adapters`, compared case-insensitively with `difflib`): `the top-level key 'overlay_enabled' is not read (found […]) (did you mean overlays_enabled?); use the top-level key instead, …`. A plain `overlays`/`adapters` entry inside a table (a framework called `adapters` in `[detector_cache.frameworks]`) is not a mistake and still loads;
- an `overlays_enabled`/`adapters_enabled` value that is not a list of strings (a lone string used to become a list of characters): `overlays_enabled must be a list of strings, got '…'; write overlays_enabled = ["…"]` — or that lists an empty name (`""` used to crash every command inside `importlib`): `overlays_enabled lists an empty name, got ['']; remove the empty entry`.

`config.check_enabled_keys` is the one check: `FileSystemStateSource.load_config` runs it on `.coding-agent-playbook.toml` and on `.coding-agent-playbook.local.toml` separately, before the §7.2 merge, so the error names the file that holds the mistake, and `Config.from_dict` runs it again for other callers. It walks every table of the file (iteratively, so a header nested a thousand levels deep still loads), and every problem in a file is listed in one error. Other unknown keys are still ignored.

Since v0.18 the same per-file pass (`config.check_config_file`, in `config_schema.py` with `ConfigError`) also refuses, in each file on its own: a file `tomllib` cannot read — a syntax error (`error: .coding-agent-playbook.local.toml: invalid TOML: Expected ']' at the end of a table declaration (at line 1, column 14)`), a byte that is not UTF-8, inline arrays/tables nested past Python's recursion limit — each of which was a traceback (exit 1); a top-level `project`, `engine`, `storage`, `output`, `detector_cache` or `user_choices` that is not a table (`error: .coding-agent-playbook.local.toml: [project] must be a table, got 'x'; write name = "<project name>" under the [project] header`), which was a `TypeError`/`AttributeError`/`ValueError` traceback; and a malformed `[output]`. Because each file is checked alone, the error names the file at fault in every command — a local `project = "x"` used to be reported against the committed file by `load_config` — and a committed non-table is refused even when the local file's table replaces it in the merge (the `[user_choices]` local file `init` writes always did), since every teammate without that local file would load it. A missing required key — `schema_version`, `[project] name`/`kind`, `[engine] version` — is a `ConfigError` too (it was a `KeyError` traceback), naming the file, the key and the line to write: `error: .coding-agent-playbook.toml: the required key engine.version is missing; write version = "<engine version>" under the [engine] header`. It is checked on the merged config, so the local file may supply one for `sync` and plain `check`, and it names the committed file, where the key belongs. Every command that loads the config (`sync` in all modes, `check` incl. `--refresh`, `validate`, `render`, `eval`, `init`) loads it first, so a `ConfigError` stops it before it writes or deletes anything: the CLI prints `error: <message>` on stderr and exits 2, like a missing config. `init` checks each existing file on its own, then the config its final sync will load (the planned committed file with the local file merged on top), on a first run too (§12.1). `playbook metrics` parses only its own `[metrics]` table, and `import-harness`/`validate-harness` never read the config, so they do not run this check. An overlay that is listed correctly but cannot be used (its import fails, or it has no `resources/` directory) is a separate, environment-dependent check (§4.2 step 1, §12.4, §12.6).

**`[output] commit`** (`config.OutputConfig`, parsed by `config.parse_output_config`) selects the output policy. An absent table means `false`; `playbook init` always writes the table explicitly so the policy is discoverable; it and `playbook check --refresh` keep the value already in the committed file (a `.local.toml` `[output]` is never written back, §7.2). The value must be a TOML boolean — `commit = "false"` is rejected with a `ConfigError` naming the file and carrying the offending value rather than coerced (`error: .coding-agent-playbook.toml: [output] commit must be a boolean (true or false), got 'false'`, exit 2). What each value implies:

| | `commit = false` (default) | `commit = true` (legacy) |
| --- | --- | --- |
| Generated files + lockfile | gitignored (managed block, §5.3) | committed |
| Write-mode `playbook sync` | applies the managed block; warns about still-tracked output (§12.2) | removes the managed block |
| `playbook sync --check` | file drift **and** a stale/missing block — only meaningful in a working copy that has run `playbook sync` (a fresh clone, e.g. CI, has no output: every file is "missing") | file drift only; suitable for CI |
| `playbook sync --check-staged` | fails when generated output is staged (§12.3.1) | no-op (exit 0) |
| Hooks (§13) | `post-checkout`/`post-merge` auto-sync + staged-output guard | `playbook sync --check` drift check |

The managed block lists what *this* checkout renders (plus still-owned leftovers, §4.2 step 9). A `.local.toml` that narrows `adapters_enabled` (§7.2) therefore narrows the block too — the dropped adapter's pristine output is deleted — and that `.gitignore` change is personal and should not be committed.
### 7.2 `.coding-agent-playbook.local.toml` (gitignored)
Personal, per-engineer overrides. Merged on top of the committed config but never checked in. `playbook init` appends it to `.gitignore`.
```toml
# .coding-agent-playbook.local.toml — DO NOT COMMIT
# I only use Claude Code, skip Continue rendering for my checkout
adapters_enabled = ["claude_code"]   # replaces the committed list (top-level key, above the first [table])
[user_choices]
docstring_style = "google"           # overrides project default for me
```
Merge semantics: deep merge, with `.local.toml` winning — tables merge key by key, while lists and scalars are **replaced**, not merged: a local `adapters_enabled` is the whole adapter list for this checkout. The local file is checked on its own before the merge (§7.1), so an `[adapters]` table there fails with `error: .coding-agent-playbook.local.toml: the [adapters] table is not read …` (exit 2) instead of being ignored. `playbook init` writes the local file as a lone `[user_choices]` header, so add `adapters_enabled` **above** that header: appended below it, the key lands in `[user_choices]` and fails the same way (`'adapters_enabled' in the [user_choices] table is not read …`). The committed config always remains the team's source of truth; local just lets individuals deviate without polluting the repo.

**Invariant: local overrides are read, never written back** (v0.18). The merged config `FileSystemStateSource.load_config()` returns is what every command runs with, and is never saved. `.coding-agent-playbook.toml` has one writer, `FileSystemStateSource.save_config_table` (the `StateSource` method `save_config` wraps it, and no command calls that), called only by `commands/_committed_config.ConfigRewrite.save` — from `playbook init` (§12.1) and `playbook check --refresh` (§12.5). A `ConfigRewrite` is built only in that module, by a `plan_*` function that starts from the committed file alone (`plan_committed_update`, `plan_detector_cache_refresh`) or refuses when one exists (`plan_first_config`, a first `init`'s answers), with the local file never merged in. `tests/unit/test_committed_config.py` walks the engine's AST and fails when another module references a writer, builds a `ConfigRewrite`, or — importing `_committed_config` — references `load_config`; it cannot see a merged config handed to a plan another way (an `update` callback returning `SyncContext.config`), which the `init` and `check --refresh` CLI tests pin by their output. So a local `adapters_enabled`, `overlays_enabled`, `[user_choices]`, `[output]`, `[engine]` or table of any name never reaches the committed file, and a committed file that lacks a required key only the local file supplies is refused by `init` and `check --refresh` (exit 2, nothing written), not completed with it — the commands that only read the merged config (`sync`, plain `check`, …) still run. Nothing rewrites an existing local file: `init` creates it only when it is missing.
### 7.3 `pyproject.toml` entry for the consumer
`playbook init` adds the engine and any chosen overlays as dev dependencies:
```toml
[dependency-groups]
dev = [
    "coding-agent-playbook>=0.4.0,<0.5.0",
    "playbook-rules-bnp>=0.2.0,<0.3.0",
]
```
The engine is pinned to a minor range; the consumer bumps it deliberately. Overlay versions move independently.
## 8. Detector subsystem
### 8.1 Responsibility
Inspect the consumer repo and produce a `facts` dictionary used as the rendering context. Run at init, cached in `.coding-agent-playbook.toml`, refreshed on `pyproject.toml` change or explicit `playbook check --refresh`.
### 8.2 Facts inventory (v1)
| Fact | Type | Source |
| --- | --- | --- |
| `python_version` | `str` (e.g. `"3.12"`) | `pyproject.toml [project] requires-python`, then `python --version` |
| `package_manager` | `Literal["uv", "poetry", "pip-tools", "pip"]` | presence of `uv.lock`, `poetry.lock`, `requirements.txt`, `[tool.poetry]` |
| `dependencies` | `dict[str, str]` (name → version) | `pyproject.toml` + resolved from lockfile |
| `dev_dependencies` | `dict[str, str]` | same, dev group |
| `frameworks` | `dict[str, str]` | subset of dependencies matching a known list (fastapi, pydantic, sqlalchemy, pytest, etc.) |
| `ml_stack` | `dict[str, str]` | subset matching ML deps (torch, transformers, scikit-learn, etc.) |
| `has_notebooks` | `bool` | any `**/*.ipynb` under repo |
| `has_dockerfile` | `bool` | `Dockerfile` exists at root or `./docker/` |
| `has_ci` | `bool` | `.github/workflows/`, `Jenkinsfile`, `.gitlab-ci.yml`, etc. |
| `dev_tools` | `set[str]` | `ruff`, `black`, `flake8`, `mypy`, `pyright` from dev deps + config presence |
| `project_kind` | `Literal[...]` | inferred from layout: presence of `src/`, notebooks, etc. (see 8.3) |
### 8.3 Project-kind inference rule
```
if has_notebooks and not has_src_layout:
    kind = "notebook"
elif has_notebooks and has_src_layout:
    kind = "ml-research"
elif has_src_layout and "fastapi" in frameworks:
    kind = "python-application"
elif has_src_layout:
    kind = "python-library"
else:
    kind = "python-unknown"
```
Tie-breakers can be overridden by the user via `[project] kind` in the config file. The detector never overrides explicit user choice.
### 8.4 Example: detector output
For Max's `risk-models` repo with FastAPI + Pydantic + pytest, the detector returns:
```python
{
    "python_version": "3.12",
    "package_manager": "uv",
    "project_kind": "python-application",
    "dependencies": {
        "fastapi": "0.115.0",
        "pydantic": "2.9.2",
        "sqlalchemy": "2.0.35",
        "httpx": "0.27.2",
    },
    "dev_dependencies": {
        "pytest": "8.3.3",
        "pytest-asyncio": "0.24.0",
        "ruff": "0.8.0",
        "mypy": "1.13.0",
    },
    "frameworks": {
        "fastapi": "0.115.0",
        "pydantic": "2.9.2",
        "sqlalchemy": "2.0.35",
        "pytest": "8.3.3",
    },
    "ml_stack": {},
    "has_notebooks": False,
    "has_dockerfile": True,
    "has_ci": True,
    "dev_tools": {"ruff", "mypy"},
}
```
### 8.5 API
```python
# coding_agent_playbook/detector.py
from pathlib import Path
from typing import TypedDict


class Facts(TypedDict, total=False):
    python_version: str
    package_manager: str
    project_kind: str
    dependencies: dict[str, str]
    dev_dependencies: dict[str, str]
    frameworks: dict[str, str]
    ml_stack: dict[str, str]
    has_notebooks: bool
    has_dockerfile: bool
    has_ci: bool
    dev_tools: set[str]


def detect(repo_root: Path) -> Facts: ...
def evaluate_predicate(predicate: dict, facts: Facts) -> bool: ...
```
## 9. Renderer subsystem
### 9.1 Responsibility
Render canonical templates with the merged context (facts + user_choices + project metadata). Two paths depending on file extension (see Section 6.0): `.md.j2` files go through Jinja2; `.md` files are returned verbatim.
### 9.2 Extension dispatch
```python
# coding_agent_playbook/renderer.py
def render_artifact_body(template_path: Path, context: dict) -> str:
    if template_path.suffix == ".j2":
        return jinja_env.get_template(str(template_path)).render(**context)
    return template_path.read_text(encoding="utf-8")
```
Frontmatter parsing is done by the engine before this call and is always treated as static YAML (no Jinja). Only the body is passed through this dispatch.
### 9.3 Jinja environment
```python
from jinja2 import Environment, FileSystemLoader, StrictUndefined

env = Environment(
    loader=FileSystemLoader([...]),  # engine resources + overlay resources
    autoescape=False,  # markdown, not HTML
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,  # fail loudly on undefined vars
)
```
`StrictUndefined` is important: a typo'd `{{ python_versoin }}` should raise, not silently render as empty. Renders are cheap; failure modes should be loud.
### 9.4 Rendering context
The context passed to every template render:
```python
context = {
    # From detector
    **facts,
    # From config [project]
    "project_name": ...,
    "project_description": ...,
    # From config [user_choices]
    **user_choices,
    # Engine metadata
    "engine_version": "0.4.0",
    "rendered_at": "2026-05-20T10:30:00Z",
    # Convenience predicates
    "has_framework": lambda name: name in facts["frameworks"],
    "has_ml_dep": lambda name: name in facts["ml_stack"],
    # Rule inclusion helper (see Section 6.2.5)
    "rule": lambda rule_id: rule_registry.render_for_inclusion(rule_id),
}
```
### 9.5 The `rule()` Jinja helper
`{{ rule("python-typing") }}` resolves to:
1. Look up `python-typing` in the post-overlay-resolution rule registry.
2. If the rule's `applies_if` evaluates to false against current facts, return an empty string (silent omission — see Section 6.2.5).
3. Otherwise, render the rule's body (recursively dispatched on extension), strip its frontmatter, and prepend an `### {rule.name}` markdown header.
4. Return the rendered fragment for inline placement.
The helper is only registered when rendering prompts, not when rendering rules. This enforces the "rules cannot include other rules" constraint at the renderer level — `{{ rule() }}` raises `UndefinedError` inside a rule template.
### 9.6 Example: render call
```python
rendered = renderer.render_artifact(
    template_path="rules/languages/python/typing.md.j2",
    context=context,
)
# rendered is now the full markdown including frontmatter, with all {{ vars }} substituted
rendered_plain = renderer.render_artifact(
    template_path="rules/frameworks/fastapi.md",
    context=context,
)
# .md files: frontmatter parsed, body returned verbatim. Context is unused for body.
```
### 9.7 Format-specific post-processing
The renderer exposes per-format transforms applied after Jinja substitution:
| Format | Transform |
| --- | --- |
| `continue_rule` | Pass-through; frontmatter is already in Continue's shape. |
| `claude_md_section` | Strip frontmatter, convert title to `##`, append `---` separator. |
| `agents_md_section` | Same as `claude_md_section`. |
| `prompt_continue` | Pass-through. If `includes_rules:` is set and body has no `{{ rule() }}` calls, append the auto-generated "Reference rules" section. |
| `prompt_claude_command` | Strip frontmatter; prepend a title line if not present. Same `includes_rules:` appendix logic. |
| `prompt_opencode_command` | Strip canonical frontmatter; emit a new minimal frontmatter with `description:` only (OpenCode's required field). Map `input_variables` to `$ARGUMENTS` / `$1` / `$2`. Same `includes_rules:` appendix logic. |
The CLI accepts both the full internal name and a short alias (e.g., `--format continue` is shorthand for `continue_rule`; `--format claude` for `claude_md_section`; `--format opencode` for `prompt_opencode_command`). The full names appear in `playbook render --show-source` output for precision; the short aliases are the daily UX.
```python
def render_for(template_path: str, context: dict, fmt: str) -> str: ...
```
## 10. Adapter subsystem
### 10.1 Adapter ABC
```python
# coding_agent_playbook/adapters/base.py
from abc import ABC, abstractmethod
from pathlib import Path
from coding_agent_playbook.types import Rule, Prompt, Skill


class Adapter(ABC):
    name: str  # e.g. "continue"
    # Repo-relative POSIX locations the adapter writes ("dir/" = everything
    # beneath it, else one file), e.g. (".claude/CLAUDE.md", ".claude/commands/",
    # ".claude/skills/"). The leftover policy (Section 4.2 step 9) deletes only
    # inside a declared location and never prunes above one.
    output_locations: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        """Write a rendered rule to the harness-specific location(s).
        Return the paths actually written. Adapters that route rules
        through another adapter (e.g. OpenCode → AGENTS.md) return []."""

    @abstractmethod
    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        """Write a rendered prompt."""

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Default: degrade to prompt. Subclasses with native skill support
        (claude_code, opencode, shared_skills) override this and delegate to the
        shared SkillWriter (Section 10.8); rules-only adapters return []."""
        prompt = skill.to_prompt()
        return self.write_prompt(prompt, repo_root)

    def finalize(self, repo_root: Path) -> list[Path]:
        """Optional lifecycle hook called after all write_* calls for this adapter.
        Used by adapters that buffer artifacts and emit a composite file at the
        end (e.g. Claude Code concatenates rules into a single CLAUDE.md).
        Default: no-op."""
        return []

    def cleanup_stale(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Delete generated files no longer corresponding to a current artifact.
        Default: scan the adapter's known output directories and remove files
        under sentinel headers that are not in written_paths (compared by file
        identity too, so a case-only rename never deletes fresh output).
        Subclasses override only if they need custom cleanup semantics; native
        skill directories are never cleaned here (Section 4.2 step 9)."""
        return self._default_cleanup(written_paths, repo_root)
```
Adapters return the paths they wrote. The CLI uses these for the lockfile and for `cleanup_stale`. `output_locations` is read from **every installed** adapter class, enabled or not (`orchestrator.installed_output_locations()`), so a since-disabled adapter's leftovers can still be settled; a third-party adapter that declares none never has a leftover deleted by the policy (its own `cleanup_stale` still runs while enabled). Of the five built-in adapters (Continue, Claude Code, OpenCode, AGENTS.md, shared_skills), only ClaudeCodeAdapter overrides `finalize()` (to compose CLAUDE.md); the rest write immediately in `write_rule` / `write_prompt` / `write_skill`.
### 10.2 Continue adapter
```python
# coding_agent_playbook/adapters/continue_adapter.py
class ContinueAdapter(Adapter):
    name = "continue"

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        target = repo_root / ".continue" / "rules" / f"{rule.priority:02d}-{rule.id}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render(rule), encoding="utf-8")
        return [target]

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        target = repo_root / ".continue" / "prompts" / f"{prompt.slash}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render(prompt, invokable=True), encoding="utf-8")
        return [target]
```
#### 10.2.1 Numbering scheme
Continue loads rules in lexicographical order, so the file name controls priority. The adapter prefixes filenames with the rule's `priority` (default 50, zero-padded to 2 digits). Authors keep priorities sparse (00, 10, 20, ..., 90) so new rules can slot in without renumbering.
| Priority | Used for |
| --- | --- |
| `00` | Project context (project name, kind, top-level description) |
| `10` | House style (formatting, naming, structure) |
| `20` | Tooling baseline (ruff, mypy, pytest, package manager) |
| `30` | Compliance and security (overlay territory) |
| `50` | Language-specific scoped rules (typing, error handling, logging) |
| `60` | Framework-specific scoped rules (fastapi, pydantic, sqlalchemy) |
| `70` | Domain-specific scoped rules |
| `90` | Per-repo customizations from `playbook/` |
### 10.3 Claude Code adapter
```python
class ClaudeCodeAdapter(Adapter):
    name = "claude_code"

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        # Rules are concatenated into CLAUDE.md, not written individually.
        # The adapter buffers rules and writes once in finalize().
        self._buffered_rules.append(rule)
        return []  # actual path returned by finalize()

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        target = repo_root / ".claude" / "commands" / f"{prompt.slash}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render_command(prompt), encoding="utf-8")
        return [target]

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        # .claude/skills/<id>/ via the shared SkillWriter (Section 10.8).
        return SkillWriter(Path(".claude") / "skills").write(skill, repo_root)

    def finalize(self, repo_root: Path) -> list[Path]:
        target = repo_root / ".claude" / "CLAUDE.md"
        body = self._compose_claude_md(self._buffered_rules)
        target.write_text(body, encoding="utf-8")
        return [target]
```
Skills are written natively to `.claude/skills/<id>/` (`SKILL.md` + byte-copied `scripts/` and `references/`) by the shared `SkillWriter`, with `name` = id and the sentinel as the first body line (§6.3). `cleanup_stale` combines two passes: the first-line sentinel scan over `.claude/commands/` and the single-file `.claude/CLAUDE.md` branch. It never deletes inside `.claude/skills/`: stale skill output is settled by the lockfile leftover policy (§4.2 step 9, §10.8).
#### 10.3.1 CLAUDE.md composition
```markdown
<!-- AUTOGENERATED by coding-agent-playbook v0.4.0 — edit in source, run 'playbook sync' -->
# {{ project_name }}
{{ project_description }}
This file is the project context for Claude Code. Rules are grouped by scope.
## Always-on rules
[concatenated bodies of all rules with scope=always, ordered by priority]
## Scoped rules
[for each scoped rule:]
### {rule.name}
*Applies to: {globs}*
[body]
---
## Available slash commands
[for each prompt:]
- `/{prompt.slash}` — {prompt.description}
```
### 10.4 AGENTS.md adapter
Always enabled. Produces a single `AGENTS.md` at the repo root. Identical in shape to `CLAUDE.md` but lives at the root because that's where Codex, Cursor, and Copilot look for it.
```python
class AgentsMdAdapter(Adapter):
    name = "agents_md"
    # Implementation mirrors ClaudeCodeAdapter but writes to repo_root / "AGENTS.md".
    # Prompts are not separately written; instead they are listed at the bottom
    # of AGENTS.md as documented slash-equivalents.
```
### 10.5 Adapter registration
Adapters are registered via entry points so overlay packages can ship their own (e.g. a Cursor adapter from a community package).
```toml
[project.entry-points."coding_agent_playbook.adapters"]
continue = "coding_agent_playbook.adapters.continue_adapter:ContinueAdapter"
claude_code = "coding_agent_playbook.adapters.claude_code_adapter:ClaudeCodeAdapter"
opencode = "coding_agent_playbook.adapters.opencode_adapter:OpenCodeAdapter"
shared_skills = "coding_agent_playbook.adapters.shared_skills_adapter:SharedSkillsAdapter"
agents_md = "coding_agent_playbook.adapters.agents_md_adapter:AgentsMdAdapter"
agent_harness = "coding_agent_playbook.adapters.agent_harness_adapter:AgentHarnessAdapter"
```
### 10.6 OpenCode adapter
OpenCode is structurally close to Claude Code but with one architectural twist: rules are not in a dedicated directory. OpenCode reads `AGENTS.md` at the repo root as its primary rules source, walking up the directory tree, with `CLAUDE.md` accepted as a fallback. This means the AGENTS.md adapter already delivers rules to OpenCode — the OpenCode adapter's job is prompts and skills.
Skills are written natively to `.opencode/skills/<id>/SKILL.md` (+ `scripts/`, `references/`) through the shared `SkillWriter` (§10.8), so OpenCode no longer depends on the Claude Code adapter being enabled. OpenCode *also* scans `.claude/skills/` (its Claude-compatibility discovery), so with both adapters on the same skill is discovered twice. That is safe: OpenCode stores discovered skills in a `Map` keyed by skill name, last write wins (verified in anomalyco/opencode `packages/core/src/config/plugin/compatibility.ts:53` and `skill.ts:155`), and the two copies are byte-identical.
```python
class OpenCodeAdapter(Adapter):
    name = "opencode"

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        # OpenCode reads AGENTS.md natively. Rules are routed through
        # the AgentsMdAdapter, not duplicated here.
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        target = repo_root / ".opencode" / "command" / f"{prompt.slash}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render_command(prompt), encoding="utf-8")
        return [target]

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        # .opencode/skills/<id>/ via the shared SkillWriter (Section 10.8);
        # byte-identical to the .claude/skills/ copy.
        return SkillWriter(Path(".opencode") / "skills").write(skill, repo_root)
```
#### 10.6.1 Prompt → OpenCode command format
OpenCode commands are markdown with YAML frontmatter. Required field is `description`; optional fields include `agent`, `model`, `subtask`. Placeholders supported in the body: `$ARGUMENTS`, `$1`, `$2`, …, `@path/to/file`, ``!`shell command` ``.
For a canonical prompt like `generate-tests`, the rendered output at `.opencode/command/generate-tests.md`:
```markdown
<!-- AUTOGENERATED by coding-agent-playbook v0.4.0 — edit in source, run 'playbook sync' -->
---
description: Generate pytest tests for the provided code, following the project's testing conventions
---
# Task: generate tests
You are writing tests for risk-models, a python-application project.
[body, fully rendered]
## Reference rules
[inlined rule bodies from includes_rules, same appendix logic as other adapters]
```
Mapping from canonical to OpenCode:
| Canonical field | OpenCode placement |
| --- | --- |
| `description` | Frontmatter `description` (required) |
| `slash` | Filename: `.opencode/command/<slash>.md` |
| `input_variables` | Mapped to `$ARGUMENTS` and positional `$1`, `$2`, … |
| `includes_rules` | Inlined into body via same appendix logic as other adapters |
| `name` | Not used in frontmatter; OpenCode uses filename as the command name |
| `applies_if` | Evaluated upstream by the engine; non-matching prompts produce no file |
OpenCode commands have no native concept of named input variables beyond positional `$N`. If a prompt declares an input variable `target`, the adapter substitutes `$ARGUMENTS` for it in the body and inlines a brief HTML comment noting the variable's purpose for the human reader. v1 does not attempt to model OpenCode's optional `agent` / `model` / `subtask` frontmatter fields — the rendered command runs in OpenCode's default agent with the user's default model.
#### 10.6.2 Hook gap (out of scope for v1)
OpenCode does not support declarative lifecycle hooks. Equivalent behavior requires shipping a JS/TS plugin to `.opencode/plugin/`, subscribing to OpenCode's 31 documented runtime events (`tool.execute.before`, `tool.execute.after`, `session.idle`, etc.). This is **out of scope for v1**; the OpenCode adapter emits no plugin code. See open question 8 in Section 19.
#### 10.6.3 Agents gap (out of scope for v1)
OpenCode supports named agents (`build`, `plan`, custom modes) with their own model and permission overrides, defined in `.opencode/agent/<name>.md`. The canonical artifact model has no concept of named agents in v1. Users wanting custom OpenCode agents write them by hand. See open question 9.
#### 10.6.4 What the OpenCode adapter does NOT touch
To make the boundaries explicit, the OpenCode adapter writes only `.opencode/command/` and `.opencode/skills/`, and its own `cleanup_stale` scans only `.opencode/command/` (stale `.opencode/skills/` output is settled by the lockfile leftover policy, §4.2 step 9). In `.opencode/skills/` it writes only engine-owned skill dirs — a hand-written skill dir whose name collides with a canonical skill id is skipped with a warning, never overwritten. It does **not** write or modify:
- **`.opencode/agent/`** — out of scope; users own custom agents.
- **`.opencode/plugin/`** — out of scope (hook equivalent); users own plugins.
- **`opencode.json`** — out of scope; users own MCP server config, permissions, model selection, and the `instructions` array.
- **`AGENTS.md`** — owned by the AGENTS.md adapter; OpenCode reads it natively.
- **`.claude/` (incl. `.claude/skills/`)** — owned by the Claude Code adapter. OpenCode may also discover skills there; duplicates are safe (see above).
This deliberate minimalism keeps the OpenCode adapter small and avoids stepping on user-owned config.
### 10.7 Agent Harness adapter
The `agent_harness` adapter renders canonical artifacts into a [Agent Harness](https://agentharnesses.io/specification) tree — a `HARNESS.md`-rooted format consumed by harness clients. Unlike the five built-in adapters it is **opt-in**: it is not in the default adapter set and is not force-enabled like `agents_md`. Enable it by listing `agent_harness` in the top-level `adapters_enabled` list (§7.1). It is discovered through the same entry-point mechanism (§10.5); the engine never constructs it directly.
```python
class AgentHarnessAdapter(Adapter):
    name = "agent_harness"
    # Buffers write_rule/write_prompt/write_skill, then composes the whole
    # tree in finalize() so HARNESS.md can index everything that was emitted.
    # Accepts an optional rule_registry to inline a prompt's includes_rules.
```
#### 10.7.1 Emitted tree
The adapter emits a harness tree under the repo root (`specs/prH-agent-harness.md` §B):
```
<repo-root>/
├── HARNESS.md                  # name/description (repo-derived) + dir index +
│                               #   "Always consult these" pointer at scope=always rules
├── .leaf-detectors             # "skill=SKILL.md" — written only when a skill/prompt leaf exists
├── skills/
│   ├── SKILLS.md               #   routing file (description-only frontmatter)
│   └── <id>/
│       ├── SKILL.md            #   name + description + body
│       ├── scripts/            #   ← Skill.scripts_dir, byte-copied verbatim (shutil.copy2)
│       └── references/         #   ← Skill.references_dir, byte-copied verbatim
├── prompts/
│   ├── PROMPTS.md
│   └── <slash>/SKILL.md        #   skill-shaped leaf; includes_rules inlined via rule()
├── rules/
│   ├── RULES.md
│   └── <priority:02d>-<id>.md  #   scope=always rules; frontmatter = description only
├── references/
│   ├── REFERENCES.md
│   └── <id>.md                 #   scope=scoped rules; frontmatter = description only
└── .playbook/                  # round-trip sidecar (dotfile; harness clients skip it)
    ├── manifest.toml           #   full canonical reconstruction payload (§20.10)
    └── .harnessleaf            #   terminal marker so clients treat .playbook/ as opaque
```
#### 10.7.2 Canonical → harness mapping
| Canonical type | Harness destination | Native fields on the leaf |
| --- | --- | --- |
| `Skill` | `skills/<id>/SKILL.md` (+ `scripts/`, `references/`) | `name`, `description`, body, copied script/reference bytes |
| `Prompt` | `prompts/<slash>/SKILL.md` (skill-shaped leaf) | `name`, `description`, body with `includes_rules` inlined via `rule()` + an input-variables note |
| `Rule` (scope=always) | `rules/<priority:02d>-<id>.md` | `description`, body |
| `Rule` (scope=scoped) | `references/<id>.md` | `description`, body |

`scope=always` rules go to `rules/` and `HARNESS.md` adds an "Always consult these" section instructing the agent to read them every session — keeping the root body small and spec-idiomatic. The harness rule file emits **only** `description`; the rule `name` and every other non-native field round-trip via the sidecar (§20.10).

**Eval tasks are not emitted.** The `Adapter` ABC has no eval hook — `sync` only dispatches `write_rule` / `write_prompt` / `write_skill` / `finalize` — so eval tasks are authoring-only and never reach any adapter. The `agent_harness` adapter therefore never writes an `evals/` directory, exactly like the five built-in adapters. (The importer in §12.9 can still *read* a foreign `evals/` directory.)
#### 10.7.3 Sentinel placement and cleanup
A harness parser requires frontmatter to start on line 1 (`^---`), so the playbook `SENTINEL` cannot be line 1. The adapter writes it as the **first body line** (an HTML comment, after the closing frontmatter fence) on every generated text file. Because of this, the adapter overrides `cleanup_stale` to detect the sentinel *anywhere* in a file rather than only on line 1 (the Claude Code / AGENTS.md single-file pattern), comparing against the written set by file identity (a case-only id rename on a case-insensitive filesystem never deletes the file just written). Files without a sentinel are user-authored and never deleted. `cleanup_stale` never deletes inside a skill directory (`skills/<id>/` — its `SKILL.md`, scripts and references): like every native skill root, stale skill output there is settled only by the lockfile leftover policy (§4.2 step 9), so a user-edited script is kept; `skills/SKILLS.md` and the `prompts/`, `rules/`, `references/` and root files are still cleaned here. The `HARNESS.md` directory index lists what this render emits, never what happens to be on disk (a leftover or user-owned top-level `skills/` would otherwise change its bytes, and `sync --check`, rendering into an empty scratch dir, would drift forever).
### 10.8 Shared-skills adapter and the `SkillWriter`
The `shared_skills` adapter writes every canonical skill to `<repo>/shared_skills/<id>/` — the **cross-agent skills hub**: one agent-neutral copy of the skills that any Agent-Skills-aware tool (or a human) can be pointed at, independent of which harness adapters are enabled. Like all generated output it is gitignored and regenerated on each machine by default; it is committed only with `[output] commit = true` (§5.3, §7.1). It is **on by default** (`playbook init` lists it in `adapters_enabled`) but, unlike `agents_md`, **not force-enabled** — remove it from `adapters_enabled` to opt out. `write_rule` / `write_prompt` return `[]` (rules reach every assistant through `AGENTS.md`; prompts through the harness adapters). It takes no `rule_registry`, so `discover_adapters` constructs it with no arguments, like `agents_md`.
```python
class SharedSkillsAdapter(Adapter):
    name = "shared_skills"

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        return []  # rules -> AGENTS.md

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        return []  # prompts -> harness adapters

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        return SkillWriter(Path("shared_skills")).write(skill, repo_root)
```
**The `SkillWriter`** (`adapters/_skill_writer.py`) is the single source of truth for a native skill directory; `claude_code` (`.claude/skills`), `opencode` (`.opencode/skills`) and `shared_skills` (`shared_skills`) each hold one, differing only in the repo-relative root, so a skill is **byte-identical in every root**.
- **Write.** `<root>/<id>/SKILL.md` (frontmatter on line 1 with `name` = id, the sentinel HTML comment as the first body line, then the body) plus byte-copies (`shutil.copy2`, copies not symlinks — source symlinks are dereferenced, exec bits preserved) of the canonical `scripts/` and `references/` subtrees. Returns every file written.
- **Path safety.** Non-path-safe ids (separators, `.`/`..`, NUL, drive/absolute) raise `ValueError` with the offending value; a destination whose directory resolves outside the root (via a symlink) is refused before anything is created, and a symlink sitting at a destination file is replaced, never written through.
- **Ownership before writing.** `write` claims `<root>/<id>/` only if it is absent, an empty directory, engine-owned (sentinel), or a real directory whose `SKILL.md` the previous sync's lockfile lists **with unchanged bytes** (pre-v0.15 output). Anything else — a hand-written skill dir with a colliding id, a symlinked dir or `SKILL.md`, a plain file, a listed `SKILL.md` the user has since rewritten (an adopted leftover, which the lockfile keeps listing as a kept orphan, or a stripped sentinel) — is skipped with a stderr warning and returns `[]`, so its files are never overwritten. A skills root that cannot hold directories (a dangling symlink, a plain file) is skipped with a warning too, never a crash. Inside a claimed dir an existing destination file or symlink is unlinked before writing (never written through, so a read-only copy from an earlier sync cannot fail the rewrite), as is a symlink where a parent directory must go. A file/folder swap — a regular file where a parent directory must go, or a real directory where a file must go — is displaced only if every file it holds is one the §4.2 step 9 leftover policy would delete (listed in the previous lockfile, bytes unchanged, untracked by git, inside a declared output location, every adapter installed): write-mode `sync` installs that very policy around its render (`_prior_output.judging_leftovers_with`), displaced files count as `removed`, and outside `sync` nothing is displaced. Anything else (a user file, an edited or tracked copy, a symlink) vetoes it, and that one destination is skipped with a stderr warning (`--check` then reports it missing, naming the blocker, until the user moves those files). Only files are ever recorded as written.
- **Check modes decide ownership against the real tree.** `playbook sync --check`/`--check-staged` render into an empty scratch dir, but inside `deciding_ownership_against(repo_root)` the writer judges `<root>/<id>/` (and the legacy lockfile claim) on the real repo, so the render skips exactly the dirs write mode skips: a colliding hand-written dir is neither false drift nor "generated output" to the staged-output guard.
- **Case-only id renames.** On a case-insensitive filesystem (default macOS APFS, Windows), an engine-owned `<root>/<Old>/` that *is* `<root>/<old>/` is renamed to the new spelling before writing, so the directory keeps matching the emitted `name`.
- **No cleanup in the writer.** `<root>/<id>/` is engine-owned iff it is a real directory whose `SKILL.md` (a regular file) contains the sentinel anywhere — searched as bytes, so binary or undecodable files never crash it. The writer and the adapters' `cleanup_stale` never delete stale skill files: a skill dir mixes engine output with files a user may have edited or added, so stale output there is settled only by the lockfile leftover policy (§4.2 step 9) — deleted only if the previous lockfile lists it, its bytes still match, git does not track it, it lies in a declared output location and every enabled adapter is installed; directories left empty are pruned (the skill dir, then an emptied skills root — never above it, and never the target of a symlinked root). A file the engine never wrote is never deleted, even inside an engine-owned dir, and directories without the sentinel are user-authored and **never touched**.
- **Upgrade note.** `.claude/skills/<id>/` directories written before v0.15 carry no sentinel. A skill still present after upgrading is re-claimed through the lockfile (its `SKILL.md` is listed there with the bytes the old engine wrote; one edited since stays the user's), gains the sentinel, and its stale engine-written files are settled by the leftover policy from then on. A skill deleted *before* upgrading is never written again, so it is left in place (treated as user-authored); delete it by hand once.
## 11. Overlay system
### 11.1 Three layers
The artifact list is built by merging three sources in order:
1. **Engine resources** (`coding_agent_playbook/resources/`). Generic, open-source, organization-neutral.
2. **Overlay packages** (e.g. `playbook_rules_bnp/resources/`). Each enabled overlay contributes additional artifacts and can override engine artifacts by ID. Overlays are applied in the order listed in the top-level `overlays_enabled` key (§7.1); each must be importable and ship a `resources/` directory (§4.2 step 1).
3. **Repo-local** (`<repo>/playbook/`). The consumer's own customizations, with the same subdirectory shape as the engine's `resources/` — i.e. `<repo>/playbook/rules/`, `<repo>/playbook/prompts/`. Always wins on ID collision. The `resources/` subfolder used by packaged sources is dropped here because consumer repos are not Python packages and don't need the extra nesting.
### 11.2 Merge semantics
For each artifact ID across all layers:
- If only one layer defines it, use it.
- If multiple layers define it, the later layer wins (overrides). The original is not merged; it is replaced.
- If a layer wants to *extend* rather than *replace*, it ships an artifact with a different ID (e.g. `python-typing-banking-extras`) and relies on both being loaded.
This is intentionally non-magic. We considered Jinja-based block inheritance across layers and rejected it as too implicit — the user reading `playbook render --show-source python-typing` should see exactly one source file.
### 11.3 Example
Engine ships:
- `python-typing` (always-on, generic)
- `fastapi` (scoped)
Overlay `playbook-rules-bnp` ships:
- `python-typing` (overrides — adds BNP-specific typing requirements like Pydantic field-level validators on PII fields)
- `banking-pii-handling` (new, always-on)
Consumer repo `playbook/` ships:
- `risk-models-glossary` (new, always-on)
Result: 4 active artifacts. The engine's `python-typing` is shadowed by BNP's version. The user can see this via `playbook render --show-source`:
```
$ playbook render --show-source python-typing
Source: playbook_rules_bnp/resources/rules/languages/python/typing.md.j2
Overrides: coding_agent_playbook/resources/rules/languages/python/typing.md.j2
```
### 11.4 Authoring an overlay
A minimal overlay package:
```python
# src/playbook_rules_bnp/__init__.py
from importlib.resources import files
from coding_agent_playbook.overlays import Overlay

OVERLAY = Overlay(
    name="bnp",
    version="0.2.0",
    resources_root=files("playbook_rules_bnp") / "resources",
    description="BNP Paribas-specific rules for ML/DS teams",
)
```
```toml
# pyproject.toml
[project]
name = "playbook-rules-bnp"
dependencies = ["coding-agent-playbook>=0.4.0,<0.5.0"]
[project.entry-points."coding_agent_playbook.overlays"]
bnp = "playbook_rules_bnp:OVERLAY"
```
That's the entire integration surface. The overlay then drops its content into `resources/rules/`, `resources/prompts/`, etc. following the same layout as the engine.
### 11.5 Bundled opt-in packs
A **pack** is an importable subpackage under `coding_agent_playbook.packs.*` whose `resources/` tree (`rules/`, `prompts/`, `skills/`) is layered **exactly like an overlay package** (Section 11.1, layer 2; same ID-collision rule as Section 11.2) but ships **inside the engine wheel**: enabling one needs no extra install, package index, or network access (G5). Packs are **off by default**. The engine layer never walks them; a consumer opts in by listing the pack's dotted package name in the top-level `overlays_enabled` key, and `FileSystemArtifactSource` resolves `<package>/resources/<kind>/` through `importlib.resources` like any overlay. No entry point is involved. Repo-local artifacts still win on ID collision, so a consumer overrides one pack skill by shipping `playbook/skills/<id>/`.
```toml
# .coding-agent-playbook.toml (top-level keys, above the first [table] header: the form `playbook init` writes and Config reads)
overlays_enabled = ["coding_agent_playbook.packs.superpowers"]
adapters_enabled = ["continue", "claude_code", "opencode", "shared_skills"]   # the init default
```
Use the top-level keys; they are the only form `Config` reads. Put them above the first `[table]` header: a config `playbook init` wrote without `--overlays` has no `overlays_enabled` line and ends with `[detector_cache.frameworks]`, so a line appended to the end lands in that table. The configuration mistakes this invites are all caught:
- **The table form, a nested key and a misspelled key are refused.** An `[overlays] enabled` / `[adapters] enabled` table (or the dotted `overlays.enabled = …` key), an `overlays_enabled`/`adapters_enabled` key written after a `[table]` header (TOML nests it in that table), or a close misspelling such as `overlay_enabled`, in `.coding-agent-playbook.toml` or `.coding-agent-playbook.local.toml`, is a `ConfigError` naming the file (and the table) and showing the top-level line to write instead, above the first `[table]` header (§7.1). Every command that loads the config exits 2 with `error: …` before writing or deleting anything, so a repo already synced with the pack keeps its skills, lockfile and managed `.gitignore` block byte-identical (pinned for every sync mode by `tests/cli/test_config_errors.py`). (Before this check the table form read as two empty lists: `sync` exited 0, rendered only `AGENTS.md`, and settled every other adapter's output as leftovers.)
- **A misspelled pack name is caught by every command**, through the one shared check `_sync_preflight.unusable_overlays` (§4.2 step 1): a listed package whose import fails, or that imports but ships no `resources/` directory (the parent `coding_agent_playbook.packs`, say), is unusable. The check imports each overlay, as rendering's `importlib.resources.files` does, so a package that raises at import time is reported with its error (`not importable (RuntimeError: …)`, likewise a missing dependency of the overlay) instead of crashing the command with a traceback; artifact discovery skips such a package like a missing one, so only this check names it. Every `playbook sync` mode refuses with an `error:` naming each unusable package and its reason, one per line, and writes nothing — write mode, `--check` and `--check-staged` (the last only under `commit = false`, where it is not a no-op, §12.3.1). `playbook validate` reports each as a validation error (exit 1, §12.6); `playbook check` flags each under `Overlays:` and no longer reports a clean state (exit 0, §12.4); `playbook init` refuses them before writing any file (exit 2, §12.1) — from `--overlays`, or from the local file's `overlays_enabled`, which replaces it. A name that reads like a mistyped bundled pack (it starts with the engine package, or its last segment is close to a pack's) gets the bundled-pack list, discovered with `pkgutil`: `coding_agent_playbook.packs.superpower: not importable (bundled packs: coding_agent_playbook.packs.superpowers)`.

`playbook init --non-interactive --name … --kind … --overlays coding_agent_playbook.packs.superpowers` writes the top-level form, with the default adapter list.

A pack's package exposes `PACK_NAME = __name__` (the string to list), ships third-party content with its upstream `LICENSE` plus an `ATTRIBUTIONS.md` next to `__init__.py`, and keeps its `resources/` out of `[tool.ruff]` (`extend-exclude = ["src/coding_agent_playbook/packs/*/resources"]`), because vendored text must stay byte-faithful and newer unpinned ruff versions also reformat code blocks inside markdown. Hatch packages every non-ignored file under `src/coding_agent_playbook/`, so the pack's markdown, `LICENSE`, `ATTRIBUTIONS.md`, and scripts ship in the wheel, and the scripts keep their executable mode. The wheel's distribution metadata (`License: Apache-2.0`, `License-File: LICENSE`) describes the engine only. A pack's third-party license ships as a file inside the package (`packs/<name>/LICENSE`), not in the dist-info metadata.

A pack's skills are canonical skills like any other, so they render through the same adapters (Section 6.3, Section 10.8) and, under the default `[output] commit = false`, are generated output like any other: the managed `.gitignore` block lists one `/<root>/<id>/` entry per skill directory, and every clone regenerates them (Section 5.3).

**Opting out and overriding.** Removing a pack from `overlays_enabled` turns everything earlier syncs wrote for it into **leftovers**, which the next write-mode `playbook sync` settles by the lockfile leftover policy (§4.2 step 9, §10.8) under both `[output] commit` settings. A file the previous lockfile lists is deleted only when its bytes still match that entry, git does not track it, it lies inside an installed adapter's declared `output_locations` (§10.1), and every enabled adapter is installed; the directories it leaves empty are pruned, never above a skills root. Generated output is untracked under the default `commit = false`, so each pack skill directory disappears from every skill root (`.claude/skills/`, `.opencode/skills/`, `shared_skills/`, and `agent_harness`'s `skills/` when enabled), and a skills root left empty is pruned too. Edited and user-added files are kept:
- A pack file you edited after it was synced stays engine-owned: it is carried forward in the lockfile and, under `commit = false`, stays in the managed block, until you delete it by hand.
- A file you added inside a synced skill directory (say, notes under `.claude/skills/<id>/references/`, or `node_modules/` under a `scripts/` directory) is not in the lockfile, so it is never deleted, and the directory that holds it is not pruned.
- Under `commit = true`, committed (tracked) skill files are kept as well and listed on stderr (`note: kept output an earlier sync wrote …`) until you `git rm` them.

The pack's degraded Continue prompts are not skill output. They carry the sentinel on line 1, so Continue's `cleanup_stale` deletes them as soon as the pack is off, edited or not, tracked or not (under `commit = true` the deletion shows up as an unstaged git deletion), as long as that line is still there (§10.1). Between opting out and that sync, `playbook sync --check` under `commit = false` reports the managed `.gitignore` block as stale (exit 1); it does not list the individual leftovers, and under `commit = true` it reports no drift.

The same policy runs when a repo-local `playbook/skills/<id>/` overrides one pack skill. The override's `SKILL.md` replaces the pack's in every skill root, and every unedited, untracked pack file under `<root>/<id>/scripts/` or `references/` that the override does not ship is deleted, whether the override ships no such directory or only some of its files. `tests/packs/test_superpowers_sync.py` pins the opt-out across all three native skill roots (and `agent_harness`'s `skills/`), the kept edited and user-added files, and both override cases, in hermetic real git repos.
#### 11.5.1 The `superpowers` pack
`coding_agent_playbook.packs.superpowers` is a **near-verbatim port** of the Superpowers skills library by Jesse Vincent (repository obra/superpowers, v7.0.0, upstream commit `bb92a77`, MIT). It ships 15 skills and nothing else (no rules, prompts, or eval tasks): `brainstorming`, `diagnosing-superpowers`, `dispatching-parallel-agents`, `executing-plans`, `finishing-a-development-branch`, `receiving-code-review`, `requesting-code-review`, `subagent-driven-development`, `systematic-debugging`, `test-driven-development`, `using-git-worktrees`, `using-superpowers`, `verification-before-completion`, `writing-plans`, `writing-skills`.

The upstream wording is kept. The only edits are the self-containment transformations:
- **Restructure.** Skill sync copies only `SKILL.md`, `scripts/`, and `references/` (Section 6.3.1). Every other file at an upstream skill root moved under `references/` (e.g. `systematic-debugging/root-cause-tracing.md` → `references/root-cause-tracing.md`, `diagnosing-superpowers/prompts/` → `references/prompts/`), and root executables moved under `scripts/` (`find-polluter.sh`, `render-graphs.js`). One file is new: `writing-skills/scripts/package.json` (`{"type": "module"}`), because `render-graphs.js` is ES-module syntax that upstream parsed as ESM only through its repo-root `package.json` (not vendored); the helper stays optional and still needs Node.js + Graphviz where it runs. Every mention of a moved file (links, inline paths, prose, graph labels, the usage comments of `find-polluter.sh` and `render-graphs.js`) points at the new location; inline paths are written relative to the skill directory, as upstream's were.
- **License copies.** Every skill ships `references/LICENSE`, a byte-identical copy of the pack's `LICENSE`, so the MIT notice travels with each synced skill directory (see Attribution below).
- **Frontmatter.** `id: <dir-name>` is inserted as the first key; `name` and `description` are kept. The one changed description is diagnosing-superpowers', which no longer names the upstream maintainers as the bug report's recipient.
- **Cross-skill references.** `superpowers:<skill>` becomes the plain skill name. All 15 skills ship together, so every reference resolves inside the pack.
- **No external URLs.** No URL (any `scheme://`, `mailto:`, or `www.` form) remains anywhere in the pack. Markdown links keep their text as plain text, MDX cards keep their title and body but lose their `href`, and each external image becomes an italic `*(Diagram omitted: <alt text>)*` note. The PR-L link gate (Section 12.6) passes under the strict default allowlist.
- **Upstream-plugin coupling removed.** Text that required installing the upstream plugin or marketplace, relied on its hooks or plugin environment variables, read upstream-repo files not in the pack, or asked the reader to file issues upstream was removed or minimally reworded. Two short additions keep dropped plumbing usable. using-superpowers' Platform Adaptation list names `references/gemini-tools.md` for Gemini CLI, because upstream loaded that file only through the dropped repo-root `GEMINI.md`. diagnosing-superpowers' skill-timeline prompt and case template explain how to attribute skills that come from a rendered, un-namespaced pack.

Dropped, and why:
- **The brainstorming visual companion** (a Node.js server with its HTML/JS assets and start/stop scripts, plus `visual-companion.md`). It needs a JavaScript runtime and a local web server, so it cannot be self-contained.
- **The SessionStart bootstrap hook** that injects `using-superpowers` at session start. The canonical artifact model has no hook artifact (cf. the hook gap in Section 10.6.2), so `using-superpowers` is discovered like any other skill, by its description.
- **diagnosing-superpowers' upstream issue filing.** The issue-filing reference, issue template, and GitHub-issues workflow step are gone. The skill still writes its local report and, when the goal is a bug report, offers a scrubbed bundle on request.
- **All non-skill repository content**: per-harness plugin manifests (including the repo-root `GEMINI.md`), hooks, docs, tests, and repo-root scripts.

Third-party content: `writing-skills/references/anthropic-best-practices.md` reproduces Anthropic's public skill-authoring best-practices documentation as upstream shipped it. `ATTRIBUTIONS.md` records that it is not authored by Jesse Vincent.

Consumer-repo conventions the skills use (`docs/superpowers/specs/`, `docs/superpowers/plans/`, the `.superpowers/sdd/` runtime workspace) are paths inside the consumer's own repo, not dependencies, and stay verbatim.

**Rendering per adapter.**
- **Claude Code, OpenCode, shared_skills:** native, through the shared `SkillWriter` (Section 10.8), to `.claude/skills/<id>/`, `.opencode/skills/<id>/` and `shared_skills/<id>/`. The three copies are byte-identical: `SKILL.md` with its frontmatter on line 1 (`name` = id, which the pack's `id == name` frontmatter already satisfies) and the sentinel HTML comment as the first body line, followed by the vendored body unchanged, plus byte-copied `references/` and `scripts/` (`shutil.copy2` keeps the scripts' executable bit). OpenCode no longer needs `claude_code` enabled, and `shared_skills` is on by default (the `playbook init` adapter list). Each adapter writes only directories it owns: a hand-written `<root>/<id>/` that collides with a pack skill id is skipped with a warning, never overwritten.
- **Continue:** has no native skills. Each skill degrades to `.continue/prompts/<id>.md` through `Skill.to_prompt`, which carries the `SKILL.md` body but not `scripts/` or `references/`. Reference links and script-driven steps therefore only work under the native adapters. Steps 2–3 of Section 6.3.2 (copying `scripts/` to `.coding-agent-playbook/skills/<id>/scripts/` and adding a helper-scripts note to the prompt) are not implemented: `Adapter.write_skill` only calls `write_prompt(skill.to_prompt())`. The degraded prompts also lack `references/LICENSE`, so a consumer that renders the pack only for Continue must keep the pack's `LICENSE` next to them.
- **Agent Harness (opt-in, Section 10.7):** emits `skills/<id>/SKILL.md` (sentinel as the first body line) with `scripts/` and `references/` byte-copied, and records each script's executable flag in `.playbook/manifest.toml`. Enable it through the top-level `adapters_enabled` key.
- **AGENTS.md:** rules only. Skills are a no-op.

**Sibling-skill dependency.** `executing-plans/scripts/task-start` and `task-done` resolve `$(dirname "$0")/../../subagent-driven-development/scripts` and call its `task-brief` and `sdd-workspace`, and `executing-plans/SKILL.md` names `../subagent-driven-development/scripts/…` helpers. This holds because sync writes every pack skill as a sibling directory under each skill root. A consumer that overrides `subagent-driven-development` must ship `scripts/task-brief` and `scripts/sdd-workspace` in its `playbook/skills/subagent-driven-development/scripts/`: sync removes the pack's unedited copies of every script the override does not ship (Section 11.5), which breaks executing-plans' scripted flow.

**Attribution.** `packs/superpowers/LICENSE` is the upstream MIT text verbatim. MIT requires the copyright and permission notice in every copy, so it ships in the wheel, and the byte-identical `references/LICENSE` in every skill carries it into each synced skill directory (`.claude/skills/<id>/`, `.opencode/skills/<id>/`, `shared_skills/<id>/`, and the Agent Harness `skills/<id>/`). Continue's body-only prompts are the exception noted above. `ATTRIBUTIONS.md` records the source, version, commit, the indication of changes above, the provenance of `anthropic-best-practices.md`, and a per-skill table. Both are plain text with no URLs.

**Gates.** `tests/packs/` pins the 15 ids, the 7-script inventory (plus the `package.json` module-type sidecar), and the full `references/` inventory, with every `references/LICENSE` byte-identical to the pack's. It also pins frontmatter identity (`id` first, `id == name ==` directory name), the synced-entries-only layout, and self-containment: no URL of any scheme anywhere in the pack (including `LICENSE`, `ATTRIBUTIONS.md`, and `__init__.py`), no `superpowers:` references, no upstream-plugin markers, and every `references/…` / `scripts/…` path named in a `SKILL.md` or reference file resolving inside the pack, apart from an explicit allowlist of illustrative examples. Further gates cover executable bits and `bash -n`; an end-to-end opt-in `playbook sync` + `validate` + `sync --check` that checks each synced `SKILL.md` (sentinel body line, then the vendored body), the license copy in every synced skill, that the `.claude/skills/`, `.opencode/skills/` and `shared_skills/` copies are byte-identical, and each degraded Continue prompt (sentinel on line 1, then the vendored body); an opt-in `agent_harness` sync whose `skills/<id>/` copies carry the sentinel body line, the vendored body and `references/LICENSE`, with every script executable and flagged in `.playbook/manifest.toml`; and the opt-out and override removal described in Section 11.5. `tests/cli/test_validate_links.py` runs the PR-L link gate over the pack and asserts that the pack's `skills/` resource directory resolves, so the gate cannot pass without scanning anything.
## 12. CLI contract
The CLI binary is `coding-agent-playbook`, with a short alias `playbook`. Both names are entry points in `pyproject.toml`:
```toml
[project.scripts]
coding-agent-playbook = "coding_agent_playbook.cli:main"
playbook = "coding_agent_playbook.cli:main"
```
### 12.1 `playbook init`
Interactive bootstrap for a fresh repo. Safe to re-run: `.coding-agent-playbook.toml` is rewritten from itself — values and unknown keys are kept, comments and layout are not (see *Re-running* below); a file `init` wrote comes back byte-identical for the same answers and detected facts — the local file is never rewritten, and `.gitignore` and `.pre-commit-config.yaml` are merged into, not replaced.
```
$ playbook init
coding-agent-playbook v0.4.0
? Project name: risk-models
? Project description: Counterparty risk scoring service
? Project kind: › python-application
                   python-library
                   ml-research
                   notebook
? Which assistants will the team use? (multi-select)
   ◉ Continue
   ◉ Claude Code
   ◉ OpenCode
   ◉ Shared skills hub (shared_skills/)
   ◯ Codex CLI (AGENTS.md only)
? Enable overlay packages? (detected: playbook-rules-bnp)
   ◉ playbook-rules-bnp
? Docstring style: › numpy
                     google
                     none
? Test layout: › tests/ mirroring src/
                 tests/ flat
                 inline (test_*.py next to source)
✓ Detected Python 3.12 with uv
✓ Detected frameworks: fastapi, pydantic, sqlalchemy, pytest
✓ Wrote .coding-agent-playbook.toml ([output] commit = false)
✓ Wrote .coding-agent-playbook.local.toml (gitignored)
✓ Appended .coding-agent-playbook.local.toml to .gitignore
✓ Wrote .pre-commit-config.yaml (merged with existing)
Install the git hooks with: pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge
✓ Ran playbook sync — generated 12 files, gitignored via the managed block
Next steps:
  - Review generated AGENTS.md, .continue/, .claude/, .opencode/ (local-only)
  - Commit .coding-agent-playbook.toml, .pre-commit-config.yaml, and .gitignore
  - Open VS Code; Continue will pick up rules automatically
```
`playbook init` writes `[output] commit = false` explicitly (an existing value is preserved) and picks the playbook hooks for that policy (§13.2/§13.3). It **does not run pre-commit itself**: under `commit = false` it prints the hook-install command, since the auto-sync hook only fires once the `post-checkout`/`post-merge` git hooks are installed: `pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge` (a plain `pre-commit install` does the same when the config carries `default_install_hook_types`, as the fresh starter does). Merging into an existing config can also print a `warning:` (a hand-edited legacy drift hook to delete) or a `note:` (no `default_stages`) on stderr — §13.3.

`playbook init` writes the enabled lists as the top-level `overlays_enabled` / `adapters_enabled` keys (§7.1). Before writing **any** file it exits 2 on a usage error: missing `--name`/`--kind` in non-interactive mode, an overlay the sync preflight would reject among those its final sync will use (`error: --overlays names package(s) that cannot be used as overlays here; nothing was written:` followed by one `<name>: <reason>` line each — not importable, with the import error when there is one, or no `resources/` directory; a pack-like typo lists the bundled packs, §11.5). When `.coding-agent-playbook.local.toml` sets `overlays_enabled`, that list replaces `--overlays` for init's final sync (§7.2), so it is checked too, and its error starts `error: overlays_enabled in .coding-agent-playbook.local.toml names package(s) …`; `--overlays` is still checked, since it is what the committed file gets and every teammate without that local file syncs with it (before v0.18 a local list hid an unusable `--overlays`, which was committed and broke their `playbook sync`). Both lists are reported when both are unusable. A `ConfigError` (§7.1) stops it too, checked in this order before the first write: the local file on its own (up front, with the overlay check: a syntax error, `[output] commit = "yes"` or `project = "x"` there exits 2 naming it); on a re-run, the committed file on its own (a missing required key included — the local file is never allowed to supply one); then the config its final sync will load, i.e. the planned committed file with the local file merged on top (`FileSystemStateSource.preview_config`), on a first run too. So nothing is written, and nothing fails in the final sync after the committed files were rewritten.

**Re-running `playbook init`** rewrites `.coding-agent-playbook.toml` from the committed file alone, through `commands/_committed_config.plan_committed_update` (`check --refresh` uses its sibling `plan_detector_cache_refresh`, §12.5). The local file is checked but never merged into what is written, so one engineer's `adapters_enabled`, `overlays_enabled`, `[user_choices]`, `[output]` or any other local key never reaches the committed file (§7.2); an existing local file is left untouched. A re-run needs a complete committed file: one missing a required key exits 2 with nothing written, even when the local file supplies the key. What the rewrite does with each key:
- **Replaced** — what `Config` owns, written from the updated committed config and never merged with the old file, so an emptied list or a dropped key stays dropped: the top-level keys in `config_entries.CONFIG_MANAGED_KEYS` — `[detector_cache]` and `[user_choices]` whole, and inside `[project]`/`[engine]`/`[storage]`/`[output]` only the keys `Config` reads (`config_entries.CONFIG_MANAGED_TABLE_KEYS`). `[project]` and `overlays_enabled` take the answers: an omitted or empty `--overlays` removes the key (both mean no overlays), and so does an empty description; `adapters_enabled` keeps the committed list in its order, then appends each answered adapter it lacks; `[detector_cache]` is re-detected, so a stale entry goes. `schema_version`, `[engine] version`, `[storage]`, `[user_choices]` and `[output] commit` keep their committed values (`[output] commit = false` is added when the table is absent, a missing `[storage]` is written with its defaults). Like `Config.to_dict`, the rewrite omits a list or description left empty: an explicit `overlays_enabled = []` or `description = ""` disappears.
- **Preserved** — everything else, with the same parsed values (floats, dates, nested tables and arrays of tables included): every other top-level key (`[links]`, `[metrics]`, a table a later engine version adds, a key the engine does not know), written after the managed keys, and the unknown keys inside `[project]`/`[engine]`/`[storage]`/`[output]` (`[project] homepage`), written after that table's own keys.

The file is re-serialized: values survive, comments and layout do not, and a value comes back in the writer's spelling — a hex, octal or binary integer in decimal, a `Z` offset as `+00:00`, an inline table as a `[sub]` table and an array holding only inline tables as `[[sub]]` tables (inside a mixed or nested array they stay inline). The hooks merged into `.pre-commit-config.yaml` (and the hook-install hint) follow the committed `[output] commit`; the final `playbook sync` runs with the merged config, local overrides included.
### 12.2 `playbook sync`
Regenerate all artifacts. The workhorse command. Run automatically by the `post-checkout`/`post-merge` hook under the default `[output] commit = false` (and **once by hand after cloning** — the rendered output is not in the repository); can also be run manually any time.
```
$ playbook sync
✓ Loaded config (engine 0.4.0, overlay bnp 0.2.0)
✓ Detector cache valid (pyproject.toml unchanged since last sync)
✓ Resolved 18 artifacts (3 overlay overrides, 1 repo-local)
✓ Filtered to 14 applicable artifacts
✓ Rendered all artifacts
✓ Wrote 12 files via continue adapter
✓ Wrote 5 files via claude_code adapter
✓ Wrote 5 files via opencode adapter
✓ Wrote 1 file via agents_md adapter
✓ Removed 0 stale files
✓ Updated .coding-agent-playbook.lock
Updated the managed block in .gitignore
Summary: 23 files written, 0 unchanged, 0 removed
```
After the lockfile is stamped, write mode applies the output policy (§4.2 step 9). With `commit = false` it rewrites the managed `.gitignore` block (§5.3) from this run's written paths — printing `Updated the managed block in .gitignore` only when the file actually changed — and then asks git, read-only, whether any generated path (or the lockfile) is **still tracked**, e.g. in a repo migrating from committed output. If so it warns on stderr and prints the exact command to stop tracking them; the exit code stays 0 and the engine never runs it itself:
```
warning: generated output is still tracked by git, but [output] commit = false
keeps it local-only (gitignored). Tracked paths:
  .claude/CLAUDE.md
  AGENTS.md
Stop tracking them (the files stay on disk) with:
  git rm -r --cached -- .claude/CLAUDE.md AGENTS.md
```
The query is `git --literal-pathspecs ls-files -z -- <paths>` (arg-list, no shell, `cwd` = repo root, 10 s timeout) behind the injectable `GitClient` protocol (`git_client.py`; tests use a `FakeGitClient`). Not a git repository, git missing, or a timeout → the warning is skipped silently. Deciding whether a *leftover* is tracked is stricter (§4.2 step 9): it asks with `:(literal,icase)` pathspecs, confirms each match by NFC spelling or file identity, and when git cannot answer inside a git work tree it keeps every leftover — it never reads "unknown" as "untracked". The paths are relative to the repo root, so when that is not the current directory (`playbook sync --repo-root packages/foo` from a monorepo root) the printed command is `git -C <repo-root> rm -r --cached -- …`. Before the block is written, leftovers of an earlier sync are settled from the previous lockfile (§4.2 step 9): pristine, untracked orphans are deleted and counted in `removed`; the rest are carried forward in the lockfile and kept in the block. A `ConfigError` (§7.1) exits 2 before anything runs. If a package in `overlays_enabled` is not importable or ships no `resources/` directory, `sync` prints `error: overlay package(s) in overlays_enabled are not usable here:` with one `<name>: <reason>` line per package (plus the bundled-pack list for a pack-like typo, §11.5) and the fix (§13.1), and exits 1 before writing anything; a missing adapter is a `warning:` and the run continues. With `commit = true` write mode removes the managed block instead (`Removed the managed block from .gitignore`); it settles leftovers by the same policy (asking git only when there are leftovers to judge) and lists every kept one on stderr (`note: kept output an earlier sync wrote …`), since a committed — tracked — leftover is never deleted. A malformed block (unmatched or duplicated markers) makes `sync` print `error: <file>:<line>: …` and exit 1 after the outputs and lockfile are written, without touching `.gitignore`.
### 12.3 `playbook sync --check`
Verify, don't write. Exits non-zero on drift. Under `[output] commit = true` it is the CI and legacy pre-commit check: the output is committed, so a fresh checkout has everything to compare. Under the default `commit = false` the output is **not in the repository**, so `--check` only makes sense in a working copy where `playbook sync` has already run (it then also reports a stale, missing, or malformed managed `.gitignore` block, and a not-yet-settled leftover, as drift; `--check` never writes `.gitignore`). Do not run it on a fresh CI clone under `commit = false` — every generated file reports "Missing on disk"; running `playbook sync` first would make it vacuous. CI for such repos validates the source instead (`playbook validate`).
```
$ playbook sync --check
✗ Drift detected:
  .continue/rules/50-python-typing.md
    Generated content differs from on-disk content.
    Run 'playbook sync' to regenerate.
  .gitignore
    Managed block is missing or stale ([output] commit = false).
    Run 'playbook sync' to regenerate.
exit code: 1
```
Implementation: the render reads its inputs (config, detector facts, artifacts, `applies_if` file checks) from the real repo but the adapters write into an **empty** scratch directory named like the repo — nothing from the working tree is copied, so a dangling symlink, an unreadable data directory, a socket/FIFO, or a large `.venv` can neither crash nor slow the check, and the real tree is never written. Skill-dir ownership is decided against the real tree, not the empty scratch (§10.8), so a skill dir write mode skips — hand-written with a colliding id, a symlink, a plain file, an unusable skills root — is skipped in the render too, and nothing the adapters render depends on what else is on disk (the `agent_harness` `HARNESS.md` index lists what it emits, §10.7.3). So after a successful `playbook sync`, `--check` exits 0 — with one documented exception: a file/folder swap inside a skill dir that `sync` refused because files it may not delete are in the way (a user file, an edited or tracked copy, §10.8). That destination stays missing, and `--check` reports it as `Missing on disk: <blocker> is in the way …`, telling the user to move those files rather than to re-run `playbook sync` (which cannot fix it); under `commit = true` the legacy `playbook-sync-check` hook fails until they do. Scratch paths are mapped back onto the real tree before ignore entries are computed, so a symlinked output directory (e.g. `.claude/skills -> ../.agents/skills`) yields exactly the entries write mode writes. The scratch output is then diffed against the repo.
#### 12.3.1 `playbook sync --check-staged`
The `[output] commit = false` commit guard (pre-commit stage). It renders into an empty scratch directory exactly like `--check` (no writes, no working-tree copy; skill-dir ownership judged on the real tree, so files in a hand-written skill dir are never flagged), asks git for the staged paths — `git diff --cached --name-only -z --relative --no-renames --diff-filter=d`, so staged *deletions* (the `git rm --cached` migration) never trip it — and exits 1 listing every staged path covered by an entry for this render's output **or for any leftover of an earlier sync still on disk** (every orphan in the previous lockfile, pristine or not), including files under a collapsed skill directory. Paths are matched in Unicode NFC on both sides:
```
$ playbook sync --check-staged
Generated output is staged for commit ([output] commit = false keeps it local-only):
  AGENTS.md
  .claude/skills/review/scripts/run.sh
Unstage it (the files stay on disk) with:
  git rm -r --cached -- AGENTS.md .claude/skills/review/scripts/run.sh
exit code: 1
```
Exit 0 when nothing generated is staged, when nothing is staged at all (fast path: no render), when the directory is not a git repository (or git is unavailable), and always under `commit = true` (no-op). Exit 1 with an `error:` (not a staged-path list) when an overlay package is unusable (§4.2 step 1). A `ConfigError` (§7.1) exits 2 even under `commit = true`: the config is loaded before the no-op decision, and a config the engine would misread must never pass silently. `--check` and `--check-staged` are mutually exclusive.
### 12.4 `playbook check`
Diagnostic dump. No writes. Used to debug "why isn't my rule appearing?"
```
$ playbook check
=== Environment ===
  Python: 3.12.1
  Package manager: uv
  Engine: coding-agent-playbook 0.4.0
  Overlays: playbook-rules-bnp 0.2.0
=== Detected ===
  project_kind: python-application
  frameworks: fastapi=0.115.0, pydantic=2.9.2, sqlalchemy=2.0.35, pytest=8.3.3
  has_notebooks: False
  has_dockerfile: True
  has_ci: True
=== Artifacts ===
  Rules (14 applicable / 18 total):
    [✓] 00-project-context         (engine, scope=always)
    [✓] 10-python-house-style      (engine, scope=always)
    [✓] 20-tooling-baseline        (engine, scope=always)
    [✓] 30-bnp-banking             (overlay bnp, scope=always)
    [✓] 50-python-typing           (overlay bnp OVERRIDES engine, scope=scoped)
    [✓] 60-fastapi                 (engine, scope=scoped)
    [✓] 70-pydantic-v2             (engine, scope=scoped)
    [✓] 70-sqlalchemy-v2           (engine, scope=scoped)
    [✗] 70-notebooks               (skipped: has_notebooks=False)
    [✗] 70-data-validation         (skipped: applies_if has_framework=['great-expectations'])
    ...
  Prompts (5 applicable / 7 total):
    [✓] refactor                   (includes_rules: [python-typing])
    [✓] generate-tests             (includes_rules: [python-typing, pytest])
    [✓] review                     (includes_rules: [python-typing, python-error-handling])
    [✓] explain
    [✓] pii-scan                   (from overlay bnp; includes_rules: [pii-handling])
    [✗] tdd-cycle                  (skipped: applies_if has_framework=['hypothesis'])
    ...
=== Drift ===
  All on-disk files match generated output ✓
```
Each overlay in `overlays_enabled` that `playbook sync` would refuse (the shared `_sync_preflight.unusable_overlays` check, §4.2 step 1: its import fails or it has no `resources/` directory) is flagged right under the `Overlays:` line, one `✗` line each, and the Drift section then never claims a clean state — a lockfile that matches the disk only describes what the last sync wrote, and no sync can run now:
```
  Overlays: coding_agent_playbook.packs.superpower
    ✗ coding_agent_playbook.packs.superpower: not importable (bundled packs: coding_agent_playbook.packs.superpowers)
    'playbook sync' refuses to run until every overlay in overlays_enabled is usable; the artifacts below omit the unusable ones.
…
=== Drift ===
  On-disk files match the lockfile, but the state is not clean:
  'playbook sync' refuses to run until every overlay in overlays_enabled is usable (see Environment).
```
`playbook check` is a diagnostic: it exits 0 whatever it reports, drift included, as before; `playbook validate` (§12.6) and `playbook sync` are the gates that exit non-zero. A `ConfigError` (§7.1) is the exception — the config cannot be loaded, so `check` (and `check --refresh`, which then writes nothing) exits 2 with `error: …`; §12.5 adds the cases where only `--refresh` refuses.
### 12.5 `playbook check --refresh`
Re-runs the detector and writes the fresh facts back to `.coding-agent-playbook.toml`, prints `Refreshed detector_cache in .coding-agent-playbook.toml.`, then the §12.4 report. Use after adding a dependency.

It rewrites only `[detector_cache]` (whole, so a stale entry goes; appended when absent), from the committed file alone (`commands/_committed_config.plan_detector_cache_refresh`). The committed table is written back as parsed with that one entry replaced — not through `Config`, as an `init` re-run does — so every other key, managed or not (`adapters_enabled`, `[output]`, `[user_choices]`, `[links]`, `[metrics]`, `[project] homepage`, …), keeps its committed value as written: an explicit `adapters_enabled = []`, `description = ""` or empty `[user_choices]` stays, and a partial `[storage]` or an `[output]` without `commit` is not filled in. Nothing from `.coding-agent-playbook.local.toml` is written (§7.2). Before v0.18 it saved the merged config, which committed the local overrides and deleted `[links]`/`[metrics]`. The file is re-serialized by the same writer as an `init` re-run (§12.1): values survive, comments and layout do not, and a literal comes back in the writer's spelling. It exits 2 with `error: …`, writing and printing nothing, when the config cannot be loaded (§7.1), when the committed file alone lacks a required key (even one the local file supplies — plain `check` and `sync` still run on the merged config), or when the local file merged over the refreshed config would not load.
### 12.6 `playbook validate`
Validate canonical sources without rendering. Used in the engine's own CI and by overlay authors.
```
$ playbook validate
✓ 18 artifacts loaded from 2 sources
✓ All frontmatter valid against schema
✓ All Jinja templates compile
✓ All `includes_rules:` references resolve
✓ All `{{ rule() }}` calls match `includes_rules:` declarations
✓ All `eval_tasks:` references resolve to existing tasks
✓ All task `prompt_id` back-references match a prompt's `eval_tasks:` list
✓ All markdown links self-contained (relative targets resolve; externals allowlisted)
✓ All skills are valid Agent Skills (string id declared, id/name matches ^[a-z0-9]+(-[a-z0-9]+)*$, description present)
✗ overlays_enabled: coding_agent_playbook.packs.superpower: not importable (bundled packs: coding_agent_playbook.packs.superpowers)
✗ rules/frameworks/sqlalchemy-v2.md.j2: applies_if references unknown fact 'orm_version'
✗ prompts/refactor.md.j2: body calls `{{ rule("python-style") }}` but rule not in includes_rules
✗ rules/languages/python/typing.md.j2: body calls `{{ rule(...) }}` — rules cannot include other rules
✗ eval_tasks/orphan-task/task.toml: prompt_id 'deleted-prompt' does not exist
✗ prompts/generate-tests.md.j2: declares eval_task 'foo-bar' but eval_tasks/foo-bar/ not found
✗ rules/languages/python/typing.md.j2: markdown link 'style.md' (line 12): target 'style.md' does not exist in the artifact set
✗ prompts/review.md.j2: markdown link 'https://blog.example.com/x' (line 4): external link to host 'blog.example.com' is not in [links] allowed_domains
✗ skills/My_Skill (<repo-local>): skill id 'My_Skill' is not a valid Agent Skills name (must match ^[a-z0-9]+(-[a-z0-9]+)*$); OpenCode silently skips it
✗ skills/query-db (<repo-local>): skill has no 'description'; Agent Skills requires a non-empty description
✗ skills/<no id; name 'pdf-tools', at playbook/skills/pdf-tools> (<repo-local>): skill has no 'id'; it is emitted as 'skill' and collides with every other id-less skill (declare 'id:' in its SKILL.md frontmatter)
exit code: 1
```
The sample is stylized: the command prints `OK <N> artifacts validated` when it passes, and otherwise one `FAIL <path>: <message>` line per error followed by `validation failed with <N> error(s)`.

The self-contained-links rule (PR L, design in `specs/prL-markdown-links.md`) covers rule bodies, prompt bodies, and skills (`SKILL.md` + every markdown file under `references/`) across all three source layers. Extraction masks frontmatter, fenced code blocks, and inline code spans (code examples like `def first[T](items: list[T])` are not links); Jinja-bearing targets are skipped as not statically checkable. Relative targets must resolve — `other.md` is satisfied by a canonical `other.md.j2` since rendering drops the suffix — and must stay inside the artifact's source layer; `http(s)` targets pass only via `[links] allowed_domains` (§7.1); every other scheme and absolute paths are violations. Deterministic by construction: stdlib only, no network. The engine's own shipped artifacts are enforced on CI by a pytest integration test (`tests/cli/test_validate_links.py`); consumer repos and overlays inherit the rule through `playbook validate`.

The overlay rule (v0.17) runs the sync preflight's own check (`_sync_preflight.unusable_overlays`, §4.2 step 1) over `overlays_enabled`: one error per package whose import fails (the reason quotes the error when the package exists but raises), or that imports with no `resources/` directory, printed as `FAIL overlays_enabled: <name>: <reason>` (with the bundled-pack list for a pack-like typo, §11.5) and counted in the exit-1 `validation failed with <N> error(s)` summary. Before v0.17 `validate` skipped such a package silently (its artifacts were simply absent) and exited 0 on a config every `sync` mode refuses. A `ConfigError` (§7.1) is not a validation error: the config cannot be loaded, so `validate` exits 2 with `error: …` before checking anything.

The Agent Skills rule (v0.15) checks every resolved skill: it must declare a string `id` (§6.3), its id — emitted as the `SKILL.md` `name` and the output directory — must match `^[a-z0-9]+(-[a-z0-9]+)*$` and be at most 64 chars, and it must carry a `description` of 1–1024 chars. OpenCode silently drops a skill that breaks either name/description constraint, so authors learn here instead of at runtime. Id-less skills all merge under the fallback id `skill` (all but one silently dropped), so they are checked from the **pre-merge** list and each one is reported. Skills carry no source path, so errors are reported as `skills/<id> (<source package>)`, or — for an id-less skill — by its authored `name` plus, when it has `scripts/`/`references/`, its source directory.
### 12.7 `playbook render` (debug)
Render a single artifact to stdout for debugging. Does not write.
```
$ playbook render python-typing --format continue
[full rendered .continue/rules/50-python-typing.md to stdout]
$ playbook render python-typing --format claude_md_section
[the CLAUDE.md section that would be emitted]
$ playbook render python-typing --show-source
Template:  playbook_rules_bnp/resources/rules/languages/python/typing.md.j2
Format:    .md.j2 (Jinja-templated)
Overrides: coding_agent_playbook/resources/rules/languages/python/typing.md.j2
Adapters:  continue, claude_code, agents_md
           (opencode reads rules via AGENTS.md natively — no direct render)
applies_if evaluated: True
$ playbook render generate-tests --show-rules
Prompt:    generate-tests
includes_rules:
  - python-typing       (overlay bnp, applies_if=True → INLINED)
  - pytest              (engine, applies_if=True → INLINED)
  - python-style        (engine, applies_if=False → OMITTED)
Inclusion mode: explicit ({{ rule() }} calls in body)
```
### 12.8 `playbook eval` (Tier 0 enumeration + the v1.1 `--run` runner)
`playbook eval` is a read-only enumeration of the prompt-to-task graph and — with `--run` (v1.1 PR R1) — the entry point that *executes* one task end-to-end through a `HarnessRunner` and grades it (§15.3). Without `--run`, the bare `playbook eval <id>` prints how to run the task (exit 0; example below).
```
$ playbook eval --list
=== Eval tasks ===
generate-tests (engine)
  ├── generate-tests-happy-path        ✓ task defined
  │   └── 4 rubric criteria, 4 gate checks
  ├── generate-tests-edge-cases        ✓ task defined
  │   └── 5 rubric criteria, 4 gate checks
  └── generate-tests-async-code        ✓ task defined
      └── 3 rubric criteria, 2 gate checks
refactor (engine)
  └── refactor-extract-helper          ✓ task defined
      └── 3 rubric criteria, 2 gate checks
review (engine)
  └── (no eval tasks declared)         ⚠ consider adding tasks
pii-scan (overlay bnp)
  └── pii-scan-detects-iban            ✓ task defined
      └── 2 rubric criteria, 1 gate checks
Total: 5 prompts, 5 eval tasks, 1 prompt without tasks
```
`playbook eval --list` walks the prompt registry, reads each prompt's `eval_tasks:`, and reports coverage. The "no eval tasks declared" warning is informational, not a `playbook validate` failure — eval tasks are recommended, not required.
```
$ playbook eval --show generate-tests-happy-path
Task: generate-tests-happy-path
Source: coding_agent_playbook/resources/eval_tasks/generate-tests-happy-path/
Prompt under test: generate-tests
Description: Generate tests for a simple pure function with no edge cases
Setup:
  Mock facts: python_version=3.12, frameworks=[pytest, pytest-asyncio]
  Files (1): src/calculator.py
Invocation:
  Prompt: /generate-tests
  Args: "for the add function in src/calculator.py"
  Variables: target=src/calculator.py::add
Gate (deterministic, 4 checks, expr: test_created and names_test and parametrized and src_unchanged):
  - test_created: check file_exists tests/test_calculator.py
  - names_test: check file_contains tests/test_calculator.py ~/def test_add/
  - parametrized: check file_contains tests/test_calculator.py ~/parametrize/
  - src_unchanged: check file_unchanged src/calculator.py
Rubric (manual / LLM-judge, 4 criteria):
  - 0.2: Tests use pytest.parametrize for table-driven cases
  - 0.2: Test file lives at tests/test_calculator.py (mirror layout)
  - 0.4: All public branches of `add` are covered
  - 0.2: No mocking is used (the function is pure)
Verdict: gate and rubric
```
```
$ playbook eval generate-tests-happy-path
playbook eval generate-tests-happy-path:
Add --run to execute this task against an agent and grade it:
  playbook eval generate-tests-happy-path --run --runner fake    # hermetic no-op agent, no CLI
  playbook eval generate-tests-happy-path --run                  # default runner: claude_code
  playbook eval generate-tests-happy-path --run --judge llm      # also score the [rubric] layer
Inspect it with `playbook eval --show generate-tests-happy-path`; coverage: `playbook eval --list`.
To run it by hand, copy setup/ to a scratch repo and invoke /generate-tests.
exit code: 0
```
(The bare `playbook eval <id>` path prints how to run the task and exits 0 — the runner is not invoked without `--run`, so `playbook eval <id>` stays a cheap existence check.) To actually execute a task, add `--run`:
```
$ playbook eval refactor-extract-helper --run --runner fake [--judge llm] [--samples N] [--format text|json]
```
- **`--runner NAME`** selects a runner from the `coding_agent_playbook.runners` entry-point group; the default is **`claude_code`** (the real runner). Use `--runner fake` for a hermetic, no-network demo/CI run.
- **`--judge NAME`** selects a judge from the `coding_agent_playbook.judges` group to score the task's `[rubric]` layer too. The shipped judge is **`llm`** (`LLMJudge`, shells out to the `claude` CLI, `available()`-gated, never in CI). **Omitting `--judge` is deterministic-only** — no `ProgrammaticOnlyJudge`, just no judge configured ⇒ the `[rubric]` layer skips (a skipped layer is neutral in the derived verdict). **`--samples N`** (default 1) is the per-criterion sample count the judge averages.
- The task's `[gate]` layer (file checks + static/execution metric checks, 0–1 normalized non-regression) is scored deterministically into one `EvaluationReport`, rendered with the same text/json renderer as `playbook metrics`. With `--judge` set, the `[rubric]` layer's judged scores fold into the same report; the per-trial verdict is then derived from the two layers' results via `[verdict].trial`.
- **`--full-scoring`** forces every check to run (no short-circuit), for a complete report even when a cheap gate check has already failed.
- **There is no `--run-tests` flag.** Unlike `playbook metrics`, execution intent is *inferred*: a task runs the suite iff its `[gate]` references an execution metric (`coverage` / `test_pass_rate`), so the task — not a CLI flag — decides whether the execution checks run.
- **Exit codes:** `0` on a passing report (the task verdict holds), `1` on a failing report, `2` on usage errors — unknown task id, unknown `--runner`, a runner that is unavailable in this environment (e.g. `claude_code` with no `claude` CLI on `PATH` — the error suggests `--runner fake`), an unknown or unavailable `--judge` (e.g. `llm` with no `claude` CLI), or a bad `--format` — and when the task **cannot be scored at all**: its prompt fails to render (`PromptResolutionError`), or the judge gives no score after its bounded retries (`JudgeError`: the CLI exited non-zero, timed out, or did not answer with exactly one number in `[0, 1]`). An unscored task is neither a pass nor a fail, so it never exits `0`/`1`.
- **Judged scores are labelled uncalibrated.** Whenever a judged check ran, the text report adds a note and the JSON carries `"uncalibrated_judge": true`, until judge calibration (§19 Q12) exists.
### 12.9 `playbook import-harness`
Parse an Agent Harness tree back into canonical artifacts and write them into an overlay directory (default `./playbook/`) in the `FileSystemArtifactSource` layout, so a later `playbook sync` re-reads them. The reverse of the `agent_harness` adapter (§10.7).
```
$ playbook import-harness ./vendor/some-harness
imported 6 artifact(s) into /repo/playbook (3 rules, 2 prompts, 1 skills)
```
Two fidelity tiers, picked automatically (`specs/prH-agent-harness.md` §C):
- **Lossless** — when a `.playbook/manifest.toml` sidecar is present (a playbook-emitted harness): every artifact is rebuilt from the manifest's full reconstruction payload (full frontmatter incl. rule `name`, the un-rendered source body, `is_templated`, per-script `executable` bit), independent of how the leaf rendered or inlined content. Script exec bits are restored on POSIX, no-op on Windows.
- **Best-effort** — no sidecar (a foreign harness): kinds are inferred from directory placement (`skills/*` → `Skill`, `prompts/*` → `Prompt`, `rules/*.md` → `Rule` scope=always, `references/*.md` → `Rule` scope=scoped, non-markdown → opaque asset). Non-native fields are defaulted and every lossy assumption is reported as a `warning:` on stderr — the importer never silently guesses.
```
$ playbook import-harness ./vendor/foreign-harness --into playbook
warning: no .playbook/manifest.toml sidecar found; reconstructing best-effort. ...
warning: rule 'pep8': scope inferred as 'always' from rules/ placement; globs/applies_if/priority/tags/version not recoverable without sidecar
imported 2 artifact(s) into /repo/playbook (2 rules, 0 prompts, 0 skills)
```
All reconstructed rules — `scope=always` *and* `scope=scoped` — are written under `<into>/rules/<id>.md` (the only directory `FileSystemArtifactSource.list_rules()` reads); `scope` is preserved in the rule's emitted frontmatter, so a scoped rule stays scoped without needing a separate directory. Exit code is 2 on a usage error (missing/non-directory path, or no `HARNESS.md`), else 0.
### 12.10 `playbook validate-harness`
Run `harnesses-ref`-equivalent structural checks on an Agent Harness tree (emitted or foreign). This is the lint half of the client-runtime decision (§10.7 / decision #3): the playbook validates harness *structure*, it does not implement a harness client runtime.
```
$ playbook validate-harness ./build/harness
OK harness validated (0 warning(s))
exit code: 0
```
Checks:
- **Errors** (non-zero exit): `HARNESS.md` present with non-empty `name` and `description`; every detected skill leaf carries a non-empty `name` and `description`.
- **Warnings** (exit 0 by default; promoted to errors by `--strict`): a grouping subdirectory lacks its routing file (`<DIR>.upper() + ".md"`); a content `.md` lacks a `description`.
```
$ playbook validate-harness ./build/harness --strict
warning: /build/harness/skills: grouping directory lacks its routing file 'SKILLS.md'
validation failed with 0 error(s), 1 warning(s) (warnings promoted by --strict)
exit code: 1
```
A missing or malformed `HARNESS.md` is reported as a validation **error** (exit 1) — not a usage error (exit 2) — because for a validator a malformed harness is precisely the failure it exists to report. Directories marked opaque by a `.harnessleaf` marker are terminal leaves: the validator never expects a routing file for them and does not inspect their internal content.
## 13. Pre-commit integration
### 13.1 The engine's `.pre-commit-hooks.yaml`
Shipped at the root of `coding-agent-playbook` so consumers can reference it. The first two hooks implement the default `[output] commit = false` policy; `playbook-sync-check` is the **legacy** hook, only for repos that set `commit = true`:
```yaml
# .pre-commit-hooks.yaml (inside the engine repo)
- id: playbook-sync
  name: coding-agent-playbook sync (regenerate local output)
  description: Re-render the gitignored AGENTS.md/.claude/.continue/.opencode output after checkout or merge
  entry: playbook sync
  language: python
  pass_filenames: false
  always_run: true
  stages: [post-checkout, post-merge]
  minimum_pre_commit_version: "3.2.0"
- id: playbook-no-generated-output
  name: coding-agent-playbook guard (no generated output staged)
  description: Fail the commit when any staged path is gitignored generated output ([output] commit = false)
  entry: playbook sync --check-staged
  language: python
  pass_filenames: false
  always_run: true
  stages: [pre-commit]
  minimum_pre_commit_version: "3.2.0"
# LEGACY — only for [output] commit = true (generated output is committed).
- id: playbook-sync-check
  name: coding-agent-playbook sync check (legacy, [output] commit = true)
  description: Verify committed .continue/, .claude/, AGENTS.md are in sync with the installed playbook
  entry: playbook sync --check
  language: python
  pass_filenames: false
  always_run: true
- id: playbook-validate
  name: coding-agent-playbook validate (overlay authors)
  description: Validate canonical artifacts (only run when authoring an overlay)
  entry: playbook validate
  language: python
  pass_filenames: false
  always_run: true
  stages: [manual]
```
(`playbook-metrics`, the static code-quality gate, is listed in §21.5.) Stage names are pre-commit's hook-type names (`pre-commit`, `post-checkout`, `post-merge`, …; verified against pre-commit 4.7.0's `clientlib.STAGES`), introduced in pre-commit 3.2.0 — hence `minimum_pre_commit_version`. `post-checkout`/`post-merge` hooks receive no filenames, so `always_run: true` is required for them to run at all. A consumer wiring the default policy installs all three hook types (`pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge`; explicit `--hook-type` flags *replace* `default_install_hook_types`, so all three must be named):
```yaml
# consumer .pre-commit-config.yaml
default_install_hook_types: [pre-commit, post-checkout, post-merge]
default_stages: [pre-commit]     # keep other always_run hooks off checkout/merge
repos:
  - repo: https://github.com/msobroza/coding-agent-playbook
    rev: v0.1.0a0                # the engine version the project pins
    hooks:
      - id: playbook-sync
        additional_dependencies: [playbook-rules-bnp]   # every overlay / out-of-tree adapter
      - id: playbook-no-generated-output
        additional_dependencies: [playbook-rules-bnp]
```
**These hooks run in pre-commit's own venv.** `language: python` means pre-commit builds an isolated environment holding only the engine at `rev:` — not the project's environment. An overlay package or out-of-tree adapter must therefore be listed under `additional_dependencies` (and `rev` kept on the engine version the project pins, or hook runs and manual runs render with different engines). Without it the sync refuses to run (missing overlay, §4.2 step 1) or skips the adapter with a warning — it never silently re-renders without the org rules. Overlay users (and anyone pinning the engine in their project environment) should prefer the `repo: local` + `language: system` hooks `playbook init` writes (§13.2), which run the project's own `playbook`.
### 13.2 Template `.pre-commit-config.yaml` (written by `playbook init`)
`playbook init` renders this starter from the packaged template `resources/precommit/config.yaml.j2`. It is **air-gapped-friendly**: every hook is `repo: local` + `language: system`, so pre-commit never clones a remote hook repo (it would otherwise fetch each `repo:` URL into `~/.cache/pre-commit` on first run — impossible offline, which also satisfies the engine's "air-gapped-friendly" invariant). The tradeoff is that the consumer must have `ruff` and `mypy` installed in their environment; `language: system` runs the tools on PATH, it does not install them. The template is rendered with one variable, `output_commit` (the `[output] commit` policy), which selects the playbook hooks — the default `commit = false` variant is shown:
```yaml
# AUTOGENERATED starter by coding-agent-playbook `playbook init`.
# Air-gapped-friendly: all hooks are `repo: local` + `language: system`.
# Requires ruff and mypy installed in your environment.
minimum_pre_commit_version: "3.2.0"
default_install_hook_types: [pre-commit, post-checkout, post-merge]
default_stages: [pre-commit]
default_language_version:
  python: python3.12
fail_fast: false
repos:
  - repo: local
    hooks:
      # The playbook — re-render the local-only output after checkout / merge
      - id: coding-agent-playbook-autosync
        name: coding-agent-playbook sync (regenerate local output)
        entry: playbook sync
        language: system
        pass_filenames: false
        always_run: true
        stages: [post-checkout, post-merge]
      # The playbook — refuse commits that stage generated output
      - id: coding-agent-playbook-no-generated-output
        name: coding-agent-playbook guard (no generated output staged)
        entry: playbook sync --check-staged
        language: system
        pass_filenames: false
        always_run: true
        stages: [pre-commit]
      # The playbook — static code-quality gate (§21.5)
      - id: coding-agent-playbook-metrics
        name: coding-agent-playbook metrics (static)
        entry: playbook metrics --baseline git:HEAD
        language: system
        types_or: [python, pyi]
        require_serial: true
      # Linting and formatting (ruff must be installed)
      - id: ruff
        name: ruff (lint + autofix)
        entry: ruff check --fix
        language: system
        types_or: [python, pyi]
        require_serial: true
      - id: ruff-format
        name: ruff format
        entry: ruff format
        language: system
        types_or: [python, pyi]
        require_serial: true
      # Type checking (mypy must be installed)
      - id: mypy
        name: mypy
        entry: mypy --config-file=pyproject.toml
        language: system
        pass_filenames: false
        always_run: true
```
`default_install_hook_types` makes a plain `pre-commit install` install the `post-checkout`/`post-merge` git hooks the auto-sync needs; `default_stages: [pre-commit]` keeps every hook without an explicit `stages` (notably the `always_run` mypy hook) from also running after each checkout/merge — pre-commit's default is *all* stages. With `[output] commit = true` the template instead renders the legacy `coding-agent-playbook-sync` hook (`entry: playbook sync --check`, every commit) and omits those three top-level keys.

Intentionally **not** shipped in the starter: generic-hygiene hooks (trailing-whitespace, end-of-file-fixer, check-yaml/-toml, detect-private-key, check-merge-conflict, check-added-large-files), secret scanning (gitleaks), and notebook hooks (nbstripout/nbqa) — all of which require cloning a remote repo. `ruff format` already covers Python whitespace/EOF; a pre-push `pytest` hook can be added by the consumer as a `repo: local` entry if desired.
### 13.3 Merge with existing `.pre-commit-config.yaml`
If the consumer already has a config, `playbook init` appends only our playbook `- repo: local` hook block for the configured policy — the `coding-agent-playbook-autosync` + `coding-agent-playbook-no-generated-output` pair for `commit = false` (deduplicated on the guard's id), the legacy `coding-agent-playbook-sync` drift check for `commit = true` — and only when it is not already present. It never injects ruff/mypy into a config the consumer already curates, and it does not add top-level keys (`default_install_hook_types`, `default_stages`) to a file it does not own: the consumer installs the extra hook types with `pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge` (which `init` prints) and should confine their own `always_run` hooks with `stages:`/`default_stages`. A legacy `coding-agent-playbook-sync` hook (`playbook sync --check`) left over from before v0.16 is **swapped in place** for the `commit = false` pair when it is still byte-for-byte what `init` wrote (in the old starter or the old appended block) — it would otherwise report drift after every checkout/merge, since the output is no longer committed. A hand-edited one is left alone and `init` prints a `warning:` telling the user to delete it. When the merged config has no `default_stages`, `init` also prints a `note:` that the consumer's own `always_run` hooks need `stages: [pre-commit]` (or `default_stages: [pre-commit]`) before the `post-checkout`/`post-merge` hook types are installed. The current implementation is a text-based append; round-trip merging with `ruamel.yaml` (to preserve comments/ordering and surface version conflicts, e.g. a different ruff pin) can land later.
## 14. Distribution and versioning
### 14.1 Channels
- **Engine and overlays**: distributed via internal PyPI (Artifactory). No public PyPI for v1.
- **Pre-commit hooks**: distributed via internal git server.
### 14.2 Versioning contract
SemVer applied to the **rendered output format**, not the Python API:
- **Patch** (`0.4.0 → 0.4.1`): rule wording improvements, bug fixes, no consumer action needed.
- **Minor** (`0.4.0 → 0.5.0`): new rules or prompts added, new optional features. Consumer re-runs `playbook sync`. Under `[output] commit = true` they review the regenerated diff; under the default `commit = false` the output is local-only, so the review happens on the engine/overlay release (its changelog and diff), or by comparing a local `playbook sync` before and after the bump.
- **Major** (`0.4.0 → 1.0.0`): breaking changes to artifact schema, adapter contract, or CLI surface. Consumer follows a migration guide.
### 14.3 Pinning policy
Consumers pin to a minor range: `coding-agent-playbook>=0.4.0,<0.5.0`. Overlays pin to the engine's minor range. Under `[output] commit = true`, Dependabot / Renovate bumps trigger a `playbook sync` and the regenerated diff lands in the PR for review. Under the default `commit = false` the PR only carries the dependency bump (rendered output is gitignored): reviewers read the engine/overlay release notes, or render locally before and after the bump.
### 14.4 Lockfile
`.coding-agent-playbook.lock` is a TOML file with:
```toml
schema_version = 1
engine_version = "0.4.0"
[overlay_versions]
playbook_rules_bnp = "0.2.0"
[file_hashes]
".continue/rules/00-project-context.md" = "sha256:abc123..."
".continue/rules/10-python-house-style.md" = "sha256:def456..."
# ... one entry per generated file
"AGENTS.md" = "sha256:..."
```
`playbook sync --check` recomputes the hashes and compares. Mismatch → drift → exit 1. Under the default `[output] commit = false` the lockfile is local state like the output it describes: it is always listed in the managed `.gitignore` block (`/.coding-agent-playbook.lock`) and never committed. The consumer's `.gitignore` is never a lockfile entry — it is a user file the engine only edits inside its managed block.
## 15. Eval abstractions
v1 shipped **Tier 0**: the task authoring format (Section 6.5), the loader, the validator, and a read-only CLI. **v1.1 makes Tier 1 live**: `HarnessRunner` executes one task end-to-end against an agent and scores it through the `Metric` / `Check` / `Rubric` model (§21). The **task-config redesign (v0.13, Tracks C1–C8)** then reshaped the *authored* format into the layered `[gate]` / `[rubric]` / `[verdict]` / `[aggregate]` model (§6.5.3): a task compiles into one per-trial `Rubric` of checks whose deterministic `[gate]` layer (file/metric checks, 0–1 normalized thresholds + non-regression vs the `setup/` baseline) is computable today, and whose judged `[rubric]` layer scores against the captured diff when a judge is configured (`--judge llm`, or any `coding_agent_playbook.judges` entry). With **no judge configured** the runner is deterministic-only (the rubric layer reports `available() is False` and is skipped — the verdict treats a skipped layer as neutral). §15.3 describes the as-built v1.1 runner; the design docs are `specs/prR-eval-runner.md` (R1), `specs/prR2-judge-r3-opencode.md` (R2), `specs/prR6-check-rubric.md` (the R6 `Metric`/`Check`/`Rubric` refactor), and **`specs/pr2b-task-config.md`** (the task-config redesign).
### 15.1 The Tier 0 / Tier 1 / Tier 2 ladder
| Tier | Capability | status |
| --- | --- | --- |
| 0 | Task schema, loader, validator, `playbook eval --list/--show` | **shipped (v1)** |
| 1 | Per-runner agent invocation + deterministic scoring (the `[gate]` layer: file + metric checks, 0–1 normalized non-regression) via the `Metric`/`Check`/`Rubric` model | **shipped (v1.1 R1)** |
| 2 | The `[rubric]` llm-judge layer (LLM-as-judge) | **shipped (v1.1 R2)** — opt-in `LLMJudge` via `--judge llm`; calibration is future work |
The ladder is deliberate: Tier 0 produces value (documentation, validation) immediately. Tier 1 makes the value computable. Tier 2 closes the loop on subjective quality. Each tier is independently shippable.
### 15.2 v1 abstractions (active)
These ship in v1 and back the `playbook eval --list` / `playbook eval --show` CLI.
```python
# coding_agent_playbook/evals/task.py
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TaskSetup:
    files: list[Path]  # files in setup/ subdir, relative to task dir
    project_kind: str
    python_version: str
    frameworks: list[str]
    # Free-form facts the task wants the detector to mock.
    extra_facts: dict[str, object] = field(default_factory=dict)


@dataclass
class TaskInvocation:
    prompt_args: str  # what the user "types" after the slash command
    input_variables: dict[str, str] = field(default_factory=dict)


@dataclass
class Layer:  # one [gate] / [rubric] / [aggregate] block
    bind: dict[str, dict] = field(default_factory=dict)  # name -> raw handle binding
    expr: str | None = None  # boolean/aggregate expr over the handle names


@dataclass
class EvalTask:
    id: str
    prompt_id: str
    description: str
    source_path: Path  # where the task.toml lives
    source_package: str
    version: int = 1
    setup: TaskSetup = field(default_factory=TaskSetup)
    invocation: TaskInvocation = field(default_factory=TaskInvocation)
    gate: Layer | None = None  # the deterministic boolean layer
    rubric: Layer | None = None  # the llm-judge weighted layer
    verdict: str = "gate and rubric"  # [verdict].trial — boolean expr over the layers
    aggregate: Layer | None = None  # optional cross-trial pass@k / pass^k layer
```
The loader (`coding_agent_playbook.evals.loader.load_tasks`) walks `resources/eval_tasks/`, parses `task.toml` per directory, and produces a `list[EvalTask]`. Overlays add their tasks via the same entry-point mechanism as rules and prompts. `EvalTask.compiled()` (a thin wrapper over `evals._compile.compile_task`) turns the raw layer blocks into a `CompiledTask` — one per-trial `Rubric` (the present `gate`/`rubric` layer checks, ids `"gate"` / `"rubric"`), the parsed `[verdict].trial` AST, and the optional compiled `[aggregate]` layer + `trials_needed`.

The validator (`coding_agent_playbook.evals.validator.validate_tasks`) enforces:
- Each `task.toml` is well-formed (the loader parses it; a task reaching the validator already parsed).
- The `[gate]`/`[rubric]`/`[verdict]` schema **trial-compiles cleanly** — unknown `check`/`metric`/gate-`ref`/rubric-`ref`, a malformed handle binding, an `expr` identifier not in its `bind` keys, a rubric group's weights ≠ 1.0, a `[verdict].trial` naming an absent layer, or no layer at all.
- A light `[aggregate]` shape check (each handle names `pass_at_k`/`pass_pow_k`, an integer `k ≥ 1`, and an `over ∈ {gate, rubric, verdict}`).
- Each task's `setup.files` list matches files actually present in `setup/`.
- Each task's `prompt_id` resolves to a known prompt, and the prompt↔task back-reference is symmetric.

**Named-rubric / named-gate refs.** A handle may `{ref = "name"}` instead of inlining a check: in the **rubric** layer it resolves a *code-defined* rubric registered under `@register_rubric("code-review")` (`coding_agent_playbook.evaluators.rubrics` + the `coding_agent_playbook.rubrics` entry-point group), wrapped in a `ThresholdCheck` on its 0–1 composite; in the **gate** layer it resolves a *code-defined* composed gate registered under `@register_gate("name")` (`coding_agent_playbook.evaluators.gates` + the new `coding_agent_playbook.gates` group). A `Rubric` subclass declares its `CRITERIA = (("criterion", weight), …)`; `get_rubric(name)` returns `cls.define()` (a built `Rubric` of `JudgeCheck`s). The engine ships **no** builtin gates or rubrics — both are purely third-party extension points; in-tree registrations win on a name clash.

That's the entire active task surface.
### 15.3 The v1.1 runner (live — deterministic layers)
`HarnessRunner` is a concrete **template method**: `run_task` owns a fixed pipeline (materialize → render prompt → `_invoke_agent` → capture → score → assemble a `TaskResult`) and the single abstract per-assistant hook is `_invoke_agent`. Scoring runs through the `Metric` / `Check` / `Rubric` model (§21): the task's layer blocks compile (via `evals._compile.compile_task`) into one per-trial `Rubric` carrying the two named layer checks (ids `"gate"` / `"rubric"`), and a single `Rubric.evaluate` folds them into one report — so the deterministic `[gate]` layer (file checks + static/execution metric checks, 0–1 normalized non-regression vs the `setup/` baseline) is live. **The judged `[rubric]` layer is opt-in**: `run_task(task, scratch_dir, *, judge=None, samples=1, fail_fast=True)` takes an optional `Judge` (keyword-only) and threads it onto the `EvalContext`; with a judge set the rubric criteria score against the captured diff and fold into the same report, and with none (the default) the rubric layer reports `available() is False` and the report is deterministic-only. The per-trial **verdict** is then *derived* from the gate/rubric layer results (a skipped layer is neutral) via `[verdict].trial` — not re-run, so the judge / test-suite is never double-invoked. The cost-tiered scheduler (§21.4) runs checks cheapest-tier-first; `run_task` is **fail-fast by default** (a lost deterministic gate skips the costlier execution/judged tiers — for the default conjunction verdict `gate and rubric`, a failing gate check never spends an LLM call; a task whose verdict or aggregate a skipped layer could change is always scored in full, see `CompiledTask.short_circuit_safe`), and `playbook eval --run --full-scoring` forces every check to run. When the task carries an `[aggregate]` block the runner runs `N = max(k)` trials and the aggregate `pass@k` / `pass^k` checks reduce them into the task verdict (§21.2.5); omit it ⇒ a single trial.
```python
# coding_agent_playbook/evals/runner.py     (v1.1, live)
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
@dataclass
class AgentRun:
    transcript: str
    returncode: int                              # 0 = the agent loop completed
@dataclass
class TaskResult:
    task_id: str
    harness: str                                 # the runner's entry-point name, e.g. "fake", "claude_code"
    report: EvaluationReport                      # the per-trial Rubric.evaluate report (the gate + rubric layer checks)
    passed: bool                                  # the TASK verdict (derived [verdict].trial, or the [aggregate] pass/fail; if that is skipped, every trial passed)
    aggregate_score: float                        # report.composite (single-trial), or the aggregate reliability score (the trial pass rate if skipped)
    duration_seconds: float
    transcript: str                              # full agent transcript for debugging
    trials: list[TrialResult] = field(default_factory=list)   # one per trial (one for N=1)
    aggregate: CheckResult | None = None          # the graded [aggregate] check, when present
@dataclass
class EvalReport:                                 # aggregate over several tasks for one harness
    engine_version: str
    harness: str
    task_results: list[TaskResult]
    aggregate_pass_rate: float                    # mean of tr.passed across task_results
    timestamp: str
    @staticmethod
    def pass_rate(task_results: list[TaskResult]) -> float: ...   # mean(tr.passed), 0.0 when empty
class PromptResolutionError(RuntimeError):
    """A task's prompt could not be resolved (strict mode) or failed to render."""
class HarnessRunner(ABC):
    """Invoke an agent for one task and grade the result (template method)."""
    name: str                                    # the coding_agent_playbook.runners entry-point key
    requires_resolved_prompt: bool = False       # real runners set True (strict render_prompt)
    def run_task(self, task, scratch_dir, *, judge=None, samples=1, fail_fast=True) -> TaskResult:   # CONCRETE template
        baseline = materialize(task, scratch_dir)            # copy setup/ + git-init baseline commit + pristine snapshot
        prompt   = render_prompt(task, strict=self.requires_resolved_prompt)
        run      = self._invoke_agent(prompt, scratch_dir)   # ← the ONLY per-assistant step
        candidate = capture(scratch_dir, baseline, run.transcript)   # post-agent tree + git diff + transcript
        report   = score(task, baseline, candidate, judge=judge, samples=samples, fail_fast=fail_fast)  # one Rubric.evaluate (§15.3.1)
        return TaskResult(task_id=task.id, harness=self.name, report=report, ...)
    @abstractmethod
    def _invoke_agent(self, prompt: str, scratch_dir: Path) -> AgentRun:
        """Drive the agent against scratch_dir and return its raw outcome. The only per-assistant step."""
        ...
```
**Result model (Option B).** `TaskResult` carries one representative `report: EvaluationReport` (the first trial's, covering the `[gate]` / `[rubric]` layer checks) plus the convenience aggregates `passed` / `aggregate_score` / `duration_seconds` / `transcript`, and — for a multi-trial `[aggregate]` task — `trials` (every per-trial `TrialResult`) and `aggregate` (the graded aggregate `CheckResult`). `passed` is the **task** verdict: the single trial's derived `[verdict].trial` for a non-aggregate task, or the `[aggregate]` layer's pass/fail when the task aggregates across trials — unless that layer is skipped (its `over` axis ran in fewer than `k` trials, e.g. `over = "rubric"` with no judge): then `aggregate` is a `status="skipped"` result, `passed` holds only if every trial's verdict passed, and `aggregate_score` is the trial pass rate (§21.2.5). A gate predicate is a deterministic `Check` whose result rides on `report.checks`; `CheckResult` is the per-check outcome of `Check.grade`. `EvalReport.pass_rate` is the mean of `tr.passed`.

Concrete runners (discovered via the `coding_agent_playbook.runners` entry-point group — never instantiated directly):
- **`FakeRunner`** (`name="fake"`, `evals/fake_runner.py`) — the **hermetic default + test driver**. Its `_invoke_agent` applies a caller-supplied deterministic mutation (`Callable[[Path], None]`; default a no-op) to the scratch tree and returns a canned transcript. No network, no CLI; every unit test uses it. It leaves `requires_resolved_prompt=False`, so it tolerates the placeholder `render_prompt` emits for a synthetic test task.
- **`ClaudeCodeRunner`** (`name="claude_code"`, `evals/claude_code_runner.py`) — a **thin, opt-in real runner**. Its `_invoke_agent` drives the Claude Code CLI via a plain `subprocess` arg-list (default `claude -p <prompt>`) bound to the scratch repo and captures stdout/stderr as the transcript. Lazy — no top-level CLI import; `available()` returns `False` when the `claude` binary is not on `PATH` (mirroring the `radon` lazy-availability pattern), so it is cleanly skippable and **never exercised in CI**. It sets `requires_resolved_prompt=True`.
- **`OpenCodeRunner`** (`name="opencode"`, `evals/opencode_runner.py`) — a second thin, opt-in real runner, the same shape as `ClaudeCodeRunner`. Its `_invoke_agent` drives the OpenCode CLI via a plain `subprocess` arg-list (default `opencode run <prompt>`) with `cwd=scratch_dir` and merges stdout/stderr into the transcript. Lazy — no top-level CLI import; `available()` returns `False` when the `opencode` binary is not on `PATH`, so it is cleanly skippable and **never exercised in CI**. It sets `requires_resolved_prompt=True`. The `command`/`timeout` are configurable (a `{prompt}` token is interpolated, else the prompt is appended).

`ContinueCLIRunner` remains future work (not yet implemented).

**`render_prompt` strictness.** `render_prompt(task, strict=…)` resolves `task.prompt_id` to its `Prompt` (scanning `resources/prompts/` alongside the task tree) and renders the body through the renderer under `StrictUndefined`. When the prompt cannot be resolved: a *real* runner (`requires_resolved_prompt=True`) raises `PromptResolutionError` — a live agent must never be driven with a placeholder; the hermetic `FakeRunner` (`strict=False`) tolerates a stable placeholder because the deterministic scoring layers never read the rendered text.

#### 15.3.1 Scoring bridge (`evals/scoring.py`)
`score(task, baseline, candidate, *, judge=None, samples=1, fail_fast=False) -> EvaluationReport` produces one report covering both layers. It compiles the task's layer blocks into the per-trial `Rubric` (`task.compiled().per_trial`; §6.5.3), **walks the compiled check tree** to discover which metrics the gate/rubric checks reference, pre-measures them into a `MeasurementSet`, and runs `Rubric.evaluate`. The two named layer checks (`id="gate"` / `id="rubric"`) draw on the checks compiled from the handle tables:
- **`[gate]` metric checks** — `ThresholdCheck` / `NonRegressionCheck` over a registered `metric=` grade a `MeasurementSet` the bridge builds up front: **static** metrics measured per candidate `*.py` file (label = tree-relative path so a candidate matches its baseline counterpart), **execution** metrics run a `ProjectHandle` over the candidate tree (only when an execution metric is referenced — `run_tests` is *inferred*) — both with the baseline measured on the **pristine `setup/` snapshot** so non-regression compares against the untouched setup, not the post-agent tree. Thresholds and `max_worsening` are **0–1 cutoffs on the metric's normalized score** (every metric owns a `Normalizer`; §21).
- **`[gate]` file checks** — `FileExistsCheck` / `FileContainsCheck` / `FileUnchangedCheck` / `FileForbiddenCheck` (`evaluators/checks/files.py`) ignore the `MeasurementSet` and read the candidate tree from `ctx.tree` (`available()` is `False` without one); `FileUnchangedCheck` compares candidate bytes against the `setup/` snapshot via `ctx.baseline_tree`. Each is a pure gate (`required=True`, `weight=0.0`).
- **`[gate]` answer checks** — `AnswerMatchesCheck` (`evaluators/checks/answer.py`, `{check = "answer_matches", pattern = …}`) regex-searches the graded artifact (`ctx.artifact`, below) instead of the tree, so a review-only task can be gated deterministically on its *conclusion*. Fail-closed: always `available()`, so an empty artifact fails rather than skipping. See §21.2.4.
- **`[rubric]` judge checks** — the `JudgeCheck`s in a `rubric` group (and standalone `judge=` checks) score the graded artifact (`ctx.artifact`) into a `0-1` leaf (averaged over `samples`), feeding the rubric-group composite and gating on the group's `fail` (or the criterion's `threshold`). They are JUDGED-cost so the scheduler runs them last, and **`available()` is `True` only when `ctx.judge is not None`** — with no judge (the default) the whole rubric layer reports `status="skipped"`. "Deterministic-only" is **simply no judge configured**; there is no `ProgrammaticOnlyJudge`.

**The graded artifact (`ctx.artifact`).** `_graded_artifact(candidate)` is the candidate's captured `git diff` when it is non-empty, and its **transcript** otherwise. An *edit* task is graded on what the agent did, so its diff is the artifact — unchanged, and the only case that existed before. A *review* task is graded on what it **said**: such a task forbids edits (its gate is `file_unchanged`), so a well-behaved agent leaves the diff empty and its whole contribution is the transcript — grading that empty diff scored every review task against nothing at all. The discriminator is the diff rather than anything declared on the task, because a task does not announce its kind and an edit task whose agent did nothing has no diff to grade either. This is byte-identical for any task with a non-empty diff.

Both layer checks flow through one `Rubric.evaluate(ctx, measurements, *, strict, fail_fast)` into a single `EvaluationReport` whose `report.checks` carry the gate/rubric `CheckResult`s. The bridge then **derives** the per-trial verdict from those results (`evals._compile.verdict_passed` over `[verdict].trial`, skipped-neutral) and writes it onto `report.passed` — the layers ran once; the verdict is a boolean fold, not a third check. `fail_fast` (the runner's default; `--full-scoring` flips it off) lets the cost-tiered scheduler short-circuit once a required gate check fails, so a failing deterministic gate spares the execution/judged tiers (the LLM judge is never invoked) — for a task whose result the skip cannot change, i.e. a pure-conjunction verdict over every layer (the default `gate and rubric`) and no aggregate over a skippable layer; any other task is scored in full (see `CompiledTask.short_circuit_safe`).

### 15.4 Why the eval abstractions live in one tree
The `coding_agent_playbook/evals/` package ships `task.py`, `loader.py`, `validator.py` (active since v1), the task-config compiler trio `_expr.py` (the boolean-expression DSL) + `_handles.py` (the handle Factory/Composite builder) + `_compile.py` (the layer compiler + derived verdict), `runner.py` + `fake_runner.py` + `claude_code_runner.py` + `opencode_runner.py` + `scoring.py` (live since v1.1 R1), and `judge.py` (**live since v1.1 R2**). `judge.py` defines the concrete-able `Judge` ABC — **Option A**: the per-criterion primitive `score_criterion(criterion, artifact, n=1) -> float` (0–1, n-sample average) is canonical, and the batch `score(rubric, transcript, scratch_dir_state) -> list[float]` is a thin wrapper that maps it over the rubric — plus the opt-in `LLMJudge` (`name="llm"`, shells out to the `claude` CLI, `available()`-gated, never in CI) and the test-only `StubJudge`. A configured judge that cannot score — `LLMJudge`'s CLI exits non-zero, times out, or answers anything but exactly one number in `[0, 1]` — retries a bounded number of times (default 2, no backoff) and then raises `JudgeError`; it never degrades to a number (an `"API Error: 529"` used to clamp to a perfect `1.0`). `prompting.py` renders a task's prompt the way `playbook sync` does — the `rule()` helper over the `applies_if`-filtered engine (+ the task's overlay) rules, and a Jinja context of detector facts over `setup/` overlaid with the task's mock facts, plus `project_name` from `setup/pyproject.toml`. This means:
- Overlay authors writing tasks can import `EvalTask`, `TaskSetup`, etc. for type hints in their own tooling.
- The module layout is stable across the v1 → v1.1 progression; only the placeholder bodies get filled in.
- The `[project.entry-points."coding_agent_playbook.runners"]` group is populated (`fake`, `claude_code`, `opencode`); the `coding_agent_playbook.judges` group is populated with `llm`; the engine ships no builtin `coding_agent_playbook.gates` / `coding_agent_playbook.rubrics` / `coding_agent_playbook.checks` entries — those are the third-party extension points a task references by `ref`/`check` name.
## 16. Testing strategy
### 16.1 Unit tests
- `test_detector.py` — synthetic `pyproject.toml` files in `tests/fixtures/repos/`; assert facts dict matches expected.
- `test_renderer.py` — render templates with hand-crafted context; assert exact output.
- `test_overlays.py` — registration, ordering, override resolution.
- `test_lockfile.py` — hash compute, drift detection.
- `test_gitignore.py` — managed-block entries (skill-dir collapse under any root, escaping verified against real git), append/replace/idempotence, CRLF and missing-final-newline preservation, malformed markers, removal.
- `test_git_client.py` — `SubprocessGitClient` against throwaway repos (guarded on git being on PATH, hermetic git env) plus its silent failure modes; `playbook sync` tests inject `tests/fakes.py::FakeGitClient` instead of patching `subprocess`.
### 16.2 Adapter tests (golden file)
Each adapter has a directory of input/output pairs:
```
tests/fixtures/golden/continue/python-typing/
├── input.facts.toml
├── input.rule.md.j2
└── output.md                    # expected exact bytes
```
Test asserts the adapter output matches `output.md` byte-for-byte. Update via `pytest --snapshot-update`.
### 16.3 Integration tests
`tests/integration/test_end_to_end.py` builds a synthetic consumer repo in a `tmp_path`, runs the full `playbook init` → `playbook sync` flow, and asserts the resulting file tree matches expectations.
### 16.4 CI
GitHub Actions / internal Jenkins running:
1. `uv sync --dev`
2. `pre-commit run --all-files` (ruff, mypy, gitleaks)
3. `pytest -q`
4. `playbook validate` against own resources
5. `playbook render python-typing --format continue > /tmp/out.md` smoke test
### 16.5 Backwards compatibility tests
A `tests/compatibility/` directory contains a frozen consumer repo from v0.3 with its expected generated output. CI asserts v0.4 still generates compatible output (or that the migration is explicitly documented).
## 17. Security and operational considerations
### 17.1 Air-gapped operation
- **No network calls at sync time.** All resources are bundled in the package.
- **No HTTP-handler hooks shipped by default.** The Claude Code / Continue CLI HTTP hook type is supported by the adapter API but no engine-shipped hook uses it.
- **Internal PyPI only.** No public PyPI dependency required for runtime; `uv` itself is the only binary dependency for the install flow.
### 17.2 Dependency allowlist
For BNP, the overlay package ships a rule (`30-bnp-banking-dependencies`) that lists approved third-party packages. The rule appears in every harness's context, so the assistant won't suggest unapproved libraries. This is enforcement-by-convention; actual enforcement happens at CI time via a separate package-check step.
### 17.3 Secrets
- The engine never reads files matching `.env*`, `*.pem`, `*.key`, `*credentials*`. Detector explicitly skips these paths.
- The pre-commit baseline includes `gitleaks` and `detect-private-key`.
- No log statement in the engine ever logs config values; only structural facts (counts, paths).
### 17.4 Audit log
`playbook sync` writes a structured log line (JSON, one per invocation) to `.coding-agent-playbook.log` (gitignored):
```json
{"timestamp": "2026-05-20T10:30:00Z", "command": "sync", "engine": "0.4.0", "overlays": {"bnp": "0.2.0"}, "files_written": 18, "duration_ms": 340}
```
For BNP, the overlay can extend this to write to a central audit endpoint at sync time (the only network egress the BNP overlay would add, and explicitly opt-in).
## 18. Rollout plan
### 18.1 Phase 0 — engine alpha (internal, 1-2 weeks)
- Build tracks 1-4 from the PR plan
- Test in Max's own repos (`conversational_core`, plus one ML/DS team repo)
- No external announcement
### 18.2 Phase 1 — engine beta + BNP overlay (2-4 weeks)
- Build tracks 5-6
- Author the BNP overlay (Track 7 content)
- Onboard 3-5 friendly teams; collect feedback
- Iterate on rule wording based on observed agent behavior
### 18.3 Phase 2 — engine 1.0 + open source release
- Move engine repo to a public namespace (GitHub, Apache-2.0)
- BNP overlay stays private; documented as the canonical example overlay
- Internal announcement; opt-in for any BNP team
- Write a Medium / engineering blog post describing the design
### 18.4 Phase 3 — v2 features
- MCP server config management
- Cursor and Codex CLI dedicated adapters
- Eval harness implementation
- Auto-suggestion of new rules from PR review patterns
## 19. Open questions
1. **Should overlay packages be allowed to ship adapters?** (E.g. a community Cursor adapter via overlay.) Currently the design says yes via entry points; we should validate no security implications.
2. **Lockfile granularity.** Per-file hashes vs. content-addressable single hash. Current spec is per-file; simpler but more lock churn. Revisit if churn becomes a problem.
3. **Migration of existing `.continue/rules/` content.** If a consumer already has rules they hand-authored, `playbook init` should detect and offer to convert them to canonical templates. Out of scope for v1, but worth scoping in v2.
4. **Multi-language support.** v1 assumes Python. The architecture is language-agnostic (rules are just markdown), but the detector is Python-specific. v2 would add JS/TS detection. Defer.
5. **Versioning of overlays vs. engine.** Currently overlays pin the engine's minor range. Is that the right contract? Or should overlays declare a `compatible_engine_versions` field explicitly?
6. **Glob/tag-based rule inclusion in prompts.** Currently `includes_rules:` requires explicit rule IDs. A natural follow-on is `includes_rules_matching: { tags: ["python", "testing"] }`. Rejected for v1 for readability reasons (see Section 6.2.5); revisit in v2 if explicit lists become unwieldy.
7. **Cross-prompt rule sharing.** If three prompts all `includes_rules: [python-typing, pytest]`, the rule content is duplicated three times in three rendered files. Acceptable for v1; v2 might explore a shared "context library" referenced from prompts.
8. **OpenCode plugin generation.** OpenCode's only lifecycle hook mechanism is JS/TS plugins under `.opencode/plugin/`, subscribing to 31 documented runtime events (`tool.execute.before`, `session.idle`, etc.). The engine could generate plugin code from a canonical hook description, but plugin code is a different artifact class entirely (executable JS, not declarative config) and the OpenCode plugin API still has known gaps around mid-session message injection. v1 leaves plugins to the user; v2 should evaluate whether the playbook ships plugins or just hook *patterns* via documentation. For BNP specifically, this is probably the highest-ROI v2 feature — a pre-tool-use PII redactor plugin is exactly the kind of guardrail banking IT will value.
9. **OpenCode agents as a first-class artifact.** OpenCode supports named modes (`build`, `plan`, custom agents) with distinct system prompts, models, and permissions, defined in `.opencode/agent/<name>.md`. Claude Code subagents are conceptually similar. v1 treats agents as out of scope; users author them by hand. v2 could add a fifth artifact category — but the degradation story for harnesses without named agents (Continue, Codex) is unclear. Revisit when a concrete use case appears.
10. **HarnessRunner invocation contract.** v2 needs a uniform way to programmatically invoke Claude Code, Continue CLI, and OpenCode with a given prompt and working directory. Each harness exposes a different surface — Claude Code SDK with session API, `cn -p --prompt`, `opencode` CLI flags. Decide: thin wrappers per harness (matched to native APIs, more flexible) or a normalized "agent loop" interface the engine owns (LiteLLM-backed, more portable but reimplements harness behavior). My instinct is thin wrappers because the value of evals is catching *harness-specific* regressions, not papering over them.
11. **Determinism and seeding for evals.** Coding agents are non-deterministic. A Tier 1 runner that fails a task once might pass it on retry. Options: (a) seed temperature=0 and accept residual noise; (b) run each task N times and report pass-rate; (c) accept flakiness, focus on aggregate trends across many tasks. (b) is statistically honest but expensive; (a) is cheap but the seed isn't always honored. Defer to v2 with bias toward (a) + per-task `flaky: true` annotation for known-noisy tasks.
12. **Rubric judging calibration.** Tier 2 uses an LLM-as-judge. Before trusting its scores, the runner needs a calibration step where humans grade ~20 task outputs and the judge is evaluated against them. If judge–human correlation is below some threshold (0.7? 0.8?), the judge's grades shouldn't be reported. v2 decision: ship the calibration tooling, or assume good correlation and add it only if scores look noisy? Lean toward shipping it — calibration is cheap relative to the cost of acting on bad eval data.
## 20. Storage sources
This section adds one architectural seam to the engine. It is purely additive — v1 behavior is unchanged — and it exists to keep the engine swappable later without a rewrite.
### 20.1 The problem this solves
Today, the engine has filesystem operations scattered across several modules: the artifact loader walks `importlib.resources` and `<repo>/playbook/`, the config module reads `.coding-agent-playbook.toml`, the lockfile module reads and writes `.coding-agent-playbook.lock`. Each of these is hardcoded to "use the local filesystem."
That is correct for v1, but it makes two things hard:
- **Testing.** Tests that exercise the loader need real temp directories with fixture files. There is no clean way to inject hardcoded artifacts.
- **Future flexibility.** If a future deployment (a hosted product, an internal company registry, an air-gapped mirror with version pinning) needs artifacts or state to come from somewhere other than the local filesystem, every call site has to be refactored.
The fix is a small abstraction: route "where do artifacts come from" and "where does state live" through two interfaces, with one concrete implementation each in v1.
### 20.2 The two interfaces
```python
# coding_agent_playbook/sources/base.py
from abc import ABC, abstractmethod
from coding_agent_playbook.types import Rule, Prompt, Skill, EvalTask
from coding_agent_playbook.config import Config
from coding_agent_playbook.lockfile import Lockfile


class ArtifactSource(ABC):
    """Where rules, prompts, skills, and eval tasks come from."""

    name: str

    @abstractmethod
    def list_rules(self) -> list[Rule]: ...
    @abstractmethod
    def list_prompts(self) -> list[Prompt]: ...
    @abstractmethod
    def list_skills(self) -> list[Skill]: ...
    @abstractmethod
    def list_eval_tasks(self) -> list[EvalTask]: ...


class StateSource(ABC):
    """Where config and lockfile are read from and written to."""

    name: str

    @abstractmethod
    def load_config(self) -> Config: ...
    @abstractmethod
    def save_config(self, config: Config) -> None: ...
    @abstractmethod
    def load_lockfile(self) -> Lockfile | None: ...
    @abstractmethod
    def save_lockfile(self, lockfile: Lockfile) -> None: ...
```
These are deliberately small. They expose typed Python objects, not raw bytes or filesystem paths. The engine never has to know whether something came from a wheel, a TOML file, or anywhere else.
### 20.3 What v1 ships
Two concrete implementations, both already implied by the rest of the spec:
```python
# coding_agent_playbook/sources/filesystem.py
class FileSystemArtifactSource(ArtifactSource):
    """Walks importlib.resources for the engine + overlay packages,
    plus <repo>/playbook/ for repo-local artifacts."""

    name = "filesystem"
    # Implementation = the current loader logic, just renamed.


class FileSystemStateSource(StateSource):
    """Reads and writes TOML files in the consumer repo:
    .coding-agent-playbook.toml, .coding-agent-playbook.local.toml,
    .coding-agent-playbook.lock."""

    name = "filesystem"
    # Implementation = the current config + lockfile logic, just renamed.
```
These are the **only** sources v1 ships. They depend on nothing beyond the existing dependency budget (jinja2, packaging) — both use stdlib `tomllib`, `pathlib`, and `importlib.metadata` only.

Beyond the ABC, `FileSystemStateSource` reads the committed file alone — `read_committed_config_table()`, the checked, decoded table with every key, which never reads `.coding-agent-playbook.local.toml`; `has_committed_config()` says whether it exists — and writes a decoded table verbatim with `save_config_table(table)`, the committed file's one writer (`save_config(config)` writes `config.to_dict()` through it, which drops what `Config` does not own, so no command calls it). `preview_config(table)` returns what `load_config()` will give once that table is saved — the table with the local file merged on top — without writing. Every rewrite is built in `commands/_committed_config` as a `ConfigRewrite` (the table and its `Config`) and checked with `preview_config` before `ConfigRewrite.save` writes it: `plan_first_config` (a first `init`; refused when the file exists), `plan_committed_update` (an `init` re-run: read the committed table once, build its `Config`, apply the answers, write it through `Config.to_dict` plus `config_entries.with_unmanaged_entries` of the committed table — top-level entries after the config's own keys, unknown keys of `[project]`/`[engine]`/`[storage]`/`[output]` inside that table, a key `Config` owns there being a `ValueError`) and `plan_detector_cache_refresh` (`check --refresh`: the committed table with `[detector_cache]` replaced, nothing else) (§12.1, §12.5). `load_config()` stays the merged, effective config (§7.2) and is never saved (the §7.2 invariant).
### 20.4 Configuration
The `[storage]` section of `.coding-agent-playbook.toml` selects which source to use. v1 defaults are filesystem for both, so existing configs need no changes:
```toml
[storage]
artifact_source = "filesystem"      # default; the only v1 option
state_source = "filesystem"         # default; the only v1 option
```
When v1 reads a config without a `[storage]` section, both default to `"filesystem"`. Users who never customize storage never see this section.
### 20.5 Discovery via entry points
Sources are registered the same way as adapters and overlays — through Python entry points. The engine ships:
```toml
[project.entry-points."coding_agent_playbook.artifact_sources"]
filesystem = "coding_agent_playbook.sources.filesystem:FileSystemArtifactSource"
[project.entry-points."coding_agent_playbook.state_sources"]
filesystem = "coding_agent_playbook.sources.filesystem:FileSystemStateSource"
```
A future package — open-source or proprietary — can register alternative sources by declaring its own entry points. The engine code does not change.
### 20.6 What this enables later (not in v1)
Concrete examples of what the seam buys, intended to clarify the design intent — none of these ship in v1:
- **An internal company registry** could provide a `RegistryArtifactSource` that fetches rule packs from a versioned HTTP endpoint behind corporate auth. The engine sees the same `Rule` objects regardless.
- **A hosted product** could provide a `DatabaseStateSource` that writes lockfile state to a central database, enabling cross-repo drift dashboards without changing how the engine writes lockfiles.
- **A test harness** can use an `InMemoryArtifactSource` to inject hardcoded rules into the engine without touching the filesystem.
These are alternative deployments of the same engine, not forks of it.
### 20.7 What v1 promises and does not promise
Promises:
- The `ArtifactSource` and `StateSource` interfaces are public API once v1 ships. Breaking changes require a major version bump.
- The filesystem implementations are the reference implementations; their behavior is what other sources must match for consumer-visible parity.
- The engine code never instantiates a specific source class; it always goes through entry-point discovery and the configured source name.
Does not promise:
- v1 does not commit to building any non-filesystem source.
- v1 does not commit to backward compatibility for the *internal* helpers used by the filesystem implementation (only the abstract base class is API).
- v1 does not commit to a sync-time API for sources beyond what the abstract base requires. Future sources may need additional capabilities (caching, prefetch, signed updates) — these will be added as optional methods on the ABC with default implementations.
### 20.8 What changes in the rest of the spec
The Repository pattern is now the implementation strategy for several earlier sections; the user-visible behavior in those sections is unchanged. Specifically:
- **Section 4.2 (data flow)**: Step 3 ("Resolve overlays. Walk the engine's resources/...") is implemented by calling `ArtifactSource.list_rules()` and friends. The resolution-order semantics are unchanged.
- **Section 5.1 (engine layout)**: Adds a `sources/` package alongside `adapters/` and `evals/`.
- **Section 8 (detector)**: Unchanged. The detector reads `pyproject.toml` from the local repo and is independent of artifact storage.
- **Section 14.4 (lockfile)**: The lockfile's *content* is unchanged; only the read/write path goes through `StateSource`.
### 20.9 Why this matters even if commercialization never happens
Two non-commercial reasons to ship this in v1:
1. **Tests get simpler.** An `InMemoryArtifactSource` in `tests/` lets every unit test build a tiny artifact list inline, with no temp directories, no fixture files, no filesystem walks. The integration tests still use the real filesystem source for end-to-end coverage.
2. **The engine codebase becomes more honest about its dependencies.** Right now, "load some rules" implicitly depends on `importlib.resources`, `pathlib`, the filesystem layout convention, and overlay entry-point discovery — all tangled together. After this change, those dependencies live in one named class with one clear responsibility. The rest of the engine depends on an interface, not a tangle.
The cost is roughly 100 lines of interface code and a renaming of existing modules. No new runtime dependencies. No new operational complexity for the consumer.
### 20.10 The `.playbook/manifest.toml` round-trip sidecar
The Agent Harness format (§10.7) cannot represent several canonical fields — a rule's `name`/`scope`/`globs`/`priority`/`tags`, a prompt's `slash`/`includes_rules`/`input_variables`, a skill's open-dict extra frontmatter, a script's executable bit. To make the harness round-trip lossless, the `agent_harness` adapter writes a dotfile sidecar at `<harness-root>/.playbook/manifest.toml` (harness clients skip dotfiles, so it is invisible to them). It is not a `StateSource` — it is a per-harness reconstruction record co-located with the emitted tree — but it plays the same role for the harness direction that the lockfile plays for sync.
The sidecar stores the **full canonical reconstruction payload**, not merely "non-native fields". For every emitted artifact, keyed by its harness-relative path, it records:
- every frontmatter field the harness leaf cannot carry (notably the rule `name`, since the harness rule file emits `description` only);
- the original, **un-rendered** canonical source `body` for every kind — the harness leaf is the client-facing *presentation* and may rewrite/inline content (a prompt's `includes_rules` are inlined into its `SKILL.md`), so the recorded body is the authoritative canonical text;
- `is_templated` for every kind (tracks `.md` vs `.md.j2` origin);
- for skills, a per-script `executable` boolean (git's single-bit model, not a full octal mode).
Frontmatter values are written with the shared `_toml` primitives as inline TOML, keeping every type YAML frontmatter yields — strings, booleans, integers, floats, dates and datetimes, nested in arrays and inline tables — so they read back with the same types. Floats and dates are written since v0.18; before, such a value in `applies_if`, `input_variables` or a skill's extra frontmatter stopped `init`/`sync` with `TypeError: manifest TOML does not support value of type float`.
Because each entry carries the whole payload, `import-harness` reconstructs each artifact via `from_dict` **independently of how the leaf rendered or inlined things** — the leaf files exist only for harness clients; the sidecar is the source of truth. When the sidecar is absent (a foreign harness), the importer falls back to best-effort structural inference and surfaces the lossiness (§12.9).
### 20.11 Out of scope: the harness client runtime
The Agent Harness spec also defines a **client runtime contract** — `load_content` / `run_script` and the four loading phases (Load → Discovery → Activation → Execution). The playbook intentionally does **not** implement that runtime. It produces harness files (the `agent_harness` adapter), consumes them (`import-harness`), and validates their structure (`validate-harness`), but it is not a harness *client*: it never injects `HARNESS.md` into a session, reads routing files at runtime, or executes scripts. Modeling the full client runtime is future work; for v1 the `validate-harness` lint is the structural stand-in for runtime conformance (decision #3 in `specs/prH-agent-harness.md` §D).
## 21. Code-quality evaluator subsystem
Added in PR M; **refactored to the `Metric` / `Check` / `Rubric` model in PR R6** (clean-slate, `specs/prR6-check-rubric.md`). This section adds a code-quality measurement engine — static metrics, execution metrics (tests/coverage), and a generalized rubric — behind **three single-responsibility abstractions**, plus a standalone `playbook metrics` gate and a static pre-commit hook. It is purely additive to the sync pipeline: it touches none of it and ships no new hard dependency. The authoritative design is `specs/prR6-check-rubric.md` (and the original `specs/prM-code-metrics.md`, now superseded for the abstraction shape); the as-built lives in `src/coding_agent_playbook/evaluators/` and `commands/metrics.py`.
### 21.1 Three abstractions: `Metric` → `Check` → `Rubric`
A rubric criterion, a code metric, a coverage number, and a test-pass rate are all the same thing — a **graded measurement over a scope** — but *measuring* a value, *grading* it pass/fail, and *aggregating* graded results into a verdict are three distinct responsibilities. PR M originally fused them into one `Evaluator` ABC + a free `grade()`; PR R6 split them along the grain (the realization of the Anthropic "Demystifying Evals for AI Agents" framing — a Check ≈ a grader's pass/fail assertion, a Rubric = a weighting of checks, and a metric becomes a check via a threshold):
```python
class Scope(Enum):
    FUNCTION
    METHOD
    CLASS
    FILE
    MODULE  # MODULE = the whole target/suite


class Determinism(Enum):
    DETERMINISTIC
    JUDGED  # who produces the value (routing)


class CostTier(IntEnum):
    DETERMINISTIC < EXECUTION < JUDGED  # cheapest-first scheduling


class Metric(ABC):  # the "measure" leaf  (evaluators/metric.py)
    name: str
    scope: Scope
    normalizer: Normalizer  # maps raw -> 0-1 GOODNESS (higher = always better)
    requires: str | None = None  # optional importable dep (e.g. "radon"); None = stdlib
    needs_project: bool = False  # True => execution metric (needs ctx.project)
    needs_judge: bool = False  # True => judge-backed metric (needs ctx.judge)

    def available(self, ctx: EvalContext) -> bool: ...
    def score(self, raw: float) -> float: ...  # raw -> 0-1 via self.normalizer
    @abstractmethod
    def measure(self, ctx: EvalContext) -> list[Measurement]: ...  # one Measurement per scope


class Check(ABC):  # the "grade" stage  (evaluators/check.py)
    id: str
    weight: float  # > 0 => contributes to the weighted composite
    required: bool  # a gate check
    determinism: Determinism  # routing axis
    cost: CostTier  # scheduling tier

    def available(self, ctx: EvalContext) -> bool: ...
    @abstractmethod
    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult: ...


class Rubric(Metric):  # the "aggregate" stage  (evaluators/rubric.py)
    def evaluate(
        self, ctx, measurements, *, strict=False, fail_fast=False, max_workers=1
    ) -> EvaluationReport: ...
    def measure(
        self, ctx
    ) -> list[Measurement]: ...  # a Rubric is ALSO a Metric (composite as one MODULE measurement)
```
The split: a **`Metric`** carries only the measurement-side descriptors (`name`, `scope`, `normalizer`, `requires`, `needs_project`/`needs_judge`) and produces a raw `Measurement` per scope; a **`Check`** carries the grading-side policy (thresholds, regression tolerance, `weight`, `required`) and turns measurements (or `ctx` directly, for file/judge checks) into one `CheckResult` — a boolean `passed` gate **plus** an optional `0-1` `score` for partial credit; a **`Rubric`** holds an ordered set of checks and folds their results into one `EvaluationReport` (gate = all `required` checks pass; composite = `Σ(weight·score)/Σweight`). The `EvalContext` (`evaluators/types.py`) carries everything a family might need, decoupled: static reads `module`/`source`/`label`; execution reads `project`; judged reads `judge`/`artifact`/`samples`; file checks read `tree`/`baseline_tree`. `available(ctx)` lets each piece degrade gracefully when its slot or dependency is missing.

**Normalization lives on the `Metric` — `higher_is_worse` is gone.** Every metric owns a `Normalizer` (`evaluators/normalizer.py`: `RampNormalizer(good, bad)` / `PercentNormalizer` / `Identity`) mapping its raw value to a `0-1` **goodness** where `1.0` is best and **higher is always better**, regardless of the metric's native direction (`cyclomatic_complexity` ramps *down* as it grows, `coverage` ramps *up*). `Metric.score(raw)` applies it. Folding direction into the normalizer is what let the per-metric `higher_is_worse` flag be **deleted**: the `Check` grades on the normalized score, so it never reasons about direction, and every threshold (`warn` / `fail` / `max_worsening`) is a `0-1` cutoff on that goodness.

**A `Rubric` is also a `Metric` — the Composite.** `Rubric` subclasses `Metric` and exposes its composite as one MODULE-scope `Measurement` via `measure()`, so a rubric thresholds into a parent `ThresholdCheck` and **nests** into a Composite tree (a rubric-of-rubrics). `measure()` self-builds its `MeasurementSet` from the additive `EvalContext.candidate_measurements`/`baseline_measurements`, guards against a re-entrant self-measure (`ValueError`), and memoizes per `ctx`. This replaces the old fused `Evaluator` with a composable algebra: any check tree (booleans via `AllOf`/`AnyOf`/`Not`, §21.2.4) is itself a check.

**The static / execution / judged discriminator is `needs_project` / `needs_judge`, not the scope axis.** A FILE-scope metric like `coverage` is *execution*, not static, so scope alone cannot separate them; `needs_project=True` (execution) / `needs_judge=True` (judge-backed) are the explicit flags. `static_metrics()` excludes `needs_project`; a metric-backed check derives its `cost` (DETERMINISTIC / EXECUTION / JUDGED) from these flags.

**How the families are differentiated — orthogonal axes, no `kind` enum.** The families are *emergent* from independent fields, so the engine never switches on a "type". A task `check` is `(type) × (metric|judge) × kwargs` — `check = "threshold"|"non_regression"` over a registered `metric=` or a `judge=` criterion (a `JudgeMetric`, §21.2.3) — plus the standalone file checks and rubric groups:

| Family | check class / id | `determinism` | `cost` | `available(ctx)` needs | task layer |
|---|---|---|---|---|---|
| static metric (§21.2.1) | `threshold` / `non_regression` over a static `metric=` | DETERMINISTIC | DETERMINISTIC | `ctx.module` (source/AST) | `[gate]` |
| execution (§21.2.2) | `threshold` / `non_regression` over an execution `metric=` | DETERMINISTIC | EXECUTION | `ctx.project` | `[gate]` |
| judged metric (§21.2.3) | `threshold` / `non_regression` over a `judge=` (a `JudgeMetric`), or a `rubric` group of `JudgeCheck`s | JUDGED | JUDGED | `ctx.judge` | `[rubric]` |
| file check (§21.2.4) | `file_exists` / `file_contains` / `file_unchanged` / `file_forbidden` | DETERMINISTIC | DETERMINISTIC | `ctx.tree` | `[gate]` |
| answer check (§21.2.4) | `answer_matches` — a regex over `ctx.artifact` | DETERMINISTIC | DETERMINISTIC | *nothing* (always available, fail-closed) | `[gate]` |
| aggregate (§21.2.5) | `pass_at_k` / `pass_pow_k` over the runner's trials | DETERMINISTIC | DETERMINISTIC | `ctx.trials` | `[aggregate]` |

Authors differentiate by **task layer + handle shape** (a `[gate.bind]` / `[rubric.bind]` / `[aggregate.bind]` handle), which the compiler turns into a `Rubric` of checks (§21.6); the engine differentiates by the axes and the cost-tiered scheduler routes by capability (`available(ctx)`) + tier, not a type switch — so a new kind drops in by choosing axis values, with no second `grade()` path.

### 21.2 The check families
| Task handle | Family | Metric / Check | `determinism` · `cost` / needs | primary use |
| --- | --- | --- | --- | --- |
| `[gate]` `{check="threshold"|…, metric="cyclomatic_complexity"|…}` | **static** | static `Metric` → `ThresholdCheck`/`NonRegressionCheck` | DETERMINISTIC · DETERMINISTIC · `ctx.module` (`ast`/`radon`) | 0–1 threshold + **non-regression** |
| `[gate]` `{check=…, metric="test_pass_rate"|"coverage"}` | **execution** | execution `Metric` → `ThresholdCheck`/`NonRegressionCheck` | DETERMINISTIC · EXECUTION · `ctx.project` (shells out to `pytest`) | 0–1 threshold + **non-regression** |
| `[rubric]` `{rubric=[{judge,weight},…]}` or `{check=…, judge="…"}` | **judged** | `JudgeCheck` (rubric group) or a `JudgeMetric`-backed check | JUDGED · JUDGED · `ctx.judge` (LLM) | weighted composite + threshold |
| `[gate]` `{check="file_exists"|…}` | **file** | `FileExists`/`FileContains`/`FileUnchanged`/`FileForbidden` | DETERMINISTIC · DETERMINISTIC · `ctx.tree` | must-be-true gate |
| `[aggregate]` `{metric="pass_at_k"|"pass_pow_k", k, over}` | **aggregate** | `PassAtK`/`PassPowK` over the runner's trials | DETERMINISTIC · DETERMINISTIC · `ctx.trials` | cross-trial reliability |
#### 21.2.1 Static metrics (`evaluators/builtins/`)
Source is parsed **once** into a `ModuleModel` (`evaluators/parse.py`, which also owns the shared `_cyclomatic` helper and the stable scope keys `<label>::<qualname>` / `<label>`); each available static `Metric` reads that model via its module-level `_measure` helper. All are stdlib-`ast`-only except MI, which is the lone radon-backed one. Each metric owns a `Normalizer` that folds its native direction into a 0–1 goodness (higher = better). The grading-side policy (the warn/fail bounds + regression tolerance below) lives on the *check*, not the metric, as **0–1 cutoffs on the normalized score**: the shared per-metric defaults are `evaluators/policy.py::METRIC_DEFAULTS`, applied by `metric_check()` when an override is absent.
| `name` | scope | `normalizer` (raw→0–1) | default warn/fail (0–1) | default `max_worsening` | requires |
| --- | --- | --- | --- | --- | --- |
| `cyclomatic_complexity` | FUNCTION/METHOD | `Ramp(good=5, bad=20)` | `warn=0.5, fail=0.25` | `0` | — |
| `wmc` | CLASS | `Ramp(good=10, bad=60)` | `fail=0.2` | `0` | — |
| `lcom4` | CLASS | `Ramp(good=1, bad=6)` | `warn=0.5` | `0` | — |
| `dit` | CLASS | `Ramp(good=1, bad=8)` | `warn=0.5` | `0` | — |
| `cbo` (≈) | CLASS | `Ramp(good=3, bad=25)` | `warn=0.5` | `0` | — |
| `maintainability_index` | FILE | `Percent` (0–100→0–1) | `fail=0.65` | `0` | `radon` |
A `Ramp(good, bad)` scores `good`→`1.0`, `bad`→`0.0` and interpolates between (clamped); the single direction-free formula handles a worse-when-larger metric (`good < bad`) and a better-when-larger one alike. Algorithms: **CC** = 1 + decision points (`If/For/AsyncFor/While`, comprehension `if`s, `BoolOp` operands−1, `ExceptHandler`, `IfExp`, `match` guards, `assert`); **WMC** = Σ of method CC; **LCOM4** = connected components of the method graph (shared `self.x` attr or `self.m()` call); **DIT** = longest resolvable base chain (external base = depth 1); **CBO≈** = distinct external types referenced (labeled approximate — undercounts under duck typing); **MI** = `radon.metrics.mi_visit(source, multi=True)`, the SEI 0–100 variant. `maintainability_index` is the engine's only optional extra (`pip install 'coding-agent-playbook[metrics]'`): it self-registers like every builtin, but radon is imported **lazily inside `measure`** and `available()` returns `False` when radon is absent, so the gate transparently skips MI and the engine still loads air-gapped with nothing extra installed.
#### 21.2.2 Execution metrics (`evaluators/execution/`)
Deterministic, but they need to **run the target's test suite**, so they add **no playbook dependency**: a `ProjectHandle` (`execution/project.py`) runs a configurable command (default `python -m pytest --junitxml=… --cov --cov-report=xml:… -q`) in the target, and the metrics parse the standard **junit XML** + **coverage XML** with stdlib `xml.etree.ElementTree` (`execution/junit.py`, `execution/coverage_xml.py`). The target supplies `pytest`/`pytest-cov`. The convenience check factories `TestsPassCheck()`/`CoverageCheck()` (`evaluators/checks/execution.py`) are thin `ThresholdCheck` wrappers bound to these metrics with the conventional default bounds.
| `name` | scope | `normalizer` (raw→0–1) | default warn/fail (0–1) | default `max_worsening` | needs |
| --- | --- | --- | --- | --- | --- |
| `test_pass_rate` | MODULE (suite) | `Identity` (already 0–1) | `fail=1.0` (all must pass) | `0` (no new failures) | `ctx.project` |
| `coverage` | FILE (+MODULE total) | `Percent` (0–100→0–1) | `warn=0.8` | `0` (must not drop) | `ctx.project` |
- **One run, both metrics:** `ProjectHandle.run()` executes the suite once and caches the parsed junit + coverage reports; both metrics read that cache (no double run).
- **Flaky tolerance:** `test_pass_rate` is DETERMINISTIC but supports an optional flaky-retry (`ProjectHandle.flaky_retries`; reruns and takes the best observed pass rate); off (`0`) by default.
- **Non-regression needs two runs.** Standalone with `--baseline git:<ref>` materialises the ref via a temporary `git worktree add` (heavier than the static `git show`); `--baseline <dir>` runs the suite there. Absolute mode (single run on the current tree) is the lighter default.
- **Opt-in & cost-gated:** running tests has side effects and cost, so execution metrics are opt-in — `--run-tests` on the standalone `playbook metrics` gate, *inferred* (a `[gate]` referencing an execution metric) on `playbook eval --run`. Their checks are EXECUTION-tier (the scheduler runs them after the deterministic tier) and are **excluded from the default pre-commit hook** — it stays static-only.
#### 21.2.3 Judged criteria — the rubric, as checks (`evaluators/checks/judged.py`, `judge_metric.py`)
A rubric criterion is a `JudgeCheck`: a graded SCORE whose value comes from a *judge* (LLM/human). It is **parameterized**, not a registered singleton — a `[rubric.bind]` `rubric` group instantiates one per criterion line (via `Rubric.of`), each carrying its own `criterion` text, `weight`, and a `0-1` `threshold` floor (id `judge:<slug>`, `determinism=JUDGED`, `cost=JUDGED`). `grade` calls `ctx.judge.score_criterion(self.criterion, ctx.artifact, n=ctx.samples) -> float` and averages over `ctx.samples` to damp LLM noise; the score feeds the composite and the `passed` gate is `score >= threshold`. It is **dormant without a judge**: `available()` returns `True` only when `ctx.judge` is set, so a `Rubric` evaluated with no judge records each `JudgeCheck` as `status="skipped"` (never sinking the gate). Because `JudgeCheck` is JUDGED-cost, the cost-tiered scheduler (§21.4) runs it **last** — a failing deterministic gate short-circuits it away, so under the default conjunction verdict a failed gate check never spends an LLM call (see `CompiledTask.short_circuit_safe` for the tasks scored in full).

**`JudgeMetric` — a judged criterion *as a metric* (`evaluators/checks/judge_metric.py`).** A weighted rubric group is the *one* shape that builds `JudgeCheck`s directly. The *other* shape — a standalone `{check = "threshold"|"non_regression", judge = "<criterion>"}` handle — needs a judged criterion that an ordinary metric-backed `ThresholdCheck`/`NonRegressionCheck` can grade, so `JudgeMetric` is an **Adapter** that presents the judge as a `Metric`: `needs_judge=True`, `normalizer=Identity` (a judge score is already a 0–1 goodness), and `measure(ctx)` returns one `Measurement` = `ctx.judge.score_criterion(criterion, ctx.artifact, n=max(1, ctx.samples))`. This is what makes **non-regression on a judged criterion** work (`{check="non_regression", judge="overall quality", max_worsening=0.1}`) — the same regression machinery as any metric, no special-casing. Like `JudgeCheck`, it never imports `evals` (it consumes only the `JudgeLike` protocol) and is `available()`-gated on `ctx.judge`.
> **Judge signature — reconciled (R2), still closed.** `JudgeCheck.grade` calls `ctx.judge.score_criterion(criterion, artifact, n) -> float` — the **canonical per-criterion primitive** (Option A). The `Judge` ABC's batch `score(rubric, transcript, scratch_dir_state) -> list[float]` is a thin wrapper that maps `score_criterion` over the rubric, so the two shapes are the *same* operation at different granularities. `ctx.judge` is typed as the structural `JudgeLike` protocol **defined in `evaluators/types.py`** (not `evals`) so `evaluators` never imports `evals` — avoiding the `evaluators` ↔ `evals` cycle; the concrete `Judge` satisfies it structurally. Tests exercise `JudgeCheck` via the deterministic `StubJudge`.
#### 21.2.4 File checks + the answer check + boolean composers (`evaluators/checks/`)

**The answer check — `answer_matches` (`evaluators/checks/answer.py`).** The file checks gate on what the agent *did*; `AnswerMatchesCheck` gates on what it *said*. Authored as `[gate.bind] <name> = { check = "answer_matches", pattern = '<regex>' }`, it applies a Python `re` search to `ctx.artifact` — which, for a **review-only** task, is the agent's transcript (§15.3.1). Such a task forbids edits (its gate is `file_unchanged`), so it produces no diff and the file predicates alone can only prove the agent stayed its hand, never that it reached the right conclusion. Its purpose is a cheap **class gate in front of the judge**: the cost-tiered scheduler's short-circuit (§21.4, `fail_fast=True` — the runner default) skips the JUDGED tier entirely when it fails, so a plainly wrong answer costs zero judge tokens. Two deliberate properties: it is **fail-closed** — `available()` is unconditionally `True` (it needs no judge, project, or tree), so a missing/empty artifact grades `False` rather than skipping (a skipped check is *neutral* in the layer expression and would let a silent agent through); and its regex **compiles at construction**, so a malformed pattern raises during task compilation (hence `playbook validate`) rather than midway through a scored run. Case-insensitivity is the pattern's business (`(?i)`), not a separate flag. The shipped `find-injected-vuln-*` fixtures each carry one, holding a lenient CWE-class regex — lenient by design, since the gate rejects a wrong *class* while the judge grades precision.

The four file predicates are first-class deterministic `Check`s (`evaluators/checks/files.py`), authored as `[gate.bind]` handles (`{check = "file_exists"|"file_contains"|"file_unchanged"|"file_forbidden", path = …, pattern = …}`): `FileExistsCheck`, `FileContainsCheck` (path + regex), `FileUnchangedCheck` (byte-identical to the `setup/` snapshot via `ctx.baseline_tree`), and `FileForbiddenCheck`. Each ignores the `MeasurementSet` and reads `ctx.tree` directly, is a pure gate (`required=True`, `weight=0.0`), and its `passed` comes straight from the predicate (`available()` is `False` without a candidate tree). The boolean composers `AllOf`/`AnyOf`/`Not` (`evaluators/checks/compose.py`) are themselves checks that fold child checks through the scheduler (an unavailable child is *neutral*, not a failure; a composer none of whose children can run is itself unavailable and records `status="skipped"`, so the skip propagates up instead of becoming a vacuous pass for `AllOf` or a fail for `AnyOf`), so any check tree nests freely inside a `Rubric` — and they back both the `{all_of=[…]}`/`{any_of=[…]}`/`{not=…}` handle groups and the compiled `[<layer>].expr`/`[verdict].trial` boolean expressions (§21.2.6).
#### 21.2.5 Aggregate checks — `pass@k` / `pass^k` across trials (`evaluators/checks/aggregate.py`)
The `[aggregate]` layer grades **reliability across `k` runner trials**, a dimension orthogonal to the per-trial gate/rubric. A handle is `{metric = "pass_at_k"|"pass_pow_k", k = <int>, over = "gate"|"rubric"|"verdict", warn?, fail?}`; the runner runs `N = max(k)` trials and the `AggregateCheck` reduces the selected `over` axis (each trial's `gate`/`rubric` `CheckResult.passed`, or its derived `verdict`) to `c` successes over `n` trials, then estimates: **pass@k** = the probability a random `k`-subset of the trials contains ≥1 success (`1 - C(n-c,k)/C(n,k)`, or `1.0` when fewer than `k` failed); **pass^k** = the probability a random `k`-subset is all successes (`C(c,k)/C(n,k)`, or `0.0` when fewer than `k` succeeded). The 0–1 estimate is graded against an absolute `warn`/`fail` floor (same higher-is-better strict-below rule the metric checks use). An aggregate check does no agent work — it reads the already-run `ctx.trials` — so it is `DETERMINISTIC` on both axes; `available()` is `True` only once the runner has populated `ctx.trials` **and** the `over` axis ran in at least `k` trials. An aggregate over a **layer** (`over = "gate"|"rubric"`) that the cross-layer short-circuit could skip — one costlier than the cheapest layer, e.g. the judged rubric behind a deterministic gate — makes scoring run every trial in full (no short-circuit): otherwise a trial whose cheaper gate failed would leave that layer ungraded, and the aggregate would depend on `fail_fast`. (A layer in the cheapest tier always runs, so `over = "gate"` with a deterministic gate keeps the short-circuit and still spares the judge.) A trial whose `over` layer was still skipped — it was *unavailable*, e.g. `over = "rubric"` with no judge — does not vote, so `n` counts only the trials where that layer ran; with fewer than `k` votes (in practice: none) the aggregate is skipped (neutral) and the task verdict falls back to the trials' own verdicts: it passes only if every trial passed, scored by the trial pass rate. (`max_worsening` vs baseline trials is accepted by the validator but not yet supported — the absolute path executes.)
#### 21.2.6 Expression DSL + derived verdict (`evals/_expr.py`, `evals/_compile.py`)
A task's `[<layer>].expr` and `[verdict].trial` are tiny boolean expressions (`and`/`or`/`not`/parens) over handle names. `evals/_expr.py` is a self-contained **Interpreter** — a hand-rolled tokenizer + recursive-descent parser (precedence `not > and > or`, chained operators flattened to n-ary nodes) to a small immutable AST — with no `eval`/`exec`/`ast` and no third-party dep. `compile_expr` folds the AST into a `compose.py` `AllOf`/`AnyOf`/`Not` check tree over the layer's `name -> Check` handle map (built by `evals/_handles.py`, the **Factory + Composite** that turns each binding into a check). The **verdict is derived, not re-run**: the per-trial `Rubric` evaluates the `gate` and `rubric` layer checks *once*, and `[verdict].trial` is a boolean fold (`eval_bool`/`verdict_passed`) over their already-decided results with **skipped-neutral** semantics (a layer that did not run — e.g. the rubric layer with no judge — is neutral, exactly like an unavailable child of `AllOf`/`AnyOf`). Folding the verdict from the layer results instead of compiling it as a third check is what keeps the judge / test-suite single-shot.
### 21.3 Registry — decorator + entry points
In-tree metric builtins self-register via the `@register_metric` class decorator (each `builtins/*` and `execution/*` module decorates its class; `builtins/__init__` and `execution/__init__` import them so the decorators fire). The extension surface is four entry-point groups, each with an in-tree-wins dedup:
- **`coding_agent_playbook.metrics`** — out-of-tree `Metric`s (renamed from the old `…​.evaluators`); `@register_metric`. An out-of-tree metric **must** declare a `normalizer`.
- **`coding_agent_playbook.checks`** — out-of-tree custom grader `Check` factories, resolved by `get_check(id, **kwargs)` from a task's `{check = "<id>", …}` handle; `@register_check`. The in-tree `threshold`/`non_regression`/`file_*`/`answer_matches`/`pass_at_k`/`pass_pow_k` ids register here too.
- **`coding_agent_playbook.gates`** (new) — out-of-tree composed boolean gates, resolved by `get_gate(name)` from a gate-layer `{ref = "<name>"}`; `@register_gate("name")`. The engine ships none.
- **`coding_agent_playbook.rubrics`** — out-of-tree named rubrics, resolved by `get_rubric(name)` from a rubric-layer `{ref = "<name>"}`; `@register_rubric("name")`. The engine ships none.

The list is never hardcoded; **in-tree builtins win** over an entry point reusing a name. Metric selection helpers (`evaluators/metric.py`):
- `all_metrics()` — builtins + entry points, deduped by name.
- `static_metrics()` — every metric with `not needs_project` (the `playbook metrics` default set).
- `execution_metrics()` — every metric with `needs_project` (`coverage`, `test_pass_rate`); `--run-tests` adds these.
- `get_metric(name)` — a fresh instance, or `KeyError`.
### 21.4 Aggregation — `Rubric.evaluate` + the cost-tiered scheduler
`Rubric.evaluate(ctx, measurements, *, strict=False, fail_fast=False, max_workers=1) -> EvaluationReport` replaces the old free `grade()`. It runs its ordered checks through the cost-tiered scheduler (`evaluators/scheduler.py`) and folds the `CheckResult`s into one report. Each metric-backed check (`_MetricCheck`) grades on the metric's **normalized 0–1 score** (every metric owns a `Normalizer`, so direction is already baked in — higher is always better), per scope, matching the baseline by `(metric.name, scope_key)`:
- **existing scope:** `worsening = base_score − cand_score` (a *drop* in goodness); `> max_worsening` ⇒ `fail`/`kind="regression"`; otherwise the absolute level. The per-scope `score` is the normalized `0-1` goodness.
- **new scope:** absolute only, `kind="new"`. **removed scope:** ignored.
**Gate-boundary semantics** on the normalized score are higher-is-better and strict-below: a score *strictly below* `fail` fails, *strictly below* `warn` warns, exactly-on is `ok` (so coverage of exactly `0.8` with `warn=0.8` is `ok`, `test_pass_rate` of exactly `1.0` with `fail=1.0` is `ok`). Because direction lives in the normalizer, a worse-when-larger raw metric (`cyclomatic_complexity`) and a better-when-larger one (`coverage`) share the one rule.
Two aggregates fall out: the **gate** (`passed` = every *required, run* check passes; under `strict` no required run check may carry a `warn` leaf; skipped checks are neutral) and the **composite** (weight-normalized mean of the run checks' `score` over checks with `weight > 0`, spanning all families uniformly; `None` when no weights are set). The metric-backed check `mode` is `regression` (default), `absolute`, or `both` (regression failure takes precedence, then absolute), set when the check is built.

**The scheduler (`evaluators/scheduler.schedule`)** is the Strategy a `Rubric` (and the composers) use to run checks: **cheapest-tier-first** (`DETERMINISTIC` → `EXECUTION` → `JUDGED`), results always returned in **authored order**, with an optional **short-circuit** (`op="and"` stops descending into costlier tiers the moment a required check fails; `op="or"` stops on the first pass) and optional within-tier `concurrent.futures` concurrency (`max_workers > 1`; the default `1` is the deterministic path CI uses). The headline guarantee: with the short-circuit on, a lost deterministic gate **never grades the JUDGED tier** — the LLM judge is never invoked. Eval scoring turns it on only where it cannot change a result (see `CompiledTask.short_circuit_safe`). `Rubric.evaluate` defaults to `fail_fast=False` (complete report); the runner passes `fail_fast=True` for cost-saving, which `playbook eval --run --full-scoring` flips off.
### 21.5 Standalone gate — `playbook metrics` (`commands/metrics.py`)
```
playbook metrics [PATHS…] [--baseline git:REF|DIR] [--mode regression|absolute|both]
                 [--strict] [--run-tests] [--test-cmd "…"]
                 [--format text|json] [--repo-root DIR]
```
- **Default targets** — the repo's `src/` if it exists, else the repo root; directories recurse for `*.py`, skipping dotdirs and common ignores (`__pycache__`, `.venv`, `venv`, `node_modules`, `build`, `dist`, `.git`, `.tox`, `.mypy_cache`).
- **Default checks** — one metric-backed check per `static_metrics()` metric (fast, air-gapped), assembled into one `Rubric` via the shared `metric_check()` factory. `--run-tests` (or `[metrics] run_tests`) additionally builds a `ProjectHandle` and adds the `execution_metrics()` checks (run once).
- **Baseline** — static via `git show <ref>:<relpath>` (`git:` form) or the matching relative file under a `<dir>`; a file missing from the baseline is treated all-new. Execution baseline via temp `git worktree` (`git:`) or running in `<dir>`. `regression`/`both` without a baseline degrade to `absolute` with a note.
- **Config** — a `[metrics]` table in `.coding-agent-playbook.toml` (parsed by `config.parse_metrics_config` into a `MetricConfig`); CLI flags override it.
- **Exit codes** — `0` pass; `1` when `report.passed` is `False` and `fail_on_breach`; `2` on usage errors (bad path, bad baseline ref/dir, unparseable `--test-cmd`, malformed/invalid `[metrics]` config).
- **Output** — `--format text` shows only `warn`/`fail` findings grouped by file plus a summary; `--format json` includes every finding (`ok` too) for machine consumption.
**Pre-commit:** the engine ships a `repo: local`, `language: python` hook `playbook-metrics` running `playbook metrics --baseline git:HEAD` — **static only**, never the suite. Execution non-regression belongs in CI or a separate, off-by-default hook. (The hook diffs the working tree against `HEAD`, not the index, which is exact for the common all-staged case.)
### 21.6 Eval `[gate]`/`[rubric]`/`[verdict]`/`[aggregate]` wiring — live (v1.1)
The eval task schema (§6.5.3, §15.2) declares its evaluation as layer blocks, each a `[<layer>.bind]` handle table + an `expr`. `evals/task.py::compile_eval_task` → `evals/_compile.py::compile_task` turns them into one `CompiledTask`:
- `[gate]` / `[rubric]` → `evals/_handles.py::build_handles` turns each handle binding into a `Check` (a `{check=…}` via `get_check`, a `{ref=…}` via `get_gate`/`get_rubric`, a `{rubric=[…]}` group via `Rubric.of` + a `ThresholdCheck`, or a boolean `{all_of/any_of/not=…}` group), then `compile_expr` folds the layer `expr` into a `compose.py` check tree labeled with the layer id. Each present layer is one named check (`id="gate"` / `id="rubric"`) inside the per-trial `Rubric` (named `task.id`).
- `[verdict].trial` → parsed to an AST; the verdict is **derived** from the gate/rubric results (skipped-neutral), not re-run (§21.2.6).
- `[aggregate]` → the same handle/expr machinery over `pass_at_k`/`pass_pow_k` handles, plus `trials_needed = max(k)`.

The validator (`evals/validator.py`) **trial-compiles** the blocks (surfacing any unknown check/metric/ref, malformed binding, expr ident ⊄ bind keys, rubric weight-sum ≠ 1.0, or verdict ident ⊄ present layers) and does a light `[aggregate]` shape check. The scoring bridge (§15.3.1) walks the compiled check tree to find the referenced metrics, measures them over the candidate (vs the pristine `setup/` snapshot), and runs `Rubric.evaluate` — so both layers flow through **one report**, gate + composite, and the verdict is derived from it.
```toml
# task.toml — the layered model (replaces the [expected]/[metrics]/[rubric] triple)
[gate]
expr = "build and no_regress and src_unchanged"
[gate.bind]
build         = { check = "threshold",      metric = "cyclomatic_complexity", fail = 0.5 }
no_regress    = { check = "non_regression", metric = "coverage",              max_worsening = 0.0 }  # coverage must not drop
src_unchanged = { check = "file_unchanged", path = "src/pagination.py" }
[rubric]
expr = "quality"
[rubric.bind]
quality = { fail = 0.8, rubric = [
  { judge = "Findings are prioritized correctly", weight = 0.5 },
  { judge = "Each finding proposes a concrete fix", weight = 0.5 },
] }
[verdict]
trial = "gate and rubric"
```
With no judge configured the `[rubric]` layer reports `available() is False` and skips; the report is the deterministic `[gate]` layer only, and the derived verdict treats the skipped rubric layer as neutral. With `--judge llm` the rubric criteria score against the captured diff and fold in. All thresholds are 0–1 normalized (every metric owns a `Normalizer`, §21.1).
### 21.7 Invariants
- **Single responsibility — `Metric` measures, `Check` grades, `Rubric` aggregates.** No fused `Evaluator`; no free `grade()` (it is `Rubric.evaluate`); no `value_kind`/`to_score`/`default_*`/`extra_evaluators`. A metric becomes a gateable thing only by wrapping it in a `Check` (a threshold). A `Rubric` is also a `Metric`, so check trees compose (Composite) and nest.
- **Air-gapped / no new hard deps.** Core is stdlib-only (`ast`, `dataclasses`, `enum`, `subprocess`, `xml.etree`, `tempfile`, `importlib.metadata`); `radon` is the only optional extra (`[metrics]`, lazy import via `available()`); execution metrics shell out to the *target's* `pytest` and parse XML with stdlib — no playbook dep. The engine + static `playbook metrics` run with nothing extra installed.
- **Normalization lives on the `Metric`; `higher_is_worse` is gone.** Every metric owns a `Normalizer` (`Ramp`/`Percent`/`Identity`) mapping raw→0–1 goodness (higher = better); the `Check` grades on that score and never reasons about direction. All thresholds (`warn`/`fail`/`max_worsening`) are 0–1 cutoffs. Out-of-tree metrics **must** declare a `normalizer`.
- **Registry via decorator AND entry points** — metrics under `coding_agent_playbook.metrics` (`@register_metric`), grader checks under `coding_agent_playbook.checks` (`@register_check`, resolved by a task `{check=…}`), composed gates under the new `coding_agent_playbook.gates` (`@register_gate("name")`, resolved by a gate-layer `{ref=…}`), named rubrics under `coding_agent_playbook.rubrics` (`@register_rubric("name")`, resolved by a rubric-layer `{ref=…}`); never hardcode the list; never instantiate out-of-tree metrics/checks/gates/rubrics directly. In-tree builtins/registrations win on a name clash.
- **A check is `(type) × (metric|judge) × kwargs`.** `check = "threshold"|"non_regression"` over a registered `metric=` (a `Metric`) or a `judge=` criterion (a `JudgeMetric` — an llm-judge criterion *is* a metric); non-regression works on any metric incl. judged. Weights live only inside a `rubric` group (sum to 1.0).
- **The verdict is derived, not re-run.** `[<layer>].expr` / `[verdict].trial` are a tiny boolean DSL (`evals/_expr.py`) over handle names; the per-trial `Rubric` evaluates each layer once and the verdict is a boolean fold over the results (skipped layer = neutral), so the judge / test-suite is never double-invoked.
- **Cost-tiered short-circuit.** The scheduler runs checks `DETERMINISTIC` → `EXECUTION` → `JUDGED`, so a failing deterministic gate **never invokes the LLM judge**; results stay in authored order. `--full-scoring` forces every check. The short-circuit may only save work, never change a result, so scoring disables it for a task where a skipped layer could flip the outcome (`CompiledTask.short_circuit_safe`): a verdict that is not a pure conjunction of every present layer (`gate or rubric`, `not …`, `rubric` alone beside a gate — which passed on a failing gate — or a weighted verdict), or an `[aggregate]` over a layer the short-circuit could skip.
- **Non-regression is primary** (new scopes fall back to absolute); it compares the normalized goodness (`worsening = base_score − cand_score`). Deterministic static/execution use `max_worsening=0`; judged uses a `threshold` floor + n-sample averaging; `test_pass_rate` has an optional flaky-retry.
- **Execution is opt-in and excluded from the default pre-commit** (side effects + cost); the static gate is the only thing that runs on every commit.
- **CI parity** — `mypy` + `pytest -q` + `ruff` from the repo root with no path args.
### 21.8 Open caveats (documented, not blocking)
- **CBO≈** undercounts under duck typing (rendered approximate); **DIT** cross-module bases are approximated and low-signal in idiomatic Python; **MI** variant is pinned (SEI 0–100); **RFC/NOC/Abstractness/Distance/LCOM1-2/standalone Halstead** are intentionally absent.
- **Execution cost/flakiness:** running tests is slow and can be flaky; test non-regression is exact only modulo flaky-retry; coverage non-regression assumes a stable test set. The two-run baseline (`git worktree`) is the cost.
- **Judged scoring is stochastic** — meaningful only with ≥N samples; single-sample judged scores are advisory. The judge signature is reconciled (§21.2.3, Option A) — no forward-compat debt remains.
## Appendix A: Full worked example
Walking through `risk-models`, a counterparty risk scoring service, going from zero to a fully synced playbook.
### A.1 Starting state
```
risk-models/
├── pyproject.toml              # FastAPI app with pydantic, sqlalchemy, pytest
├── src/risk_models/
│   ├── __init__.py
│   ├── api/
│   │   └── routes.py
│   ├── models/
│   │   └── counterparty.py
│   └── services/
│       └── scoring.py
├── tests/
│   ├── api/
│   │   └── test_routes.py
│   └── services/
│       └── test_scoring.py
├── Dockerfile
└── .github/workflows/ci.yml
```
`pyproject.toml`:
```toml
[project]
name = "risk-models"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "pydantic>=2.9",
    "sqlalchemy>=2.0",
    "httpx>=0.27",
]
[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]
```
### A.2 Step 1: install
```bash
$ uv add --dev coding-agent-playbook playbook-rules-bnp
```
### A.3 Step 2: init
```bash
$ playbook init
```
User answers the prompts. The tool writes:
- `.coding-agent-playbook.toml` (with `[output] commit = false`)
- `.coding-agent-playbook.local.toml`
- updated `.gitignore`
- merged `.pre-commit-config.yaml`
- prints the `pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge` command for you to run (init never runs pre-commit itself)
- runs `playbook sync` (which also writes the managed `.gitignore` block)
### A.4 Step 3: result
Generated files (all with sentinel headers; all local-only — listed in the managed `.gitignore` block, never committed):
```
AGENTS.md
.continue/
├── rules/
│   ├── 00-project-context.md       # engine
│   ├── 10-python-house-style.md    # engine
│   ├── 20-tooling-baseline.md      # engine
│   ├── 30-bnp-banking.md           # overlay
│   ├── 50-python-typing.md         # overlay (overrides engine)
│   ├── 50-python-error-handling.md # engine
│   ├── 50-python-logging.md        # engine
│   ├── 60-fastapi.md               # engine (because fastapi detected)
│   ├── 70-pydantic-v2.md           # engine (pydantic 2.x detected)
│   └── 70-sqlalchemy-v2.md         # engine
└── prompts/
    ├── refactor.md
    ├── generate-tests.md
    ├── review.md
    ├── explain.md
    └── pii-scan.md                 # overlay
.claude/
├── CLAUDE.md
└── commands/
    ├── refactor.md
    ├── generate-tests.md
    ├── review.md
    ├── explain.md
    └── pii-scan.md
.opencode/
└── command/
    ├── refactor.md
    ├── generate-tests.md
    ├── review.md
    ├── explain.md
    └── pii-scan.md
.coding-agent-playbook.lock
```
### A.5 Step 4: usage
Engineer opens VS Code with Continue.
```
User opens src/risk_models/api/routes.py
→ Continue loads:
  - All scope=always rules (5 rules)
  - 60-fastapi.md (matches glob **/api/**/*.py)
  - 50-python-typing.md (matches glob **/*.py)
  - 70-pydantic-v2.md (matches glob, since pydantic models are imported)
User types: "/generate-tests for the score_counterparty endpoint"
→ Continue invokes .continue/prompts/generate-tests.md
→ The fully rendered prompt includes:
  - Project context (project_name, project_kind, pytest conventions)
  - Inlined body of python-typing rule       (via includes_rules)
  - Inlined body of pytest rule              (via includes_rules)
  → All three are guaranteed in context, regardless of which files are open
→ Assistant generates tests/api/test_routes.py extension following the mirror layout
```
The `includes_rules:` mechanism is what gives `/generate-tests` its reliability. Even if the user invokes it from a markdown file or an unrelated module, the typing and pytest rules are still in scope because the prompt declared them as dependencies. Without `includes_rules:`, the agent would only see whichever scoped rules happened to match the currently-open file's globs — which on a markdown file would be none of them.
### A.6 Step 5: update
Two weeks later, the engine releases v0.4.1 with improved test-generation prompt wording.
```bash
$ uv lock --upgrade-package coding-agent-playbook
$ playbook sync
✓ Rendered all artifacts
✓ Wrote 1 file via continue adapter (.continue/prompts/generate-tests.md updated)
✓ Wrote 1 file via claude_code adapter (.claude/commands/generate-tests.md updated)
✓ Wrote 1 file via opencode adapter (.opencode/command/generate-tests.md updated)
✓ Updated .coding-agent-playbook.lock
Summary: 3 files changed
```
Engineer commits the dependency bump (`uv.lock`) — the regenerated files are local-only, so the review happens on the engine/overlay release itself. Teammates pulling the bump must **update their environment first** (`uv sync`) and then run `playbook sync`: the `post-merge` hook re-renders only with the engine and overlays *already installed* (the `language: system` init hook uses their current venv; a remote `language: python` hook uses the `rev:`-pinned engine), so on its own it renders the old wording. (Under `[output] commit = true` the engineer commits the regenerated diff instead, and the team reviews it like any other config change.)
### A.7 Step 6: generated output stays out of commits
A junior developer hand-edits `.continue/rules/50-python-typing.md` without going through the source, then force-adds it to share the tweak.
```bash
$ git add -f .continue/rules/50-python-typing.md
$ git commit -m "tweak rule"
[pre-commit running]
playbook-no-generated-output:
Generated output is staged for commit ([output] commit = false keeps it local-only):
  .continue/rules/50-python-typing.md
Unstage it (the files stay on disk) with:
  git rm -r --cached -- .continue/rules/50-python-typing.md
[commit blocked]
```
The dev unstages it and either adds a repo-local override under `playbook/rules/` or files a PR against the overlay to make the change properly; the next `playbook sync` (or checkout) overwrites the local hand-edit anyway. Under `[output] commit = true` the legacy `playbook-sync-check` hook blocks the same commit as drift instead.
## Appendix B: BNP overlay shape
For Max's reference, the BNP overlay layout in detail:
```
playbook-rules-bnp/
├── pyproject.toml
├── README.md
├── src/playbook_rules_bnp/
│   ├── __init__.py                         # registers OVERLAY
│   └── resources/
│       ├── rules/
│       │   ├── always/
│       │   │   └── 30-bnp-banking.md.j2
│       │   ├── languages/python/
│       │   │   └── typing.md.j2            # OVERRIDES engine python-typing
│       │   ├── compliance/
│       │   │   ├── pii-handling.md.j2
│       │   │   ├── dependency-allowlist.md.j2
│       │   │   └── audit-logging.md.j2
│       │   └── infra/
│       │       ├── litellm-routing.md.j2
│       │       └── air-gapped-net.md.j2
│       └── prompts/
│           ├── pii-scan.md.j2
│           └── compliance-review.md.j2
└── tests/
    └── test_rules_compile.py               # smoke test that all .j2 files render
```
The overlay is small. It carries only what's BNP-specific. Anything generic (Python style, FastAPI conventions, pytest patterns) stays in the engine where every other team can benefit from improvements.
---
## Implementation order (recap)
Cross-referencing the prior conversation's track plan:
| PR | Track | What | LoC estimate |
| --- | --- | --- | --- |
| 1 | Track 1 | Project scaffolding + adapter ABC + source ABCs | ~400 |
| 2 | Track 1b | Canonical types (`Rule`, `Prompt`, `Skill`) with markdown round-trip | ~250 |
| 3 | Track 2a | Detector module | ~400 |
| 4 | Track 2b | Renderer module | ~250 |
| 5 | Track 2c | `FileSystemArtifactSource` + `FileSystemStateSource` | ~250 |
| 6 | Track 3 | Continue adapter | ~300 |
| 7 | Track 4a | Claude Code adapter | ~300 |
| 8 | Track 4b | AGENTS.md adapter | ~200 |
| 9 | Track 4c | OpenCode adapter | ~150 |
| 10 | Track 5 | CLI (`init`, `sync`, `check`, `validate`, `render`) | ~500 |
| 11 | Track 5b | Eval Tier 0 (task schema + loader + validator + `playbook eval --list/--show/<stub>`) | ~250 |
| 12 | Track 6 | Pre-commit integration + `.pre-commit-hooks.yaml` | ~150 |
| 13 | Track 7 | Initial Python rule pack (5 rules + 4 prompts + 8 eval tasks) | ~800 (mostly markdown + TOML) |
| 14 | — | SPEC.md, README, internal wiki page | this file |
Total: ~3900 lines of Python + ~800 lines of markdown/TOML content. 5-7 weeks at half-time, 2.5-3.5 weeks full-time.
Notes on sequencing:
- **Track 1 (PR 1)** adds the source ABCs (interfaces only, in `sources/base.py`) alongside the adapter ABC. The interfaces are public API from v1, so they ship in the scaffolding PR.
- **Track 1b (PR 2)** adds the canonical types (`Rule`, `Prompt`, `Skill` dataclasses) with markdown round-trip. Lands second because almost every subsequent module imports from `types.py`. Includes the round-trip property tests (Section 6.6.3).
- **Track 2c (PR 5)** adds the filesystem implementations after the detector and renderer because those modules' types (`Config`, `Facts`, `Lockfile`) are needed by `StateSource`.
- **Track 5b (Eval Tier 0)** lands after the main CLI because it adds CLI subcommands and one new validator pass. It is independent of the adapters — eval tasks are authoring-side artifacts and don't flow through any adapter.
- The source abstraction and the canonical types together add maybe two days of work to the early tracks but pay for themselves in test simplicity from PR 6 onward, and in clean serialization boundaries when the commercial product arrives.
---
*End of SPEC.md v0.18.*
---
## Changelog
### v0.18 (2026-10-14)
No command writes local overrides into the committed config, and the two that rewrite it — `playbook init` and `playbook check --refresh` — keep what `Config` does not manage. Two bugs, shared by a re-run of `init` and by `check --refresh` on a repo with a committed config: (1) each loaded the config through `load_config`, i.e. merged with the gitignored `.coding-agent-playbook.local.toml` (§7.2), and saved the result as the committed file — a personal `adapters_enabled = ["claude_code"]` turned the team's `["continue", "claude_code", "opencode", "shared_skills"]` into `["claude_code", "continue", "opencode", "shared_skills"]`, and a personal `[user_choices]`, `overlays_enabled` or `[output] commit` (which, on an `init` re-run, also picked the committed pre-commit hooks) landed in the commit; (2) the round trip through `Config` dropped every table `Config` does not carry — `[links]` and `[metrics]`, which `validate` and `metrics` read from the raw TOML — and every unknown key inside the tables it does carry (`[project] homepage`), although `init` promised to preserve what it does not know. **Behaviour change:** an `init` re-run's committed file now depends on the committed file, the answers and the detected facts only, a refresh's on the committed file and the detected facts only. Both exit 2 with nothing written on a committed file missing a required key (they used to complete it from the local file) and on a local file `Config` refuses (a malformed `[output]`, checked up front); a first `init` checks the latter too, where it used to write every file and fail only in its final sync. `check --refresh` no longer round-trips through `Config`, so only `[detector_cache]` changes (an explicit `adapters_enabled = []` or `description = ""` used to vanish, and `artifact_source`/`commit = false` to appear). Each config file is checked whole on its own, naming it, in every command: a syntax error, a non-UTF-8 byte or inline values nested too deeply (tracebacks, exit 1), a top-level `project`/`engine`/`storage`/`output`/`detector_cache`/`user_choices` that is not a table (a `TypeError`/`AttributeError`/`ValueError` traceback; a local one was blamed on the committed file, and a committed one hidden by a local table crashed only `init`/`check --refresh`), and a malformed `[output]` (its error now names the file) are `ConfigError`s, exit 2. A missing required key (`schema_version`, `[project] name`/`kind`, `[engine] version`) is a `ConfigError` (exit 2) in every command, where it was a `KeyError` traceback. `init` now checks `--overlays` even when a local `overlays_enabled` replaces it for its own sync: a local list used to hide an unusable `--overlays`, which was committed and broke every teammate's `playbook sync`. A first `init` writes the same bytes as before, except where the old writer was wrong: a detected dependency name that needs quotes is now written quoted in `[detector_cache]` (`"ruamel.yaml" = ">=0.17"`, which used to be re-read as a `ruamel` table; a non-ASCII name such as `Café_Pkg` used to make the file unparseable) — see the TOML writer bullet.
- **Section 7.1 (config)**: a missing required key is a `ConfigError`; each file is checked whole on its own before the merge (`config.check_config_file`: a file `tomllib` cannot read, a non-table `project`/`engine`/`storage`/`output`/`detector_cache`/`user_choices`, a malformed `[output]`), so the error names the file at fault; `init` checks each file on its own, then the config its final sync will load, before writing (a first run too); `init` and `check --refresh` keep the committed `[output] commit`, not a local one.
- **Section 7.2 (local overrides)**: the invariant — local overrides are read, never written back: `save_config_table` is the committed file's one writer and `commands/_committed_config.ConfigRewrite.save` its one caller, a `ConfigRewrite` being built only by that module's `plan_*` functions from the committed file alone (or with none, on a first `init`); an AST test pins the writers, the builders and that no importer of `_committed_config` references `load_config`; nothing rewrites an existing local file.
- **Section 12.1 (`playbook init`)**: safe to re-run (re-serialized, not clobbered); the order of the pre-write checks; what a re-run replaces (what `Config` owns, from the updated committed config, never merged with the old file: an omitted or empty `--overlays`, an empty description and a stale detector entry stay dropped; adapters are the committed list then each answered one it lacks; `schema_version`/`[engine] version`/`[storage]`/`[user_choices]`/`[output] commit` kept) and preserves (every other top-level key and the unknown keys of `[project]`/`[engine]`/`[storage]`/`[output]`, same parsed values); a re-run needs a complete committed file; comments, layout and literal spelling are not kept. The pre-commit hooks follow the committed `[output] commit`; the final sync still uses the merged config. `--overlays` is checked even when the local file's list replaces it.
- **Sections 12.4 / 12.5 (`playbook check --refresh`)**: rewrites only `[detector_cache]`, from the committed file alone, writing every other entry back as parsed (`plan_detector_cache_refresh`, no `Config` round trip); exits 2 with nothing written or printed on a committed file missing a required key or a local file that breaks the result.
- **Section 20.3 (state source)**: `FileSystemStateSource.read_committed_config_table()` reads the committed file alone and `has_committed_config()` says whether it exists; `save_config_table(table)` writes a decoded table verbatim (`save_config(config)` wraps it, unused by commands); `preview_config(table)` is what `load_config()` will return after that save, without writing; the rewrites are `commands/_committed_config`'s `plan_*` functions. `load_config()` keeps its merged behaviour, so `sync` and every other command still apply local overrides.
- **TOML writer**: `_toml.dump_toml` (moved from `sources/filesystem.py::_dump_toml`, which pushed that module past 500 lines) writes anything `tomllib` parses — tables and arrays of tables at any depth (the deliberate two-level `TypeError` is gone; preserved `[metrics.thresholds.<metric>]` tables nest three deep), a table's own keys before its sub-tables, empty tables, a non-empty array holding only tables as `[[…]]` sections and every other array (mixed, nested, empty) inline, tables in it as inline tables, keys quoted through `_toml.format_key`. `_toml.format_scalar` gains `float` (`float.__repr__`: `1.0`, `1e-05`, `inf`, `-inf`, `nan`, plus `-nan`, whose sign `repr` drops) and `date`/`datetime`/`time` (`isoformat`; a time with an offset or a sub-minute offset is a `ValueError`, as TOML cannot hold it); an integer too long for `str` is written in hex, and a negative one — no TOML literal holds it, and `tomllib` never yields one — is a `ValueError`. Other Python types still raise `TypeError`. Both walks are iterative — `_dump_toml` over tables and `format_scalar` over inline values — so no depth `tomllib` accepts can overflow the writer (a recursive table walk hits `RecursionError` at headers a few hundred levels deep, and `tomllib` builds headers with no depth limit). Four latent writer bugs are fixed, each with a regression test: `format_key` left non-ASCII keys (`café`) bare and `format_string` wrote U+007F raw, both unparseable; `format_scalar` passed every `int` to `str`, which raises `ValueError` past `sys.get_int_max_str_digits()` digits although `tomllib` reads such integers from `0x`/`0o`/`0b` literals (the Config, lockfile and manifest paths alike); and `_dump_toml` wrote keys and header parts raw instead of through `format_key`, so a key that needs quotes was valid TOML that `tomllib` re-read as a different structure — a detected `ruamel.yaml` dependency became a `ruamel` table on a first `init`, and a committed `[user_choices] "docs.style"` became a `docs` table on every `save_config` (`init` re-run, `check --refresh`). Config, lockfile and `.playbook/manifest.toml` bytes are unchanged wherever the old output parsed back correctly (golden tests). The manifest (§20.10) now also writes the float and date values YAML frontmatter yields (`applies_if`, `input_variables`, a skill's extra frontmatter), which used to stop `init`/`sync` with `TypeError: manifest TOML does not support value of type float`.
- **Implementation**: `config.py` (`check_config_file`, `Config.from_dict` running it and the required-key check, `parse_output_config(…, source=…)`; it re-exports `ConfigError`, `check_enabled_keys` and `check_config_tables`), the new `config_schema.py` (split from `config.py`: `ConfigError`, the enabled-key checks with an iterative table walk, `check_config_tables`, `required_value`), the new `config_entries.py` (`CONFIG_MANAGED_KEYS`, `CONFIG_MANAGED_TABLE_KEYS`, `unmanaged_config_entries`, `with_unmanaged_entries`), `sources/filesystem.py` (`read_committed_config_table`, `has_committed_config`, `preview_config(table)`, `save_config_table`, `save_config` through it, per-file checks and decode errors in `_read_config_file`), `_toml.py` (`dump_toml`, moved here, and the iterative `format_scalar`), `harness/manifest.py` (docstring only), the new `commands/_committed_config.py` (`ConfigRewrite`, `plan_first_config`, `plan_committed_update`, `plan_detector_cache_refresh`, `detector_cache_table`), `commands/init.py` (`_plan_config`, `_fresh_config`, `_apply_answers`, `_adapters_union`, `_overlay_lists_to_check`) and `commands/check.py` (`_refresh`).
- **CI**: `tests/cli/test_init.py` (a re-run with every local override leaves the committed file byte-identical, committed `[user_choices]` included, and the local file untouched; the committed hooks ignore a local `[output] commit = true`; `[links]`, `[metrics]` with 3-level thresholds, float weights and arrays, a future table with a date, a mixed array, nested tables and an array of tables, and a future top-level key come back as the same parsed values, compared type-strictly; an emptied `--overlays`, a dropped description and a stale detector entry stay dropped; unknown keys inside `[project]`/`[engine]`/`[storage]`/`[output]` survive; a local file `Config` refuses, and a committed file missing a key only the local file supplies, exit 2 with every file unchanged), `tests/cli/test_check.py` (`check --refresh` with local overrides changes only `[detector_cache]` and leaves the local file untouched; the same two exit-2 cases), `tests/unit/test_committed_config.py` (each `plan_*` builder: the committed file alone, a refresh changing nothing but `[detector_cache]`, a first-run plan refusing an existing file, both plans refusing a broken local file or a committed file missing a key; an AST walk: the writers and `ConfigRewrite` builders are named only in `_committed_config`, and no importer of it references `load_config` — four bypass mutants are caught), `tests/unit/test_sources_filesystem.py` (the committed-only reader: local file ignored even when broken, missing file, `ConfigError` naming the committed file; `save_config_table`/`save_config`, unknown keys of managed tables; `preview_config` writes nothing; a syntax error, a non-UTF-8 byte and deep inline nesting are `ConfigError`s naming either file; a 1000-level header loads; every misread table shape names the local file from `load_local_overrides`, `load_config` and `preview_config`, and the committed file even when a local table hides it; a `save_config`/`load_config` round trip keeps `"docs.style"` and `ruamel.yaml` keys), `tests/cli/test_check.py` (`check`, `check --refresh`, `sync` and `validate` name the local file for a local non-table, and refuse a committed non-table a local table hides; `check --refresh` keeps a hand-written file's explicit empties), `tests/cli/test_unusable_overlays.py` (`init` refuses an unusable `--overlays` behind a usable local list, and reports both lists), `tests/unit/test_config.py` (`CONFIG_MANAGED_KEYS` and `CONFIG_MANAGED_TABLE_KEYS` equal what a full `to_dict` writes, the full fixture sets every dataclass field off its default, every key is read by `from_dict`; a missing required key or a non-table `project` is a `ConfigError` naming the file, the key and the line to write; `unmanaged_config_entries`/`with_unmanaged_entries`), `tests/unit/test_dump_toml.py` (a round-trip corpus over every TOML value type, a fixed-point check, the rendering shape, golden Config/lockfile bytes, tables, arrays of tables and inline values nested 200–400 deep written with 60 stack frames to spare, integers past the int-to-str limit, Config keys that need quotes), `tests/unit/test_toml.py` (integral floats, `-nan`, hex for huge ints — with the int-to-str limit pinned by the `default_int_max_str_digits` fixture, so `PYTHONINTMAXSTRDIGITS` cannot change the outcome — decimal when the limit is off, inline nesting twice the recursion limit) and `tests/harness/test_manifest_roundtrip.py` (golden manifest bytes; float and date frontmatter through `write_manifest`/`read_manifest` and `import-harness`). Round trips compare with `tests/toml_equality.py`, which checks exact types, float signs (NaN-aware) and datetime offsets — Python `==` passes `1.0` written as `1`.
### v0.17 (2026-10-14)
Bundled opt-in packs and the `superpowers` pack. The pack itself is purely additive: no rendering, config-schema, or lockfile change; it is consumed through the existing overlay path and rendered by the v0.15 native-skill adapters, and leaving or overriding it is settled by the v0.16 lockfile leftover policy. The config hardening below changes what is *accepted*: the enabled-list shapes the engine used to misread silently are now refused (other unknown keys are still ignored).
- **Section 11.5 (new)**: packs are importable subpackages under `coding_agent_playbook.packs.*`, layered exactly like overlay packages but shipped in the engine wheel (no extra install), off by default, and enabled by listing the dotted package name in the top-level `overlays_enabled` key. It documents the two configuration mistakes the pack invites and how each is now caught (see the config-hardening bullet): the `[overlays]`/`[adapters]` table form is refused with a `ConfigError`, and a misspelled pack name is flagged by `sync`, `validate`, `check` and `init`. "Opting out and overriding" applies §4.2 step 9 to a pack: removing it, or overriding one of its skills with fewer `scripts/`/`references/` files, deletes the pristine, untracked pack files from every skill root on the next sync and prunes the emptied directories; edited, tracked, and user-added skill files are kept; the degraded Continue prompts are removed by `cleanup_stale`, edited or not, tracked or not.
- **Section 11.5.1 (new)**: the `superpowers` pack: 15 skills ported near-verbatim from the Superpowers skills library (v7.0.0, MIT), the self-containment transformations, what was dropped and why, the per-adapter rendering (`.claude/skills/`, `.opencode/skills/`, `shared_skills/` byte-identical via the `SkillWriter`, `SKILL.md` with the sentinel as its first body line; Continue degrades to prompts; `agent_harness` `skills/<id>/`), the executing-plans → subagent-driven-development sibling-script dependency (an override of `subagent-driven-development` must ship the two scripts executing-plans calls), and the MIT attribution (`LICENSE` + `ATTRIBUTIONS.md`, plus a `references/LICENSE` copy in every skill so the notice travels with each synced skill directory).
- **Sections 5.1 / 6.3**: `packs/` added to the engine layout. The engine's default `resources/` still ships no skills; the only bundled skills live in the opt-in pack. Section 6.3.2 now notes that only its step 1 (render as a prompt) is implemented.
- **Config hardening (same release; Sections 4.2, 7.1, 7.2, 10.7, 10.8, 11.1, 11.5, 12.1–12.6)**: `Config` read only the top-level `overlays_enabled`/`adapters_enabled` keys, while the SPEC and README showed an `[overlays] enabled` / `[adapters] enabled` table form that parsed as two empty lists — `playbook sync` exited 0, rendered only `AGENTS.md`, and settled every other adapter's earlier output as leftovers ("1 files written, 278 removed" in a repo synced with the pack); a string value became a list of characters. **Behaviour change:** the new `config.ConfigError` (a `ValueError`) refuses an `overlays`/`adapters` key of any shape (table, dotted key, plain value), an `overlays_enabled`/`adapters_enabled` key inside any table at any depth (TOML nests a key written after a `[table]` header there — so applying the fix-it hint in place, or appending the key to an init-written file that ends with `[detector_cache.frameworks]` or a local file that is `[user_choices]` only, would still be ignored), a nested `overlays`/`adapters` table holding `enabled`, a close misspelling of either key (`difflib`, case- and separator-insensitive), and any `*_enabled` value that is not a list of non-empty strings (an empty name used to crash in `importlib`), with a message that names the file (and table), quotes the value and shows the top-level line to write instead, "at the top of the file, above the first [table] header". One helper, `config.check_enabled_keys`, walks every table of each of `.coding-agent-playbook.toml` and `.coding-agent-playbook.local.toml` before the §7.2 merge (`FileSystemStateSource.load_config`; `load_local_overrides` lets `init` check the local file up front) and again in `Config.from_dict` for other callers. `parse_output_config` raises `ConfigError` too. `cli.main` maps `ConfigError` like a missing config — `error: <message>`, exit 2 — and every command that loads the config does so before writing or deleting anything (`sync` in every mode, `--check-staged` under `commit = true` included; `check` incl. `--refresh`; `validate`; `render`; `eval`; `init`). Unusable overlays: `_sync_preflight.missing_overlays` became `unusable_overlays`, which also refuses an importable package with no `resources/` directory (it would contribute nothing, e.g. the parent `coding_agent_playbook.packs`), so every sync mode refuses it too. It now imports each overlay (`find_spec` alone passed a package that raises at import time, and a dotted name whose parent raised escaped as a traceback): any import failure is a reason, quoting the error unless it only says the package does not exist; a `ModuleNotFoundError` for an overlay's own dependency is named as such. `sources.filesystem._resource_subdir` correspondingly skips a package whose import raises, like a missing one, so discovery never crashes before the check can report it. The check is shared by `validate` (a `FAIL overlays_enabled: <name>: <reason>` validation error, exit 1), `check` (a `✗` line under `Overlays:` and no clean Drift claim; still exit 0 as a diagnostic) and `init` (exit 2, nothing written; it checks `--overlays`, or the local file's `overlays_enabled` when that replaces it), each reporting every unusable overlay on its own line. A pack-like typo lists the bundled packs (`_sync_preflight.bundled_packs`, via `pkgutil`). Docs: every config example now uses the top-level keys (`.local.toml` overrides replace lists), and §7.1 shows the `[detector_cache]` table the code reads and writes (was `[detector.cache]`).
- **Tooling**: `[tool.ruff] extend-exclude = ["src/coding_agent_playbook/packs/*/resources"]` keeps vendored text byte-faithful, because newer unpinned ruff also formats code blocks inside markdown.
- **CI**: `tests/packs/` (identity, opt-in, per-skill layout, `references/` inventory + license copies, self-containment incl. path-mention resolution, executable scripts + `bash -n`, end-to-end opt-in sync/validate/`sync --check` with the `SKILL.md` sentinel body line, byte-identical `.claude/skills/`/`.opencode/skills/`/`shared_skills/` copies and the Continue prompts' sentinel line + vendored body, an opt-in `agent_harness` sync (`skills/<id>/` copies, script flags in `.playbook/manifest.toml`, removal on opt-out), opt-out removal from every skill root that keeps a consumer-added and an edited file, SKILL.md-only and fewer-references override removal, the mutating cases in hermetic real git repos) and `tests/cli/test_validate_links.py::test_superpowers_pack_has_self_contained_links` (the PR-L link gate over the pack). Config hardening: `tests/unit/test_config_enabled_keys.py` (each table in each file, both tables, dotted keys, an enabled key nested under `[engine]`/`[output]`/`[project]`/`[detector_cache.frameworks]` and under the local `[user_choices]`, misspelled keys, empty names, non-list and non-string values, framework names that resemble the legacy names, valid configs and the `to_dict`/`from_dict` round trip unchanged), `tests/unit/test_sync_preflight.py` (unimportable vs. no-`resources/` overlays, packages raising at import or whose parent raises, a missing dependency, `pkgutil` pack discovery of subpackages only, the pack-typo hint), `tests/cli/test_config_errors.py` (every config-loading command exits 2 with the tree byte-identical — for the table form, the hint applied in place, keys appended after the last table, a misspelled key and an empty name — `--check-staged` under `commit = true`, the local-file case, `init`, and the safety test: a repo synced with the pack, then switched to any of those shapes in the committed or the local file, is left byte-identical — lockfile and `.gitignore` included — by every sync mode, in a hermetic real git repo) and `tests/cli/test_unusable_overlays.py` (`validate`/`check`/`init` with a misspelled pack, the parent `coding_agent_playbook.packs`, an unrelated name, packages raising at import and several at once, one line each; `init` checking the local file's list; every sync mode refusing a package with no `resources/` or one that raises at import).
### v0.16 (2026-10-14)
Generated output is **local-only** in consumer repos by default. Rendered files are build products of the installed engine + overlays + `playbook/`, so they are gitignored and regenerated on each machine instead of being committed. Behaviour change for consumers: new repos (and repos without an `[output]` table) stop committing output; `[output] commit = true` restores the pre-v0.16 committed-output policy.
- **Section 7.1 (config)**: new `[output]` table — `commit` (bool, default `false`), parsed by `config.parse_output_config` into `config.OutputConfig`; a non-bool is a `ValueError` carrying the value. `Config.output` is `None` when the table is absent (sparse round-trip) and `Config.commit_output` is the effective value. `playbook init` writes `commit = false` explicitly and preserves an existing value.
- **Sections 4.2 / 5.3 (data flow, consumer layout)**: new step 9 — the output policy. `commit = false`: an engine-owned managed block in the consumer's `.gitignore` lists every generated file root-anchored and escaped (skill directories — any directory holding a written `SKILL.md` — collapse to `/<dir>/`), plus the lockfile. Byte-preserving (CRLF, missing final newline), atomic, idempotent; malformed markers fail with file + line. `.gitignore` is never in the lockfile. `commit = true`: the block is removed. Leftover settling (below) runs under **both** settings.
- **Sections 12.2 / 12.3 / 12.3.1 (sync)**: write mode applies/removes the block and, under `commit = false`, warns on stderr about generated paths git still tracks with the exact `git rm -r --cached -- …` (read-only `git ls-files`, 10 s timeout, silent when git cannot answer; exit code unchanged). `--check` also reports a stale/missing/malformed block as drift. New `--check-staged` (mutually exclusive with `--check`) fails when a staged path is generated output; no-op under `commit = true` or outside a git repo.
- **Section 13 (pre-commit)**: new consumer hooks `playbook-sync` (`post-checkout`/`post-merge` auto-sync) and `playbook-no-generated-output` (pre-commit guard), both `minimum_pre_commit_version: "3.2.0"`; `playbook-sync-check` is kept as the legacy `commit = true` hook. The `playbook init` starter renders per policy and, for `commit = false`, adds `default_install_hook_types: [pre-commit, post-checkout, post-merge]` and `default_stages: [pre-commit]`.
- **Review hardening (same release)**: leftovers of an earlier sync (a removed skill's `SKILL.md`/scripts, a disabled adapter's output) are owned through the previous lockfile — pristine untracked ones deleted, the rest carried forward (and, under `commit = false`, kept in the managed block), and always caught by `--check-staged` (§4.2 step 9). Under `commit = true` the same settling runs and kept leftovers are listed on stderr (`_sync_output.report_kept_leftovers`): **behaviour change from v0.15** — a removed skill's committed (tracked) files are no longer deleted; they stay until the user runs `git rm`. This is the **single deletion policy for skill dirs**: adapters' `cleanup_stale` never deletes inside one (`agent_harness` `skills/<id>/` included), a file absent from the previous lockfile is never deleted, a skill-dir file/folder swap displaces only what the policy would delete, and the pre-v0.15 lockfile claim needs unchanged `SKILL.md` bytes. Bounds: deletion only inside installed adapters' declared `Adapter.output_locations` (§10.1), never under `.git/` or through a symlink; pruning never above a declared directory or into a symlinked root's target; a skills root that is a dangling symlink is skipped with a warning. The tracked check asks `:(literal,icase)` pathspecs, matches in NFC or by file identity, and keeps everything when git cannot answer inside a work tree. Stale-vs-written comparisons use file identity; `--check`/`--check-staged` decide skill ownership on the real tree (`deciding_ownership_against`), `HARNESS.md` indexes only what it emits, and `--check` names the blocker of a refused swap (the one documented exception to "`--check` exits 0 after a successful sync", §12.3). `--check`/`--check-staged` render into an empty scratch dir (no working-tree copy: dangling symlinks, unreadable dirs, FIFOs and big venvs no longer crash or slow the guard) and map paths back through the repo's own symlinks, so they agree with write mode. Every `sync` mode refuses to run when an `overlays_enabled` package is not importable; a missing adapter is a warning. Entries are NFC-normalised (plus the as-written form); a BOM before a first-line block is tolerated and preserved; the atomic write uses a unique temp name. The `git rm -r --cached` hint gains `git -C <repo-root>` when run from elsewhere. `init` swaps a verbatim pre-v0.16 `coding-agent-playbook-sync` hook for the new pair, warns about a hand-edited one, and notes a missing `default_stages`. Docs: §12.3 limits CI use of `--check` to `commit = true`; §13.1 documents `additional_dependencies`/`rev` for the remote hooks (or the init `language: system` hooks); §12.1/A.3 say init prints (not runs) `pre-commit install`; §14.2/§14.3/A.6 drop the "review the regenerated diff" assumption under `commit = false`.
- **Implementation**: `gitignore.py` (stdlib-only entries + managed block), `git_client.py` (`GitClient` protocol + `SubprocessGitClient`), `commands/_sync_output.py` (policy glue), `commands/_sync_orphans.py` (lockfile-based ownership of leftovers: `LeftoverPolicy`), `commands/_output_locations.py` (deletion allowlist + prune bounds), `_file_identity.py` (`FileSet`), `adapters/_prior_output.py` (the previous lockfile as proof + the installed leftover judge), `commands/_sync_preflight.py` (overlay/adapter availability), `commands/_precommit_merge.py` (existing-config merge + legacy swap), `commands/sync.py` (`--check-staged`, empty-scratch render shared with `--check`), `cli.py`, `commands/init.py`, `resources/precommit/config.yaml.j2`, `.pre-commit-hooks.yaml`, with tests (`tests/fakes.py::FakeGitClient` instead of patching `subprocess`; `tests/conftest.py::apply_hermetic_git_env` drops inherited `GIT_*` and the default global excludes).
### v0.15 (2026-10-14)
Native skills for every Agent-Skills harness plus the cross-agent `shared_skills/` hub, and two skill-output bug fixes. Additive for authors — the canonical skill format is unchanged.
- **Section 10.8 (NEW)**: the `shared_skills` adapter (`shared_skills/<id>/`, on by default, not force-enabled; rules/prompts are no-ops) and the shared `SkillWriter` (`adapters/_skill_writer.py`) — the single source of truth for a native skill directory, byte-identical across roots, path-safe, with the sentinel marking a skill dir as engine-owned. (v0.15 shipped a per-directory `SkillWriter` cleanup; **since v0.16** there is none — stale skill output is settled only by the §4.2 step 9 lockfile leftover policy.)
- **Sections 10.3 / 10.6 / 10.6.4**: `claude_code` and `opencode` delegate `write_skill` to the `SkillWriter`; OpenCode now writes `.opencode/skills/` natively instead of relying on `.claude/skills/` (duplicate discovery is safe: OpenCode keys skills by name, last wins).
- **Section 6.3 (bug fixes)**: emitted `SKILL.md` sets `name` = the skill id (= directory name), as the Agent Skills standard requires — previously the authored display name was copied verbatim and OpenCode dropped the skill. `SKILL.md` now carries the sentinel as its first body line, so a skill directory is recognisably engine-owned (previously skill output was never cleaned); user-authored skill dirs (no sentinel) are never touched. Since v0.16 a deleted skill's output is settled only by the §4.2 step 9 lockfile leftover policy: pristine, untracked, lockfile-listed files are deleted; edited and user-added files are kept.
- **Section 12.6 (`playbook validate`)**: new rule flagging skill ids that break `^[a-z0-9]+(-[a-z0-9]+)*$` / 64 chars, skills without a 1–1024 char `description`, and every skill with no (or a non-string) `id` — id-less skills all merge under `skill`, so they are checked from the pre-merge list.
- **Section 10.8 (cleanup safety)**: ownership is decided before writing (a colliding hand-written skill dir is skipped with a warning, never overwritten; pre-v0.15 output is re-claimed via the lockfile); stale-vs-written decisions compare file identity, not path spelling (the identity comparison now lives in `_file_identity.FileSet`, used by the leftover policy and `Adapter._default_cleanup`); case-only id renames, file↔folder flips in `scripts/`/`references/`, and read-only copies from an earlier sync no longer delete fresh output or crash `sync` / `sync --check`.
- **Sections 2.2 / 3 / 4 / 5.1 / 5.3 / 7.1 / 12.1**: skills are no longer described as Claude-Code-only; the consumer layout gains `.claude/skills/`, `.opencode/skills/` and `shared_skills/`; `shared_skills` joins the default adapter list.
- **Implementation**: `adapters/_skill_writer.py`, `adapters/shared_skills_adapter.py` (+ the `shared_skills` entry point), `commands/init.py` default adapters, `commands/validate.py::_check_agent_skills`, with tests (`tests/adapters/test_skill_writer.py`, `tests/adapters/test_shared_skills.py`, `tests/cli/test_sync_skills.py`).
### v0.14 (2026-07-14)
Self-contained markdown links in canonical artifacts (PR L). A deterministic, CI-enforced rule: every markdown link in every artifact must stay inside the shipped bundle. Purely additive — no rendering changes, no new dependency. Authoritative design: `specs/prL-markdown-links.md`.
- **Section 12.6 (`playbook validate`)**: new rule — links extracted from rule/prompt/skill bodies (plus skill `references/*.md`), after masking frontmatter, fenced code blocks, and inline code spans. Relative targets must resolve inside the artifact's source layer (package `resources/` or repo-local `playbook/`; `.j2`-suffixed sources satisfy their rendered names); absolute paths, `..`-escapes, and non-`http(s)` schemes are violations; `http(s)` hosts pass only via the allowlist. Jinja-bearing targets are skipped.
- **Section 7.1 (config)**: new `[links]` table — `allowed_domains` (list of hostnames, subdomains included; default `[]` = fully strict), parsed by `config.parse_links_config`.
- **CI**: the engine's own shipped artifacts are gated by `tests/cli/test_validate_links.py::test_shipped_engine_artifacts_have_self_contained_links` under the existing `pytest` step (a bare `playbook validate` step needs a consumer config, which the engine repo has none of).
- **Implementation**: `links.py` (`MarkdownLink`, `LinksConfig`, `extract_markdown_links`, `classify_link`; stdlib-only), `config.parse_links_config`, `commands/validate.py::_check_markdown_links`, with tests.
### v0.13 (2026-06-29)
Eval **task-config redesign** ("2b refined", Tracks C1–C8): the `[expected]`/`[metrics]`/`[rubric]` triple is replaced by a layered, expression-composed task config. This is a **destructive cutover** of the *authored* task format (no backward compat); the `Metric`/`Check`/`Rubric` engine (v0.12) is reused underneath. Authoritative design: `specs/pr2b-task-config.md`.
- **Sections 6.5.3 / 15.2 (task schema)**: a task now declares up to four layer blocks sharing one `[<layer>.bind]` + `[<layer>].expr` shape — `[gate]` (deterministic boolean), `[rubric]` (llm-judge weighted), `[verdict]` (boolean expr over the two), and an optional `[aggregate]` (cross-trial `pass@k`/`pass^k`). **There is no `[expected]` block** — file predicates are gate `check`s. `ExpectedOutcome`/`Rubric`(`criteria`/`weights`) dataclasses are deleted; `EvalTask` carries `gate`/`rubric`/`verdict`/`aggregate` `Layer`s.
- **0–1 normalization**: every `Metric` owns a `Normalizer` (`evaluators/normalizer.py`: `RampNormalizer`/`PercentNormalizer`/`Identity`) folding the metric's native direction into a 0–1 goodness (higher = better). `higher_is_worse` is **deleted**; `warn`/`fail`/`max_worsening` are 0–1 cutoffs on the normalized score.
- **A check is `(type) × (metric|judge) × kwargs`**: `check = "threshold"|"non_regression"` over a registered `metric=` **or** a `judge=` criterion (a `JudgeMetric` — an llm-judge criterion *is* a metric, normalized `Identity`). Non-regression works on any metric including judged.
- **Registries**: checks via `@register_check` + `coding_agent_playbook.checks`; gates via `@register_gate` + the new **`coding_agent_playbook.gates`**; rubrics via `@register_rubric` + `coding_agent_playbook.rubrics`. A handle `{ref="name"}` resolves a registered composed **gate** (gate layer) or **rubric** (rubric layer).
- **Expression DSL + derived verdict**: `[<layer>].expr` and `[verdict].trial` are tiny boolean expressions (`and`/`or`/`not`/parens) over handle names (`evals/_expr.py` → `compose.py` tree). The verdict is **derived** from the already-run gate/rubric layer results (a skipped layer is neutral), so the judge / test-suite is never double-invoked.
- **Aggregate / pass@k**: `[aggregate]` is the same bind+expr shape over `pass_at_k`/`pass_pow_k` (`k`, `over ∈ {gate,rubric,verdict}`, 0–1 `warn`/`fail`); the runner runs `N=max(k)` trials and the aggregate composes them into a reliability score. Omit ⇒ single trial.
- **Implementation**: `evaluators/{normalizer,gates,rubrics}.py`, `evaluators/checks/{registry,judge_metric,aggregate}.py`, and `evals/{_expr,_handles,_compile}.py` (the expression DSL, handle Factory+Composite, and task compiler), with the parser/validator/scoring/runner cut over and all 10 authored tasks migrated. `rubric_for_task`/`ExpectedOutcome`/`higher_is_worse` are removed. Out-of-tree migration: `MIGRATION.md`.
### v0.12 (2026-06-28)
Evaluator subsystem refactored to the `Metric`/`Check`/`Rubric` model (PR R6 — clean-slate). The fused `Evaluator` ABC + free `grade()` are replaced by three single-responsibility abstractions; a cost-tiered scheduler short-circuits so a failing deterministic check never invokes the LLM judge. The authored `[expected]`/`[metrics]`/`[rubric]` task TOML is **unchanged** — zero authoring migration; only the engine internals and the out-of-tree extension surface change.
- **Section 21 (rewritten 21.1–21.8)**: `Metric` (measure) / `Check` (grade — a boolean gate + optional partial-credit score) / `Rubric` (aggregate — gate + weighted composite). A `Rubric` is also a `Metric` (Composite — it surfaces its composite via `measure()`, so checks compose + nest). Builtins: static metrics + execution `coverage`/`test_pass_rate`; checks: `ThresholdCheck`/`NonRegressionCheck`, `FileExists`/`FileContains`/`FileUnchanged`/`FileForbidden`, `JudgeCheck`, `TestsPassCheck`/`CoverageCheck`, and the boolean composers `AllOf`/`AnyOf`/`Not`. The cost-tiered (`CostTier` DETERMINISTIC < EXECUTION < JUDGED) scheduler with short-circuit + optional concurrency (21.4). Entry-point groups renamed/split: metrics under `coding_agent_playbook.metrics` (was `…​.evaluators`), custom grader checks under the new `coding_agent_playbook.checks` (21.3). `grade()`/`value_kind`/`to_score`/`default_*`/`extra_evaluators`/`JudgedCriterion`/`evaluators_for_task`/the `Evaluator` ABC are **deleted** (21.7).
- **Sections 15.3 / 15.3.1**: the scoring bridge builds one `Rubric` via `rubric_for_task` and runs `Rubric.evaluate`; `score(...)` gains `fail_fast` (the runner default; `--full-scoring` flips it off so every check runs). The `[metrics]`/`[rubric]`/`[expected]` blocks compile into one ordered check list → one `EvaluationReport`.
- **Implementation**: `evaluators/{metric,check,rubric,scheduler,policy}.py` + `evaluators/checks/{files,judged,execution,compose}.py`; consumers `evals/scoring.py`, `evals/task.py::rubric_for_task`, `commands/metrics.py`. Authoritative design `specs/prR6-check-rubric.md`; out-of-tree migration `MIGRATION.md`.
### v0.11 (2026-06-28)
Judged `[rubric]` scoring activated, the `[expected]` family unified, and a second real runner added (PR R2 Track J + R3 Tracks E/O). The judge is live: the deterministic-only behaviour of R1 is preserved as the default (no judge configured), and passing `--judge llm` folds the rubric scores into the same report. The v1 public surface (`Evaluator`/`grade`/`evaluators_for_task` API and the `[metrics]`/`[rubric]`/`[expected]` task schema) is unchanged — only the eval result/scoring internals evolve, the sanctioned v1.1-activation revision.
- **Section 15.1 (Tier ladder)**: Tier 2 (rubric judging) marked **shipped (v1.1 R2)** — opt-in `LLMJudge` via `--judge llm`; calibration remains future work.
- **Section 15.3 (runner)**: `run_task(task, scratch, *, judge=None, samples=1)` documented as taking an optional judge threaded onto the `EvalContext` (with a judge, the `[rubric]` criteria score against the captured diff and fold into the same report; with none — the default — judged evaluators report `available() is False` and the report is deterministic-only). **`OpenCodeRunner`** (`name="opencode"`, `evals/opencode_runner.py`) added to the runners list as a second thin, opt-in real runner (default `opencode run <prompt>` with `cwd=scratch_dir`, `available()`-gated on the `opencode` binary, never in CI); `ContinueCLIRunner` is the only remaining future runner.
- **Section 15.3.1 (scoring bridge)**: the `[expected]` checks are now **real BOOL `Evaluator`s** (`evaluators/expected.py`: `FileExists`/`FileContains`/`FileUnchanged`/`FileForbidden`) compiled by `evaluators_for_task` and graded through the **same `grade(…, extra_evaluators=…)` call** as `[metrics]` and the judged `[rubric]` criteria — one model, one `EvaluationReport`. The R1 interim that compiled `[expected]` into BOOL findings outside `grade()` is removed. The `[rubric]` pass is included only when `judge is not None`; "deterministic-only" is **simply no judge configured** (`ctx.judge is None`), there is no `ProgrammaticOnlyJudge`.
- **Section 15.4**: `judge.py` documented as **live** — the `Judge` ABC's canonical per-criterion primitive `score_criterion(criterion, artifact, n=1) -> float` (Option A; batch `score()` wraps it), the opt-in `LLMJudge`, and the test-only `StubJudge`. The `JudgeLike` protocol lives in `evaluators/types.py` so `evaluators` never imports `evals`.
- **Section 12.8 (`playbook eval`)**: `playbook eval <id> --run` gains **`--judge NAME`** (default: no judge ⇒ deterministic-only) and **`--samples N`** (default 1, the per-criterion sample count the judge averages); exit `2` now also covers an unknown/unavailable `--judge`.
- **Section 21.2.3 / 21.8**: the forward-compat `Judge.score` signature debt is **closed** — `JudgedCriterion` calls `score_criterion` through the structural `JudgeLike` protocol.
- **`pyproject.toml`**: the `coding_agent_playbook.runners` group gains `opencode`; the `coding_agent_playbook.judges` group is populated with `llm`.
- **Implementation**: `evals/judge.py` (`Judge` ABC + `LLMJudge` + `StubJudge`), `evaluators/expected.py` (the four BOOL evaluators), `evaluators/types.py` (`JudgeLike` protocol + `EvalContext.judge`/`tree`/`baseline_tree`), `evals/opencode_runner.py`, and the unified `evaluators_for_task`/`evals/scoring.py`/`commands/eval.py` wiring, with tests. See `specs/prR2-judge-r3-opencode.md` and the roadmap `specs/v1.1-eval-execution.md`.

### v0.10 (2026-06-28)
Eval runner activated (PR R1). The former v2 placeholder is now a live, hermetic-by-default runner that executes one task end-to-end and scores it through the unified PR-M `Evaluator`/`grade()` model. The deterministic layers (`[expected]` file checks + `[metrics]` static/execution non-regression) are computable today; judged `[rubric]` scoring stays deferred to R2. The v1 public surface (the `Evaluator`/`grade`/`evaluators_for_task` API and the `[metrics]`/`[rubric]`/`[expected]` task schema) is unchanged — only the eval *result* types evolve, which is the sanctioned v2-activation revision.
- **Section 15 (rewritten 15.1 / 15.3 / 15.4)**: the Tier ladder now marks Tier 1's deterministic layers **shipped (v1.1 R1)**. `HarnessRunner` documented as a concrete **template method** (`run_task` = materialize → `render_prompt` → `_invoke_agent` → `capture` → `score`; `_invoke_agent` the only per-assistant hook) with `render_prompt` strictness (`requires_resolved_prompt` ⇒ `PromptResolutionError` for real runners). Result model evolved to **Option B** — `TaskResult.report: EvaluationReport` (+ `passed`/`aggregate_score`/`duration_seconds`/`transcript`); `programmatic_checks`/`rubric_scores`/`CheckResult` retired; `EvalReport.pass_rate` = mean of `tr.passed`. Concrete runners: hermetic `FakeRunner` (`name="fake"`, default test driver, no-op default mutation) + opt-in `ClaudeCodeRunner` (`name="claude_code"`, lazy, `available()`-gated on the `claude` CLI, never in CI), via the `coding_agent_playbook.runners` group. New 15.3.1 documents the `evals/scoring.py` bridge ([metrics] via `evaluators_for_task` + non-regression vs the pristine `setup/` snapshot; `[expected]` compiled to BOOL findings — the R1 interim, full compile is R3).
- **Section 12.8 (`playbook eval`)**: documents `playbook eval <id> --run [--runner fake|claude_code] [--format text|json]` — default runner `claude_code`, **no `--run-tests`** (execution intent lives in the task's `[metrics]` block), exit `0` pass / `1` fail / `2` usage or runner-unavailable. The bare `playbook eval <id>` (no `--run`) deferral path is unchanged.
- **`pyproject.toml`**: the `coding_agent_playbook.runners` entry-point group is now populated (`fake`, `claude_code`); the `coding_agent_playbook.judges` group stays reserved for the R2 judge.
- **Implementation**: `evals/runner.py` (template + result types + orchestration helpers `materialize`/`render_prompt`/`capture` + `PromptResolutionError`), `evals/scoring.py`, `evals/fake_runner.py`, `evals/claude_code_runner.py`, and the `--run` path in `commands/eval.py`, with tests. See `specs/prR-eval-runner.md` (tracks R1a–R1e) and the roadmap `specs/v1.1-eval-execution.md`.

### v0.9 (2026-06-27)
Code-quality evaluator subsystem added (PR M). A single `Evaluator` abstraction unifies static metrics, execution metrics, and judged criteria; a standalone `playbook metrics` gate + static pre-commit hook ship now; eval `[metrics]` wiring is parsed/validated but dormant until v1.1. Purely additive — no new hard dependency, no edits to the sync pipeline, and the v2 eval ABCs (§15) stay inert.
- **Section 21 (NEW)**: the evaluator subsystem. The `Evaluator` ABC + `Scope`/`ValueKind`/`Determinism` axes (21.1); the three families — static (CC/WMC/LCOM4/DIT/CBO≈ via `ast`, MI via the optional `radon` extra), execution (`test_pass_rate`/`coverage`, shelling out to the target's `pytest` and parsing junit/coverage XML with stdlib), and judged (`JudgedCriterion`, dormant) — with per-evaluator default tables (21.2); the `@register_evaluator` decorator + `coding_agent_playbook.evaluators` entry-point group + `static/deterministic_evaluators()` selection (21.3); `grade()` gate + weighted composite with the inclusive/strict gate-boundary semantics and the non-regression comparator (21.4); the `playbook metrics` command, flags, exit codes, `[metrics]` config, and the `repo: local` static pre-commit hook (21.5); the eval `[metrics]` block (sibling of `[rubric]`), `EvalTask.metrics`, `evaluators_for_task`, and validator rule 7 (21.6); invariants (21.7) and open caveats incl. the forward-compat `Judge.score` signature mismatch (21.2.3 / 21.8).
- **Section 15 (eval)**: the eval-task schema gains a top-level `[metrics]` block parsed into `EvalTask.metrics`; validated in v1, executed by the v1.1 runner via `evaluators_for_task` against the same registry + `grade()`. The `[expected]` → bool-evaluator compilation is deferred.
- **`pyproject.toml`**: new `[project.optional-dependencies] metrics = ["radon>=6.0"]` extra (backs `maintainability_index` only; lazy-imported) and the `coding_agent_playbook.evaluators` entry-point group (empty in-tree; for third-party evaluators).
- **Implementation**: `evaluators/` package (`registry`, `types`, `scope`, `parse`, `grade`, `judged`, `builtins/*`, `execution/*`) + `commands/metrics.py` + `config.parse_metrics_config` + the `playbook-metrics` hook in `.pre-commit-hooks.yaml`, with tests. See `specs/prM-code-metrics.md` (tracks M1–M6).

### v0.8 (2026-06-26)
Agent Harness round-trip support added (the [agentharnesses.io](https://agentharnesses.io/specification) format) as a fifth, opt-in output target plus a reverse importer and a structural validator. Authoring and the existing four adapters are unchanged; the new surface is purely additive (no edits to `types.py`, `renderer.py`, or `orchestrator.py`).
- **Section 10.7 (NEW)**: the `agent_harness` output adapter. Renders canonical `Rule`/`Prompt`/`Skill` into a `HARNESS.md`-rooted tree (`skills/`, `prompts/`, `rules/`, `references/`, `.leaf-detectors`, `.playbook/`). Opt-in via `adapters_enabled`. Eval tasks are not emitted (no eval hook on the adapter ABC). Documents the sentinel-as-first-body-line nuance (frontmatter must be line 1) and the custom `cleanup_stale`.
- **Sections 12.9 / 12.10 (NEW)**: `playbook import-harness <path> [--into]` (harness → canonical, lossless via the sidecar / best-effort otherwise) and `playbook validate-harness <path> [--strict]` (`harnesses-ref`-equivalent structural checks).
- **Sections 20.10 / 20.11 (NEW)**: the `.playbook/manifest.toml` sidecar — full canonical reconstruction payload (rule `name`, un-rendered source body, `is_templated`, per-script `executable` flag) enabling lossless round-trip; and a future-work note that the harness client runtime (`load_content`/`run_script`) is intentionally out of scope.
- **Implementation**: `harness/` core module (`models`, `leaf_detectors`, `parser`, `emitter`, `manifest`) + the adapter, two CLI commands, and tests. See `specs/prH-agent-harness.md`.

### v0.7 (2026-05-20)
Canonical types formalized. Authoring stays markdown; internal pipeline becomes typed end-to-end; alternative deployments (commercial, hosted) get a stable interchange format.
- **Section 5.1 (engine layout)**: Added `types.py` at the package root containing the `Rule`, `Prompt`, `Skill` dataclasses. Added `test_types.py` to unit tests.
- **Section 6.6 (NEW)**: Canonical types and serialization. Explicitly separates the *authoring format* (markdown + YAML frontmatter, what humans write) from the *canonical internal format* (typed dataclasses, what the engine operates on). Defines `RuleFrontmatter` / `Rule` / `PromptFrontmatter` / `Prompt` / `Skill` with full field lists. Specifies the lossless round-trip contract (`Rule.from_markdown` ↔ `Rule.to_markdown`, `Rule.to_dict` ↔ `Rule.from_dict`). Documents what is deliberately absent from the canonical type (no harness-specific rendering, no source-specific data, no render context). Includes a "contract for alternative deployments" subsection that protects compatibility between the OSS engine and a future commercial product.
- **Implementation order**: Added Track 1b (PR 2) for the canonical types with markdown round-trip. Lands second because almost every subsequent module imports from `types.py`. Total LoC bumped to ~3900.
### v0.6 (2026-05-20)
Storage abstraction added. Engine still ships filesystem-only in v1; the seam exists so future deployments can swap in alternative artifact/state backends without modifying engine code.
- **Section 4.2 (data flow)**: Steps 1 and 3 now reference `StateSource` and `ArtifactSource` instead of hardcoded filesystem walks. Behavior unchanged in v1; framing reflects the abstraction.
- **Section 5.1 (engine layout)**: Added `sources/` package with `base.py` (ABCs) and `filesystem.py` (v1 implementations). Added `test_sources.py` to unit tests.
- **Section 7.1 (config example)**: Added `[storage]` block with `artifact_source = "filesystem"` and `state_source = "filesystem"` defaults. Configs without this block default to filesystem, so existing configs need no changes.
- **Section 20 (NEW)**: Storage sources. Defines `ArtifactSource` and `StateSource` ABCs as public API from v1. Lists the v1 filesystem implementations as the only concrete sources shipped. Documents entry-point discovery, the `[storage]` config block, and what the seam enables later (registry sources, database state, in-memory test sources) — none of which ship in v1. Includes an explicit "what v1 promises and does not promise" subsection.
- **Implementation order**: Added Track 2c (PR 4) for the filesystem source implementations. Track 1 (PR 1) now also adds the source ABCs alongside the adapter ABC. Total LoC bumped to ~3650.
### v0.5 (2026-05-20)
Eval Tier 0 added: prompts can declare eval tasks, tasks are validated, but no runner ships in v1.
- **Section 2.1 (G6)**: Rewrote eval goal to be specific about Tier 0 — schema + validator + read-only CLI, no runner.
- **Section 2.2 / 2.3**: Non-goals now distinguish "no eval runner" (Tier 1) from "no LLM-as-judge" (Tier 2). v2 aspirations split the eval work into two milestones.
- **Section 3 (glossary)**: Added "Eval task" entry.
- **Section 4.2 (data flow)**: Added explicit note that eval tasks are authoring-side artifacts and not part of `playbook sync`.
- **Section 5.1 (engine layout)**: Added `resources/eval_tasks/` tree with three example tasks. Updated `evals/` package to split active modules (`task.py`, `loader.py`, `validator.py`) from v2 placeholders (`runner.py`, `judge.py`). Added `test_eval_tasks.py` to unit tests.
- **Section 6.2.1 (prompt frontmatter)**: Added optional `eval_tasks:` field.
- **Section 6.5 (NEW)**: Eval tasks — Tier 0 design. Directory layout, `task.toml` schema (setup / invocation / expected / rubric), authoring discipline, validation rules, Tier 0/1/2 capability table.
- **Section 12.6 (`playbook validate`)**: Added two new validation rules — `eval_tasks:` references resolve, and task `prompt_id` back-references are consistent.
- **Section 12.8 (NEW)**: `playbook eval --list` enumerates the prompt-to-task graph; `playbook eval --show <task>` displays a single task; `playbook eval <task>` prints a deferred-implementation message (exit 0).
- **Section 15**: Complete rewrite. Now structured as Tier 0 (v1, active) / Tier 1 (v1.1) / Tier 2 (v2). Active dataclasses (`EvalTask`, `TaskSetup`, `TaskInvocation`, `ExpectedOutcome`, `Rubric`) replace the old `GoldenTask`. Added `HarnessRunner` and `Judge` ABCs as v2 placeholders. Added concrete examples of v2 runners (`ClaudeCodeRunner`, `ContinueCLIRunner`, `OpenCodeRunner`).
- **Section 19**: Added open questions Q10 (HarnessRunner invocation contract), Q11 (determinism / seeding), Q12 (rubric calibration).
- **Implementation order**: Added PR 9 (Track 5b, Eval Tier 0, ~250 LoC). PR 11 (initial content pack) now also ships 8 eval tasks alongside the rules and prompts. Total LoC and timeline bumped slightly.
### v0.4 (2026-05-20)
Consistency audit — no new design decisions, only reconciliation of drift introduced by previous additions.
- **Section 4.1 (component diagram)**: Added `opencode` adapter and `.opencode/command/*.md` to the consumer repo. Resources block now shows `*.md|*.md.j2` (consistent with Section 6.0) instead of uniform `*.md.j2`.
- **Section 6.1.1 (rule frontmatter)**: Removed unused `invokable` scope value (rules have `always | scoped`; only prompts are invokable, via their own frontmatter).
- **Section 6.2.1 (prompt frontmatter)**: `slash:` comment now mentions OpenCode alongside Continue & Claude Code.
- **Section 6.4 (applies_if)**: Added explanatory note disambiguating `has_framework` as both an `applies_if` predicate key (list-of-strings) and a Jinja context callable (single-string). Same conceptual question, different evaluation layers.
- **Section 7.1 (config example)**: `[adapters] enabled` now includes `"opencode"`.
- **Section 9.7 (format table)**: Added `prompt_opencode_command` row. Documented the CLI's short-alias mapping (`--format continue` → `continue_rule`, etc.).
- **Section 10.1 (Adapter ABC)**: Reconciled with concrete implementations. `finalize()` is now declared as a default no-op lifecycle hook (used by ClaudeCodeAdapter). `cleanup_stale()` is no longer `@abstractmethod` and ships with a default implementation that all built-in adapters can rely on. `write_skill()` docstring clarifies the OpenCode case (returns [] because Claude Code adapter already writes to a path OpenCode reads).
- **Section 11.1 (overlay layers)**: Resolved a three-way contradiction. The repo-local override directory is `<repo>/playbook/` (containing `rules/`, `prompts/`), not `<repo>/playbook/resources/`. Section 4.2 and Section 5.3 were already consistent with this; Section 11.1 was the outlier and is now fixed.
- **Section 12.1 (playbook init)**: "Next steps" now mentions `.opencode/`.
- **Section 12.2 (playbook sync)**: Output includes a line for opencode adapter writes (5 files). Total adjusted to 23.
- **Section 12.7 (playbook render)**: `--show-source` output explains why opencode isn't listed for rules ("reads rules via AGENTS.md natively — no direct render").
- **Appendix A.4 (worked example)**: Result tree includes `.opencode/command/` with the five prompts.
- **Appendix A.6 (update step)**: playbook sync output includes opencode adapter line; summary count updated to 3.
### v0.3 (2026-05-20)
OpenCode support added as a third primary adapter alongside Continue and Claude Code.
- **Section 2.1 (G1)**: Updated primary adapter list to include OpenCode.
- **Section 2.2 (non-goals)**: Expanded with OpenCode-specific exclusions — no agents, no plugins, no `opencode.json` management in v1. Codex moved from "no dedicated adapter" to "AGENTS.md is sufficient".
- **Section 2.3 (v2 aspirations)**: Added OpenCode plugin generation and OpenCode agents as a fifth canonical artifact category.
- **Section 3 (glossary)**: Added entries for OpenCode plugin and OpenCode agent. Updated rule/prompt/skill entries to mention OpenCode's discovery paths.
- **Section 4.2 (data flow)**: Step 6 now lists four adapters including `opencode`.
- **Section 5.1 (engine layout)**: Added `opencode_adapter.py` and `test_opencode.py`.
- **Section 5.3 (consumer repo layout)**: Added `.opencode/command/` block, with explicit notes on why no `.opencode/rules/` or `.opencode/skills/` is generated.
- **Section 6.1 (rules)**: Added note that OpenCode receives rules via the AGENTS.md adapter.
- **Section 10.6 (NEW)**: OpenCode adapter design — prompt-to-command translation, hook gap, agents gap, explicit boundaries on what the adapter does not touch.
- **Section 12.1 (`playbook init`)**: OpenCode added to the assistant multi-select.
- **Section 19**: Added open questions Q8 (OpenCode plugin generation) and Q9 (OpenCode agents as a first-class artifact).
- **Implementation order recap**: Added PR 7 (Track 4c, OpenCode adapter, ~150 LoC); subsequent PRs renumbered.
### v0.2 (2026-05-20)
- **Section 6.0**: Added explicit `.md` vs `.md.j2` distinction. Plain markdown is the default; Jinja is opt-in via `.j2` suffix.
- **Section 6.2**: Added rule inclusion in prompts. New `includes_rules:` frontmatter field, `{{ rule("id") }}` Jinja helper, and implicit-appendix mode for plain-markdown prompts. Full design in new Section 6.2.5.
- **Section 9**: Renderer subsystem updated with extension dispatch (9.2) and the `rule()` Jinja helper (9.5). Format post-processing in 9.7 documents the auto-appendix behavior for prompts.
- **Section 12.6 (`playbook validate`)**: New validation rules for `includes_rules:` consistency and the "rules cannot include rules" constraint.
- **Section 12.7 (`playbook render`)**: New `--show-rules` flag to display resolved rule inclusions for a prompt.
- **Section 19**: Added open questions on glob/tag-based rule inclusion (Q6) and cross-prompt rule sharing (Q7).
- **Sections 5.1, 5.2**: Tree examples updated to mix `.md` and `.md.j2` realistically rather than uniformly using `.md.j2`.
- **Appendix A.5**: Worked example updated to show how `includes_rules:` makes slash commands reliable across contexts.
### v0.1 (2026-05-20)
- Initial draft.
