# SPEC.md — coding-agent-playbook
| Field | Value |
| --- | --- |
| Version | 0.12 (draft) |
| Status | Proposed |
| Last updated | 2026-06-28 |
| Authors | Max Pereira, with Claude |
| Audience | Implementers, reviewers, future contributors |
| License | Apache-2.0 (engine); organization overlays may be private |

**Changelog**
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
**G4 — Pre-commit-native distribution.** Installation produces a pre-commit-managed sync hook. Drift between the canonical source and what is checked into the repo fails CI.
**G5 — Air-gapped friendly.** No required network calls at sync time. Internal PyPI distribution. No HTTP-based hooks shipped by default. No telemetry.
**G6 — Eval task authoring (Tier 0).** v1 ships the schema, loader, validator, and read-only CLI for prompt-associated eval tasks (Section 6.5). The runner, programmatic checks, and LLM-as-judge are deferred to v1.1 (Tier 1) and v2 (Tier 2) respectively. Authors write tasks alongside prompts from day one; the corpus accumulates as documentation and is ready when the runner lands.
### 2.2 v1 non-goals (named so people stop asking)
- Skills are not first-class for non-Claude-Code harnesses; they degrade to prompts. (Exception: OpenCode reads `.claude/skills/` natively, so skills work there without a separate adapter path.)
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
- **Skill** — a Claude Code-specific richer prompt with bundled scripts and progressive disclosure. Degrades to a prompt for harnesses that lack the concept. OpenCode reads `.claude/skills/<name>/SKILL.md` natively, so skills authored for Claude Code work in OpenCode without duplication.
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
              │   - banking-security rules   │         │  Generated files:            │
              │   - PII redaction prompts    │         │   .continue/rules/*.md       │
              │   - LiteLLM-aware config     │         │   .continue/prompts/*.md     │
              │                              │         │   .claude/CLAUDE.md          │
              └──────────────┬───────────────┘         │   .claude/commands/*.md      │
                             │                         │   .opencode/command/*.md     │
                             │                         │   AGENTS.md                  │
                             └─────── merges ─────────►│   .pre-commit-config.yaml    │
                                                       │                              │
                                                       │  Personal overrides:         │
                                                       │   .coding-agent-playbook.    │
                                                       │       local.toml (gitignored)│
                                                       └──────────────────────────────┘
```
### 4.2 Data flow
The end-to-end flow of `playbook sync` in a consumer repo:
1. **Load configuration.** Read `.coding-agent-playbook.toml` (committed), merge `.coding-agent-playbook.local.toml` (gitignored, personal overrides) on top. The read goes through the configured `StateSource` (filesystem in v1; see Section 20).
2. **Run detector.** Inspect `pyproject.toml`, lockfiles, filesystem. Produce a facts dictionary.
3. **Resolve overlays.** Query the configured `ArtifactSource` (filesystem in v1; see Section 20) for rules, prompts, skills, and eval tasks across the engine package, each declared overlay package, and the consumer's `playbook/` directory. Build a unified artifact list, with later layers overriding earlier ones by ID.
4. **Filter.** For each artifact, evaluate its `applies_if` predicate against the facts dictionary. Drop non-matching artifacts.
5. **Render.** Apply Jinja2 to each surviving artifact's template with `facts | config` as context.
6. **Dispatch to adapters.** For each enabled adapter (`continue`, `claude_code`, `opencode`, `agents_md`), pass the rendered artifacts; the adapter writes to its harness-specific locations.
7. **Write `AGENTS.md`** as the universal fallback regardless of which adapters are enabled.
8. **Stamp.** Write a `.coding-agent-playbook.lock` file containing the rendered file hashes via the configured `StateSource`; used by `playbook sync --check` to detect drift.
Eval tasks (Section 6.5) are intentionally **not** part of the sync flow. They live in engine and overlay packages, are read at validation time (`playbook validate`) and enumeration time (`playbook eval --list`), and v2 will read them at runner time — but they never produce files in the consumer repo. They are authoring-side artifacts, not deliverables.
### 4.3 Key design choices, recapped
- **Copies, not symlinks.** Cross-platform, banking-friendly, git-friendly.
- **Jinja sparingly.** Variable substitution and conditional file selection only. Avoid `{% if %}` inside rule bodies — makes templates unreadable.
- **Sentinel headers.** Every generated file begins with `# AUTOGENERATED — edit in coding-agent-playbook, run 'playbook sync'`.
- **Detector facts are cached.** Written into `.coding-agent-playbook.toml` at init. Refreshed automatically when `pyproject.toml` mtime changes, or manually via `playbook check --refresh`.
- **`AGENTS.md` is always generated.** Even if no adapters are enabled. It is the lowest-common-denominator output and costs nothing.
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
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py                         # Adapter ABC
│   │   ├── continue_adapter.py
│   │   ├── claude_code_adapter.py
│   │   ├── opencode_adapter.py
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
│       │   └── (empty in v1; Claude Code only)
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
├── .coding-agent-playbook.toml             # committed
├── .coding-agent-playbook.local.toml       # gitignored
├── .coding-agent-playbook.lock             # committed; drift detection
├── .pre-commit-config.yaml                 # committed; references engine
├── .gitignore                              # init appends .local.toml
├── AGENTS.md                               # AUTOGENERATED
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
│   └── commands/
│       ├── refactor.md
│       ├── generate-tests.md
│       ├── review.md
│       └── explain.md
├── .opencode/
│   └── command/                            # AUTOGENERATED — OpenCode slash commands
│       ├── refactor.md
│       ├── generate-tests.md
│       ├── review.md
│       └── explain.md
└── playbook/                               # OPTIONAL: per-repo customizations
    └── rules/
        └── risk-models-specific.md.j2
```
Everything marked AUTOGENERATED has a sentinel header and is owned by `playbook sync`. The user owns `.coding-agent-playbook.toml`, `.coding-agent-playbook.local.toml`, anything under `playbook/`, and their own source code.
Note two deliberate non-duplications for OpenCode:
- **No `.opencode/rules/` directory.** OpenCode reads `AGENTS.md` natively as its primary rules source, walking up the directory tree. The universal AGENTS.md adapter is OpenCode's rule-delivery path. Writing a separate `.opencode/rules/` would just duplicate content OpenCode is already reading from `AGENTS.md`.
- **No `.opencode/skills/` directory.** OpenCode reads `.claude/skills/<name>/SKILL.md` natively as a fallback. Skills written by the Claude Code adapter are automatically picked up by OpenCode without copying.
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
def parse_response(payload: Dict) -> Optional["Response"]:
    ...
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
### 6.3 Skills (Claude Code only in v1)
Skills are Claude Code-specific. The engine ships none in v1; the abstraction exists so v2 can add them without breaking the artifact model. Overlay packages may ship skills already in v1 if they want Claude Code-only richer prompts; they degrade gracefully.
#### 6.3.1 Schema
A skill is a directory:
```
skill-name/
├── SKILL.md.j2                      # the prompt body, with frontmatter
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
    │   ├── task.toml                 # task metadata + expected outcomes
    │   ├── setup/                    # files written to scratch repo before invocation
    │   │   └── src/calculator.py
    │   └── expected/                 # optional: golden files or fragments
    │       └── tests/test_calculator.py.contains
    ├── generate-tests-edge-cases/
    │   └── ...
    └── refactor-extract-helper/
        └── ...
```
Each task is a directory, not a single file, because tasks need fixture files (the `setup/` tree) and optionally expected output fragments. Mirrors the skills pattern (Section 6.3).
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
[expected]
# Files the agent must create (relative to repo root).
files_created = ["tests/test_calculator.py"]
# Regex patterns that must appear in created or modified files.
# Each entry: { path = "...", pattern = "..." }.
files_must_contain = [
  { path = "tests/test_calculator.py", pattern = "def test_add" },
  { path = "tests/test_calculator.py", pattern = "parametrize" },
]
# Files that must NOT be modified by the agent.
files_unchanged = ["src/calculator.py"]
# Files that, if created, are a failure (regression guards).
files_forbidden = ["__pycache__/", "tests/conftest.py"]
[rubric]
# Human-readable criteria, for v1 manual grading and v2 LLM-as-judge.
# Each criterion is one sentence describing a quality dimension.
criteria = [
  "Tests use pytest.parametrize for table-driven cases",
  "Test file lives at tests/test_calculator.py (mirror layout)",
  "All public branches of `add` are covered",
  "No mocking is used (function is pure)",
]
# Optional weights per criterion (must sum to 1.0). Default: uniform.
weights = [0.2, 0.2, 0.4, 0.2]
```
Field-by-field:
| Field | Required | Purpose |
| --- | --- | --- |
| `id` | yes | Unique across all overlays. |
| `prompt_id` | yes | Back-reference to the prompt this task tests. Must appear in that prompt's `eval_tasks:` list. |
| `description` | yes | One-sentence summary, shown in `playbook eval --list`. |
| `version` | no | Bump on breaking changes to setup/expected. |
| `[setup]` | yes | Mock facts and `setup/` directory listing. |
| `[invocation]` | yes | What the user "types" — prompt arguments and variable bindings. |
| `[expected]` | no | Programmatic checks. Multiple keys, all ANDed. |
| `[rubric]` | no | Text-based criteria for human or LLM-as-judge grading. |
A task is valid in v1 even with no `[expected]` and no `[rubric]` — it documents the test case without committing to how success is measured. The validator only enforces structural correctness.
#### 6.5.4 Authoring discipline
Recommended (not enforced, since this is conventions over rules):
- **Three tasks per prompt minimum.** One happy-path, one edge-case, one regression target. Adding a fourth means the prompt is genuinely complex; if you can't find a fourth, the prompt is probably fine.
- **Task IDs follow `<prompt-id>-<scenario>`.** Predictable, sortable, makes `playbook eval --list` readable.
- **Programmatic checks are cheap, rubric criteria are precious.** Every regex or file check is free to run forever. Rubric criteria are slow (humans in v1, LLM tokens in v2), so reserve them for things that genuinely can't be checked programmatically. *"Tests use parametrize"* → programmatic. *"Tests cover all public branches"* → rubric.
- **Don't test the model; test the prompt.** If a task fails because Claude 4.6 is dumber than Claude 4.7, that's not your prompt regressing. Tasks should target things the prompt itself controls: layout, conventions, what gets imported, what doesn't.
#### 6.5.5 `eval_tasks:` validation in `playbook validate`
Two new validation rules ship in v1:
1. **Every `eval_tasks:` reference resolves to a real task.** If a prompt declares `eval_tasks: [foo, bar]` but `eval_tasks/bar/` doesn't exist, error.
2. **Every task's `prompt_id` points back to a prompt that lists it.** Bi-directional check, same shape as `includes_rules` / `{{ rule() }}` symmetry. Catches orphan tasks where someone deleted the prompt but left the task behind, or where a task was renamed and a prompt's frontmatter wasn't updated.
There is no v1 check that `[expected]` programmatic patterns actually work — that requires running the agent, which is v2.
#### 6.5.6 What runs in v1 vs v2
| Capability | v1 | v2 |
| --- | --- | --- |
| Author `eval_tasks/` directories | yes | yes |
| `task.toml` schema + validation | yes | yes |
| `playbook validate` cross-reference checks | yes | yes |
| `playbook eval --list` (read-only enumeration) | yes | yes |
| `playbook eval` actually runs the agent | **no — stub prints message** | yes |
| Programmatic checks against agent output | no | yes |
| LLM-as-judge for rubric | no | yes (Tier 2) |
| Per-harness eval (`--harness claude_code`) | no | yes |
This is what makes Tier 0 cheap: most of the surface ships as schema + validator + read-only CLI, with the actual execution deferred. Section 15 carries the matching execution abstractions (`HarnessRunner`, `EvaluationReport`, and the `Metric`/`Check`/`Rubric` scoring model of §21), live since v1.1.
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
    body: str                          # post-Jinja markdown body
    template_body: str                 # pre-Jinja source, if needed for re-render
    is_templated: bool                 # True if source was .md.j2
    source_path: Path | None           # filesystem origin; None for non-filesystem sources
    source_package: str                # e.g. "coding_agent_playbook", "playbook_rules_bnp"
    @classmethod
    def from_markdown(cls, path: Path, context: dict, source_package: str) -> "Rule": ...
    def to_markdown(self) -> str: ...
    def to_dict(self) -> dict: ...     # JSON-serializable
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
    # Claude Code-only artifact, see Section 6.3
    frontmatter: dict                  # Claude's SKILL.md frontmatter shape
    body: str
    scripts_dir: Path | None           # if the skill bundles scripts
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
[project]
name = "risk-models"
kind = "python-application"          # or "python-library", "ml-research", "notebook"
description = "Counterparty risk scoring service"
[engine]
version = "0.4.0"                    # engine version this config was generated against
[overlays]
# Ordered list of overlay packages to merge in.
# Earlier overlays are overridden by later ones on ID collision.
enabled = ["playbook_rules_bnp"]
[adapters]
# Which adapters render output. AGENTS.md is always generated.
enabled = ["continue", "claude_code", "opencode"]
[storage]
# Where artifacts and state come from / go to. See Section 20.
# v1 ships only "filesystem"; future deployments can add others.
artifact_source = "filesystem"
state_source = "filesystem"
[detector.cache]
# Cached detector output. Refreshed on pyproject.toml change or `playbook check --refresh`.
python_version = "3.12"
package_manager = "uv"
has_notebooks = false
has_dockerfile = true
[detector.cache.frameworks]
fastapi = "0.115.0"
pydantic = "2.9.2"
sqlalchemy = "2.0.35"
pytest = "8.3.3"
[user_choices]
# Answered during `playbook init`.
docstring_style = "numpy"            # numpy | google | none
test_layout = "tests-mirror"         # tests-mirror | tests-flat | inline
```
### 7.2 `.coding-agent-playbook.local.toml` (gitignored)
Personal, per-engineer overrides. Merged on top of the committed config but never checked in. `playbook init` appends it to `.gitignore`.
```toml
# .coding-agent-playbook.local.toml — DO NOT COMMIT
[user_choices]
docstring_style = "google"           # overrides project default for me
[adapters]
# I only use Claude Code, skip Continue rendering for my checkout
enabled = ["claude_code"]
```
Merge semantics: deep merge, with `.local.toml` winning. The committed config always remains the team's source of truth; local just lets individuals deviate without polluting the repo.
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
    loader=FileSystemLoader([...]),        # engine resources + overlay resources
    autoescape=False,                      # markdown, not HTML
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,             # fail loudly on undefined vars
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
    name: str                                # e.g. "continue"
    @abstractmethod
    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        """Write a rendered rule to the harness-specific location(s).
        Return the paths actually written. Adapters that route rules
        through another adapter (e.g. OpenCode → AGENTS.md) return []."""
    @abstractmethod
    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        """Write a rendered prompt."""
    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Default: degrade to prompt. Subclasses override if native skill support
        (or if a sibling adapter already covers the harness — e.g. OpenCode reads
        .claude/skills/ natively, so its adapter overrides this to return [])."""
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
        under sentinel headers that are not in written_paths. Subclasses override
        only if they need custom cleanup semantics."""
        return self._default_cleanup(written_paths, repo_root)
```
Adapters return the paths they wrote. The CLI uses these for the lockfile and for `cleanup_stale`. Of the four built-in adapters, only ClaudeCodeAdapter overrides `finalize()` (to compose CLAUDE.md); the rest write immediately in `write_rule` / `write_prompt`.
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
    def finalize(self, repo_root: Path) -> list[Path]:
        target = repo_root / ".claude" / "CLAUDE.md"
        body = self._compose_claude_md(self._buffered_rules)
        target.write_text(body, encoding="utf-8")
        return [target]
```
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
agents_md = "coding_agent_playbook.adapters.agents_md_adapter:AgentsMdAdapter"
```
### 10.6 OpenCode adapter
OpenCode is structurally close to Claude Code but with one architectural twist: rules are not in a dedicated directory. OpenCode reads `AGENTS.md` at the repo root as its primary rules source, walking up the directory tree, with `CLAUDE.md` accepted as a fallback. This means the AGENTS.md adapter already delivers rules to OpenCode — the OpenCode adapter's job is limited to prompts.
Skills are also covered without duplication: OpenCode reads `.claude/skills/<name>/SKILL.md` natively as a fallback, so the Claude Code adapter's skill output is automatically picked up by OpenCode. The OpenCode adapter does not write skills.
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
        # OpenCode reads .claude/skills/ natively as a fallback. The
        # ClaudeCodeAdapter already writes there — no duplication needed.
        return []
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
To make the boundaries explicit, the OpenCode adapter writes only `.opencode/command/`. It does **not** write or modify:
- **`.opencode/agent/`** — out of scope; users own custom agents.
- **`.opencode/plugin/`** — out of scope (hook equivalent); users own plugins.
- **`opencode.json`** — out of scope; users own MCP server config, permissions, model selection, and the `instructions` array.
- **`AGENTS.md`** — owned by the AGENTS.md adapter; OpenCode reads it natively.
- **`.claude/skills/`** — owned by the Claude Code adapter; OpenCode reads it natively as a fallback.
This deliberate minimalism keeps the OpenCode adapter to ~150 lines and avoids stepping on user-owned config.
### 10.7 Agent Harness adapter
The `agent_harness` adapter renders canonical artifacts into a [Agent Harness](https://agentharnesses.io/specification) tree — a `HARNESS.md`-rooted format consumed by harness clients. Unlike the four built-in adapters it is **opt-in**: it is not in the default adapter set and is not force-enabled like `agents_md`. Enable it by listing `agent_harness` in `[adapters] enabled`. It is discovered through the same entry-point mechanism (§10.5); the engine never constructs it directly.
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

**Eval tasks are not emitted.** The `Adapter` ABC has no eval hook — `sync` only dispatches `write_rule` / `write_prompt` / `write_skill` / `finalize` — so eval tasks are authoring-only and never reach any adapter. The `agent_harness` adapter therefore never writes an `evals/` directory, exactly like the four built-in adapters. (The importer in §12.9 can still *read* a foreign `evals/` directory.)
#### 10.7.3 Sentinel placement and cleanup
A harness parser requires frontmatter to start on line 1 (`^---`), so the playbook `SENTINEL` cannot be line 1. The adapter writes it as the **first body line** (an HTML comment, after the closing frontmatter fence) on every generated text file. Because of this, the adapter overrides `cleanup_stale` to detect the sentinel *anywhere* in a file rather than only on line 1 (the Claude Code / AGENTS.md single-file pattern). Files without a sentinel are user-authored and never deleted. Scripts and raw assets carry no sentinel; their engine ownership is tracked through the previous `.playbook/manifest.toml`, which `cleanup_stale` reads at the start of `finalize` before overwriting it.
## 11. Overlay system
### 11.1 Three layers
The artifact list is built by merging three sources in order:
1. **Engine resources** (`coding_agent_playbook/resources/`). Generic, open-source, organization-neutral.
2. **Overlay packages** (e.g. `playbook_rules_bnp/resources/`). Each enabled overlay contributes additional artifacts and can override engine artifacts by ID. Overlays are applied in the order listed in `[overlays] enabled`.
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
## 12. CLI contract
The CLI binary is `coding-agent-playbook`, with a short alias `playbook`. Both names are entry points in `pyproject.toml`:
```toml
[project.scripts]
coding-agent-playbook = "coding_agent_playbook.cli:main"
playbook = "coding_agent_playbook.cli:main"
```
### 12.1 `playbook init`
Interactive bootstrap for a fresh repo. Idempotent if re-run, but won't clobber user-edited files.
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
✓ Wrote .coding-agent-playbook.toml
✓ Wrote .coding-agent-playbook.local.toml (gitignored)
✓ Appended .coding-agent-playbook.local.toml to .gitignore
✓ Wrote .pre-commit-config.yaml (merged with existing)
✓ Installed pre-commit hooks
✓ Ran playbook sync — generated 12 files
Next steps:
  - Review generated AGENTS.md, .continue/, .claude/, .opencode/
  - Commit .coding-agent-playbook.toml, .pre-commit-config.yaml, and generated files
  - Open VS Code; Continue will pick up rules automatically
```
### 12.2 `playbook sync`
Regenerate all artifacts. The workhorse command. Run automatically by pre-commit; can also be run manually.
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
Summary: 23 files written, 0 unchanged, 0 removed
```
### 12.3 `playbook sync --check`
Verify, don't write. Used by pre-commit and CI. Exits non-zero on drift.
```
$ playbook sync --check
✗ Drift detected:
  .continue/rules/50-python-typing.md
    Generated content differs from on-disk content.
    Run 'playbook sync' to regenerate.
exit code: 1
```
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
### 12.5 `playbook check --refresh`
Re-runs the detector and writes the fresh facts back to `.coding-agent-playbook.toml`. Use after adding a dependency.
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
✗ rules/frameworks/sqlalchemy-v2.md.j2: applies_if references unknown fact 'orm_version'
✗ prompts/refactor.md.j2: body calls `{{ rule("python-style") }}` but rule not in includes_rules
✗ rules/languages/python/typing.md.j2: body calls `{{ rule(...) }}` — rules cannot include other rules
✗ eval_tasks/orphan-task/task.toml: prompt_id 'deleted-prompt' does not exist
✗ prompts/generate-tests.md.j2: declares eval_task 'foo-bar' but eval_tasks/foo-bar/ not found
exit code: 1
```
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
`playbook eval` is a read-only enumeration of the prompt-to-task graph and — with `--run` (v1.1 PR R1) — the entry point that *executes* one task end-to-end through a `HarnessRunner` and grades it (§15.3). Without `--run`, the bare `playbook eval <id>` still prints the deferral message below (exit 0).
```
$ playbook eval --list
=== Eval tasks ===
generate-tests (engine)
  ├── generate-tests-happy-path        ✓ task defined
  │   └── 4 rubric criteria, 3 programmatic checks
  ├── generate-tests-edge-cases        ✓ task defined
  │   └── 5 rubric criteria, 4 programmatic checks
  └── generate-tests-async-code        ✓ task defined
      └── 3 rubric criteria, 2 programmatic checks
refactor (engine)
  └── refactor-extract-helper          ✓ task defined
      └── 3 rubric criteria, 2 programmatic checks
review (engine)
  └── (no eval tasks declared)         ⚠ consider adding tasks
pii-scan (overlay bnp)
  └── pii-scan-detects-iban            ✓ task defined
      └── 2 rubric criteria, 1 programmatic check
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
Expected (programmatic, 3 checks):
  - File created: tests/test_calculator.py
  - tests/test_calculator.py contains: def test_add
  - tests/test_calculator.py contains: parametrize
Rubric (manual / LLM-judge, 4 criteria, weights sum=1.0):
  - 0.2: Tests use pytest.parametrize for table-driven cases
  - 0.2: Test file lives at tests/test_calculator.py (mirror layout)
  - 0.4: All public branches of `add` are covered
  - 0.2: No mocking is used (function is pure)
```
```
$ playbook eval generate-tests-happy-path
Eval runner not yet implemented (v1 ships task schema only).
The task is well-formed and ready to run when the v2 runner lands. For now:
  - Use `playbook eval --show generate-tests-happy-path` to inspect the task.
  - Use `playbook eval --list` to see all task coverage.
  - To run manually: copy setup/ to a scratch repo, invoke /generate-tests
    with the documented args, and grade against the expected/rubric.
See SPEC.md Section 15 for the v2 runner API.
exit code: 0
```
Note the exit code is 0, not 1 — the task is not broken, the runner is just absent on the bare path. This lets users wire `playbook eval` into CI today as a no-op placeholder. To actually execute a task, add `--run`:
```
$ playbook eval refactor-extract-helper --run --runner fake [--judge llm] [--samples N] [--format text|json]
```
- **`--runner NAME`** selects a runner from the `coding_agent_playbook.runners` entry-point group; the default is **`claude_code`** (the real runner). Use `--runner fake` for a hermetic, no-network demo/CI run.
- **`--judge NAME`** (v1.1 R2) selects a judge from the `coding_agent_playbook.judges` group to score the task's `[rubric]` criteria too. The shipped judge is **`llm`** (`LLMJudge`, shells out to the `claude` CLI, `available()`-gated, never in CI). **Omitting `--judge` is deterministic-only** — no `ProgrammaticOnlyJudge`, just no judge configured ⇒ judged criteria skipped. **`--samples N`** (default 1) is the per-criterion sample count the judge averages.
- The task's `[expected]` + `[metrics]` blocks are scored deterministically into one `EvaluationReport`, rendered with the same text/json renderer as `playbook metrics`. With `--judge` set, the `[rubric]` SCORE findings are folded into the same report (feeding the composite, gating on an optional min-score).
- **There is no `--run-tests` flag.** Unlike `playbook metrics`, an eval task declares its execution intent in its own `[metrics]` block (`run_tests`), so the task — not a CLI flag — decides whether the execution evaluators (`coverage`/`test_pass_rate`) run.
- **Exit codes:** `0` on a passing report (gate clean), `1` on a failing report, `2` on usage errors — unknown task id, unknown `--runner`, a runner that is unavailable in this environment (e.g. `claude_code` with no `claude` CLI on `PATH` — the error suggests `--runner fake`), an unknown or unavailable `--judge` (e.g. `llm` with no `claude` CLI), or a bad `--format`.
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
Shipped at the root of `coding-agent-playbook` so consumers can reference it:
```yaml
# .pre-commit-hooks.yaml (inside the engine repo)
- id: playbook-sync-check
  name: coding-agent-playbook sync check
  description: Verify .continue/, .claude/, AGENTS.md are in sync with the installed playbook
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
### 13.2 Template `.pre-commit-config.yaml` (written by `playbook init`)
`playbook init` renders this starter from the packaged template `resources/precommit/config.yaml.j2`. It is **air-gapped-friendly**: every hook is `repo: local` + `language: system`, so pre-commit never clones a remote hook repo (it would otherwise fetch each `repo:` URL into `~/.cache/pre-commit` on first run — impossible offline, which also satisfies the engine's "air-gapped-friendly" invariant). The tradeoff is that the consumer must have `ruff` and `mypy` installed in their environment; `language: system` runs the tools on PATH, it does not install them.
```yaml
# AUTOGENERATED starter by coding-agent-playbook `playbook init`.
# Air-gapped-friendly: all hooks are `repo: local` + `language: system`.
# Requires ruff and mypy installed in your environment.
default_language_version:
  python: python3.12
fail_fast: false
repos:
  - repo: local
    hooks:
      # The playbook — sync drift check
      - id: coding-agent-playbook-sync
        name: coding-agent-playbook sync
        entry: playbook sync --check
        language: system
        pass_filenames: false
        always_run: true
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
Intentionally **not** shipped in the starter: generic-hygiene hooks (trailing-whitespace, end-of-file-fixer, check-yaml/-toml, detect-private-key, check-merge-conflict, check-added-large-files), secret scanning (gitleaks), and notebook hooks (nbstripout/nbqa) — all of which require cloning a remote repo. `ruff format` already covers Python whitespace/EOF; a pre-push `pytest` hook can be added by the consumer as a `repo: local` entry if desired.
### 13.3 Merge with existing `.pre-commit-config.yaml`
If the consumer already has a config, `playbook init` appends only our `coding-agent-playbook-sync` local hook block, and only when it is not already present — it never injects ruff/mypy into a config the consumer already curates. The current implementation is a text-based append; round-trip merging with `ruamel.yaml` (to preserve comments/ordering and surface version conflicts, e.g. a different ruff pin) can land later.
## 14. Distribution and versioning
### 14.1 Channels
- **Engine and overlays**: distributed via internal PyPI (Artifactory). No public PyPI for v1.
- **Pre-commit hooks**: distributed via internal git server.
### 14.2 Versioning contract
SemVer applied to the **rendered output format**, not the Python API:
- **Patch** (`0.4.0 → 0.4.1`): rule wording improvements, bug fixes, no consumer action needed.
- **Minor** (`0.4.0 → 0.5.0`): new rules or prompts added, new optional features. Consumer re-runs `playbook sync` and reviews the diff.
- **Major** (`0.4.0 → 1.0.0`): breaking changes to artifact schema, adapter contract, or CLI surface. Consumer follows a migration guide.
### 14.3 Pinning policy
Consumers pin to a minor range: `coding-agent-playbook>=0.4.0,<0.5.0`. Overlays pin to the engine's minor range. Dependabot / Renovate bumps trigger a `playbook sync` and the diff lands in a PR for review.
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
`playbook sync --check` recomputes the hashes and compares. Mismatch → drift → exit 1.
## 15. Eval abstractions (forward-compatible)
v1 shipped **Tier 0**: the task authoring format (Section 6.5), the loader, the validator, and a read-only CLI. **v1.1 makes Tier 1 live**: `HarnessRunner` (PR R1) executes one task end-to-end against an agent and scores it through the `Metric` / `Check` / `Rubric` model (§21). The `[expected]` file checks and the `[metrics]` static + execution metrics (including non-regression vs the `setup/` baseline) are computable today; the judged `[rubric]` layer is **live as of PR R2** — pass `--judge llm` (or any `coding_agent_playbook.judges` entry) and the `JudgeCheck`s score against the captured diff. With **no judge configured** the runner is deterministic-only (judged checks report `available() is False` and are skipped) — the default. §15.3 describes the as-built v1.1 runner; the design docs are `specs/prR-eval-runner.md` (R1), `specs/prR2-judge-r3-opencode.md` (R2), and `specs/prR6-check-rubric.md` (the R6 clean-slate refactor that replaced the fused `Evaluator`/`grade()` with `Metric`/`Check`/`Rubric`).
### 15.1 The Tier 0 / Tier 1 / Tier 2 ladder
| Tier | Capability | status |
| --- | --- | --- |
| 0 | Task schema, loader, validator, `playbook eval --list/--show` | **shipped (v1)** |
| 1 | Per-harness agent invocation + deterministic scoring (`[expected]` file checks + `[metrics]` static/execution non-regression) via the `Metric`/`Check`/`Rubric` model | **shipped (v1.1 R1)** |
| 2 | Rubric judging (LLM-as-judge) | **shipped (v1.1 R2)** — opt-in `LLMJudge` via `--judge llm`; calibration is future work |
The ladder is deliberate: Tier 0 produces value (documentation, validation) immediately. Tier 1 makes the value computable. Tier 2 closes the loop on subjective quality. Each tier is independently shippable.
### 15.2 v1 abstractions (active)
These ship in v1 and back the `playbook eval --list` / `playbook eval --show` CLI.
```python
# coding_agent_playbook/evals/task.py
from dataclasses import dataclass, field
from pathlib import Path
@dataclass
class TaskSetup:
    files: list[Path]                            # files in setup/ subdir, relative to task dir
    project_kind: str
    python_version: str
    frameworks: list[str]
    # Free-form facts the task wants the detector to mock.
    extra_facts: dict[str, object] = field(default_factory=dict)
@dataclass
class TaskInvocation:
    prompt_args: str                             # what the user "types" after the slash command
    input_variables: dict[str, str] = field(default_factory=dict)
@dataclass
class ExpectedOutcome:
    files_created: list[str] = field(default_factory=list)
    files_must_contain: list[dict] = field(default_factory=list)  # [{path, pattern}]
    files_unchanged: list[str] = field(default_factory=list)
    files_forbidden: list[str] = field(default_factory=list)
@dataclass
class Rubric:
    criteria: list[str]
    weights: list[float] | None = None           # None = uniform
    ref: str | None = None                       # named-rubric registry ref (mutually exclusive with criteria)
@dataclass
class EvalTask:
    id: str
    prompt_id: str
    description: str
    version: int
    source_path: Path                            # where the task.toml lives
    setup: TaskSetup
    invocation: TaskInvocation
    expected: ExpectedOutcome | None = None
    rubric: Rubric | None = None
```
The loader (`coding_agent_playbook.evals.loader.load_tasks`) walks `resources/eval_tasks/`, parses `task.toml` per directory, and produces a `list[EvalTask]`. Overlays add their tasks via the same entry-point mechanism as rules and prompts.
The validator (`coding_agent_playbook.evals.validator.validate_tasks`) enforces:
- Each `task.toml` is well-formed.
- Each task's `setup.files` list matches files actually present in `setup/`.
- Each task's `prompt_id` resolves to a known prompt.
- Each task is listed in its referenced prompt's `eval_tasks:` frontmatter.
- Weights, if present, sum to 1.0 (±0.001 tolerance).
- A `[rubric]` block sets exactly one of `criteria` or `ref` (mutually exclusive); a `ref` resolves to a rubric registered in the `coding_agent_playbook.rubrics` group.

**Named-rubric registry.** A `[rubric]` may name a *code-defined* rubric instead of inlining criteria:
```toml
[rubric]
ref = "code-review"      # mutually exclusive with `criteria`
```
A `Rubric` subclass declares its `CRITERIA = (("criterion", weight), …)` and registers under a name via `@register_rubric("code-review")` from `coding_agent_playbook.evaluators.rubrics` (an out-of-tree extension point — the engine ships none; in-tree registrations win over an entry-point plugin of the same name). `get_rubric(name)` resolves the class and returns `cls.define()` (a built `Rubric` of `JudgeCheck`s, weights normalized to sum 1.0). A task may combine `ref` with `[expected]` and `[metrics]` — `rubric_for_task` splices the referenced rubric's `JudgeCheck`s in alongside the file + metric checks. Out-of-tree packages register named rubrics through the `coding_agent_playbook.rubrics` entry-point group.

That's the entire active surface in v1.
### 15.3 The v1.1 runner (live — deterministic layers)
PR R1 activates the former placeholder. `HarnessRunner` is now a concrete **template method**: `run_task` owns a fixed pipeline (materialize → render prompt → `_invoke_agent` → capture → score → assemble a `TaskResult`) and the single abstract per-assistant hook is `_invoke_agent`. Scoring runs through the `Metric` / `Check` / `Rubric` model (§21): the task's three eval blocks compile into one `Rubric` (`rubric_for_task`) whose ordered checks `Rubric.evaluate` folds into one report, so the deterministic layers — `[expected]` file checks and `[metrics]` static + execution metrics (non-regression vs the `setup/` baseline) — are live. **Judged `[rubric]` scoring landed in v1.1 R2**: `run_task(task, scratch, *, judge=None, samples=1)` takes an optional `Judge` (keyword-only, R1-compatible default) and threads it onto the `EvalContext`; with a judge set the rubric criteria score against the captured diff and fold into the same report, and with none (the default) judged checks report `available() is False` and the report is deterministic-only. The cost-tiered scheduler (§21.4) runs checks cheapest-tier-first; `run_task` is **fail-fast by default** (a lost deterministic gate skips the costlier execution/judged tiers — a failing `[expected]`/metric check never spends an LLM call), and `playbook eval --run --full-scoring` forces every check to run.
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
    report: EvaluationReport                      # the Rubric.evaluate report ([expected] + [metrics] + optional [rubric] checks)
    passed: bool                                  # mirrors report.passed
    aggregate_score: float                        # report.composite, or 1.0/0.0 from passed when no weighted evaluator contributed
    duration_seconds: float
    transcript: str                              # full agent transcript for debugging
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
    """A runner that requires_resolved_prompt could not resolve its prompt."""
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
**Result model evolved (Option B).** `TaskResult` now carries one `report: EvaluationReport` covering the `[expected]` file checks, the `[metrics]` static/execution checks, and (with a judge) the `[rubric]` judged checks, plus the convenience aggregates `passed` / `aggregate_score` / `duration_seconds` / `transcript`. The old `programmatic_checks` / `rubric_scores` lists are **retired**; an `[expected]` predicate is now a deterministic `Check` whose result rides on `report.checks`. (The R6 refactor later repurposed the *name* `CheckResult` for the per-check outcome of `Check.grade` — distinct from the retired placeholder field.) `EvalReport.pass_rate` is the mean of `tr.passed`. This is the **sanctioned v2-activation revision** of the §15.3 placeholder shape (the retired fields had no consumers): v1.1 *is* the activation milestone, so evolving the eval *result* types here is in-bounds while the authored `[metrics]` / `[rubric]` / `[expected]` task schema stays stable.

Concrete runners (discovered via the `coding_agent_playbook.runners` entry-point group — never instantiated directly):
- **`FakeRunner`** (`name="fake"`, `evals/fake_runner.py`) — the **hermetic default + test driver**. Its `_invoke_agent` applies a caller-supplied deterministic mutation (`Callable[[Path], None]`; default a no-op) to the scratch tree and returns a canned transcript. No network, no CLI; every unit test uses it. It leaves `requires_resolved_prompt=False`, so it tolerates the placeholder `render_prompt` emits for a synthetic test task.
- **`ClaudeCodeRunner`** (`name="claude_code"`, `evals/claude_code_runner.py`) — a **thin, opt-in real runner**. Its `_invoke_agent` drives the Claude Code CLI via a plain `subprocess` arg-list (default `claude -p <prompt>`) bound to the scratch repo and captures stdout/stderr as the transcript. Lazy — no top-level CLI import; `available()` returns `False` when the `claude` binary is not on `PATH` (mirroring the `radon` lazy-availability pattern), so it is cleanly skippable and **never exercised in CI**. It sets `requires_resolved_prompt=True`.
- **`OpenCodeRunner`** (`name="opencode"`, `evals/opencode_runner.py`, **PR R3 Track O**) — a second thin, opt-in real runner, the same shape as `ClaudeCodeRunner`. Its `_invoke_agent` drives the OpenCode CLI via a plain `subprocess` arg-list (default `opencode run <prompt>`) with `cwd=scratch_dir` and merges stdout/stderr into the transcript. Lazy — no top-level CLI import; `available()` returns `False` when the `opencode` binary is not on `PATH`, so it is cleanly skippable and **never exercised in CI**. It sets `requires_resolved_prompt=True`. The `command`/`timeout` are configurable (a `{prompt}` token is interpolated, else the prompt is appended).

`ContinueCLIRunner` remains future work (not yet implemented).

**`render_prompt` strictness.** `render_prompt(task, strict=…)` resolves `task.prompt_id` to its `Prompt` (scanning `resources/prompts/` alongside the task tree) and renders the body through the renderer under `StrictUndefined`. When the prompt cannot be resolved: a *real* runner (`requires_resolved_prompt=True`) raises `PromptResolutionError` — a live agent must never be driven with a placeholder; the hermetic `FakeRunner` (`strict=False`) tolerates a stable placeholder because the deterministic scoring layers never read the rendered text.

#### 15.3.1 Scoring bridge (`evals/scoring.py`)
`score(task, baseline, candidate, *, judge=None, samples=1, fail_fast=False) -> EvaluationReport` produces one report across the deterministic families and — with a `judge` set — the judged family. It compiles the task's three eval blocks into **one `Rubric`** (`rubric_for_task(task, task.metrics)`; §21.6), pre-measures the metrics that rubric's metric-checks reference into a `MeasurementSet`, and runs `Rubric.evaluate`:
- **`[metrics]`** — the metric-backed checks (`ThresholdCheck` / `NonRegressionCheck`) grade a `MeasurementSet` the bridge builds up front: **static** metrics measured per candidate `*.py` file (label = tree-relative path so a candidate matches its baseline counterpart), **execution** metrics run a `ProjectHandle` over the candidate tree — both with the baseline measured on the **pristine `setup/` snapshot** so non-regression compares against the untouched setup, not the post-agent tree. The checks grade exactly (`max_worsening=0`; new scopes fall back to absolute).
- **`[rubric]` (R2)** — the `JudgeCheck`s (one per criterion) score the candidate's captured `git diff` (`ctx.artifact`) into a `0-1` SCORE leaf (averaged over `samples`), feeding the weighted composite and gating on the criterion's `threshold` floor. They are JUDGED-cost so the scheduler runs them last, and **`available()` is `True` only when `ctx.judge is not None`** — with no judge (the default) every `JudgeCheck` records `status="skipped"` and never sinks the gate. "Deterministic-only" is **simply no judge configured**; there is no `ProgrammaticOnlyJudge`.
- **`[expected]`** — the four deterministic file checks (`evaluators/checks/files.py`: `FileExistsCheck`, `FileContainsCheck`, `FileUnchangedCheck`, `FileForbiddenCheck`) ignore the `MeasurementSet` and read the candidate tree from `ctx.tree` (`available()` is `False` without one); `FileUnchangedCheck` compares candidate bytes against the `setup/` snapshot via `ctx.baseline_tree`. Each is a pure gate (`required=True`, `weight=0.0`): a check that does not hold gates the report but never feeds the composite.

All three families flow through one `Rubric.evaluate(ctx, measurements, *, strict, fail_fast)` into a single `EvaluationReport`: `composite` is the weight-normalized mean over the run checks' scores, `passed` is the gate verdict (every required, run check must pass — a failed `[expected]` check or a regressed `[metrics]` scope gates it; skipped checks are neutral). `fail_fast` (the runner's default; `--full-scoring` flips it off) lets the cost-tiered scheduler short-circuit once the gate is lost, so a failing deterministic check spares the execution/judged tiers.

### 15.4 Why the eval abstractions live in one tree
The `coding_agent_playbook/evals/` package ships `task.py`, `loader.py`, `validator.py` (active since v1), `runner.py` + `fake_runner.py` + `claude_code_runner.py` + `scoring.py` (live since v1.1 R1), and `judge.py` (**live since v1.1 R2**). `judge.py` defines the concrete-able `Judge` ABC — **Option A**: the per-criterion primitive `score_criterion(criterion, artifact, n=1) -> float` (0–1, n-sample average) is canonical, and the batch `score(rubric, transcript, scratch_dir_state) -> list[float]` is a thin wrapper that maps it over the rubric — plus the opt-in `LLMJudge` (`name="llm"`, shells out to the `claude` CLI, `available()`-gated, never in CI) and the test-only `StubJudge`. This means:
- Overlay authors writing tasks can import `EvalTask`, `TaskSetup`, etc. for type hints in their own tooling.
- The module layout is stable across the v1 → v1.1 progression; only the placeholder bodies get filled in.
- The `[project.entry-points."coding_agent_playbook.runners"]` group is populated (`fake`, `claude_code`, `opencode`); the `coding_agent_playbook.judges` group is now populated with `llm` (third-party packages can register additional runners/judges against either group).
## 16. Testing strategy
### 16.1 Unit tests
- `test_detector.py` — synthetic `pyproject.toml` files in `tests/fixtures/repos/`; assert facts dict matches expected.
- `test_renderer.py` — render templates with hand-crafted context; assert exact output.
- `test_overlays.py` — registration, ordering, override resolution.
- `test_lockfile.py` — hash compute, drift detection.
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
Because each entry carries the whole payload, `import-harness` reconstructs each artifact via `from_dict` **independently of how the leaf rendered or inlined things** — the leaf files exist only for harness clients; the sidecar is the source of truth. When the sidecar is absent (a foreign harness), the importer falls back to best-effort structural inference and surfaces the lossiness (§12.9).
### 20.11 Out of scope: the harness client runtime
The Agent Harness spec also defines a **client runtime contract** — `load_content` / `run_script` and the four loading phases (Load → Discovery → Activation → Execution). The playbook intentionally does **not** implement that runtime. It produces harness files (the `agent_harness` adapter), consumes them (`import-harness`), and validates their structure (`validate-harness`), but it is not a harness *client*: it never injects `HARNESS.md` into a session, reads routing files at runtime, or executes scripts. Modeling the full client runtime is future work; for v1 the `validate-harness` lint is the structural stand-in for runtime conformance (decision #3 in `specs/prH-agent-harness.md` §D).
## 21. Code-quality evaluator subsystem
Added in PR M; **refactored to the `Metric` / `Check` / `Rubric` model in PR R6** (clean-slate, `specs/prR6-check-rubric.md`). This section adds a code-quality measurement engine — static metrics, execution metrics (tests/coverage), and a generalized rubric — behind **three single-responsibility abstractions**, plus a standalone `playbook metrics` gate and a static pre-commit hook. It is purely additive to the sync pipeline: it touches none of it and ships no new hard dependency. The authoritative design is `specs/prR6-check-rubric.md` (and the original `specs/prM-code-metrics.md`, now superseded for the abstraction shape); the as-built lives in `src/coding_agent_playbook/evaluators/` and `commands/metrics.py`.
### 21.1 Three abstractions: `Metric` → `Check` → `Rubric`
A rubric criterion, a code metric, a coverage number, and a test-pass rate are all the same thing — a **graded measurement over a scope** — but *measuring* a value, *grading* it pass/fail, and *aggregating* graded results into a verdict are three distinct responsibilities. PR M originally fused them into one `Evaluator` ABC + a free `grade()`; PR R6 split them along the grain (the realization of the Anthropic "Demystifying Evals for AI Agents" framing — a Check ≈ a grader's pass/fail assertion, a Rubric = a weighting of checks, and a metric becomes a check via a threshold):
```python
class Scope(Enum):       FUNCTION; METHOD; CLASS; FILE; MODULE   # MODULE = the whole target/suite
class Determinism(Enum): DETERMINISTIC; JUDGED                    # who produces the value (routing)
class CostTier(IntEnum): DETERMINISTIC < EXECUTION < JUDGED       # cheapest-first scheduling

class Metric(ABC):                       # the "measure" leaf  (evaluators/metric.py)
    name: str
    scope: Scope
    higher_is_worse: bool                 # CC/WMC/CBO/DIT/LCOM4 True; MI/coverage/test False
    requires: str | None = None           # optional importable dep (e.g. "radon"); None = stdlib
    needs_project: bool = False           # True => execution metric (needs ctx.project)
    def available(self, ctx: EvalContext) -> bool: ...
    @abstractmethod
    def measure(self, ctx: EvalContext) -> list[Measurement]: ...  # one Measurement per scope

class Check(ABC):                        # the "grade" stage  (evaluators/check.py)
    id: str
    weight: float                         # > 0 => contributes to the weighted composite
    required: bool                        # a gate check
    determinism: Determinism              # routing axis
    cost: CostTier                        # scheduling tier
    def available(self, ctx: EvalContext) -> bool: ...
    @abstractmethod
    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult: ...

class Rubric(Metric):                    # the "aggregate" stage  (evaluators/rubric.py)
    def evaluate(self, ctx, measurements, *, strict=False,
                 fail_fast=False, max_workers=1) -> EvaluationReport: ...
    def measure(self, ctx) -> list[Measurement]: ...   # a Rubric is ALSO a Metric (composite as one MODULE measurement)
```
The split: a **`Metric`** carries only the measurement-side descriptors (`name`, `scope`, `higher_is_worse`, `requires`, `needs_project`) and produces a raw `Measurement` per scope; a **`Check`** carries the grading-side policy (thresholds, regression tolerance, `weight`, `required`) and turns measurements (or `ctx` directly, for file/judge checks) into one `CheckResult` — a boolean `passed` gate **plus** an optional `0-1` `score` for partial credit; a **`Rubric`** holds an ordered set of checks and folds their results into one `EvaluationReport` (gate = all `required` checks pass; composite = `Σ(weight·score)/Σweight`). The `EvalContext` (`evaluators/types.py`) carries everything a family might need, decoupled: static reads `module`/`source`/`label`; execution reads `project`; judged reads `judge`/`artifact`/`samples`; file checks read `tree`/`baseline_tree`. `available(ctx)` lets each piece degrade gracefully when its slot or dependency is missing.

**A `Rubric` is also a `Metric` — the Composite.** `Rubric` subclasses `Metric` and exposes its composite as one MODULE-scope `Measurement` via `measure()`, so a rubric thresholds into a parent `ThresholdCheck` and **nests** into a Composite tree (a rubric-of-rubrics). `measure()` self-builds its `MeasurementSet` from the additive `EvalContext.candidate_measurements`/`baseline_measurements`, guards against a re-entrant self-measure (`ValueError`), and memoizes per `ctx`. This replaces the old fused `Evaluator` with a composable algebra: any check tree (booleans via `AllOf`/`AnyOf`/`Not`, §21.2.4) is itself a check.

**The static-vs-execution discriminator is `needs_project`, not the scope axis.** A FILE-scope metric like `coverage` is *execution*, not static, so scope alone cannot separate them; `needs_project=True` is the explicit flag. `static_metrics()` excludes it; a metric-backed check derives its `cost` (EXECUTION vs DETERMINISTIC) from the metric's `needs_project`.

**How the families are differentiated — orthogonal axes, no `kind` enum.** The families are *emergent* from independent fields, so the engine never switches on a "type":

| Family | check class | `determinism` | `cost` | `available(ctx)` needs | authoring block |
|---|---|---|---|---|---|
| static metric (§21.2.1) | `ThresholdCheck`/`NonRegressionCheck` | DETERMINISTIC | DETERMINISTIC | `ctx.module` (source/AST) | `[metrics]` |
| execution (§21.2.2) | `ThresholdCheck` (+`TestsPassCheck`/`CoverageCheck`) | DETERMINISTIC | EXECUTION | `ctx.project` | `[metrics]` |
| judged / rubric (§21.2.3) | `JudgeCheck` | JUDGED | JUDGED | `ctx.judge` | `[rubric]` |
| file check (§21.2.4) | `FileExists`/`FileContains`/`FileUnchanged`/`FileForbidden` | DETERMINISTIC | DETERMINISTIC | `ctx.tree` | `[expected]` |

Authors differentiate by **TOML block** (`[metrics]` / `[rubric]` / `[expected]`), which `rubric_for_task` compiles into a `Rubric` of checks (§21.6); the engine differentiates by the axes and the cost-tiered scheduler routes by capability (`available(ctx)`) + tier, not a type switch — so a new kind drops in by choosing axis values, with no second `grade()` path.

### 21.2 The check families
| Authoring | Family | Metric / Check | `determinism` · `cost` / needs | primary use |
| --- | --- | --- | --- | --- |
| `[metrics]` CC, WMC, MI, LCOM4, DIT, CBO≈ | **static** | static `Metric` → `ThresholdCheck`/`NonRegressionCheck` | DETERMINISTIC · DETERMINISTIC · `ctx.module` (`ast`/`radon`) | threshold + **non-regression** |
| `[metrics]` `test_pass_rate`, `coverage` | **execution** | execution `Metric` → `ThresholdCheck` (`TestsPassCheck`/`CoverageCheck`) | DETERMINISTIC · EXECUTION · `ctx.project` (shells out to `pytest`) | threshold + **non-regression** |
| `[rubric]` criteria + weights | **judged** | `JudgeCheck` (one per criterion) | JUDGED · JUDGED · `ctx.judge` (LLM/human) | weighted composite + threshold |
| `[expected]` file checks | **file** | `FileExists`/`FileContains`/`FileUnchanged`/`FileForbidden` | DETERMINISTIC · DETERMINISTIC · `ctx.tree` | must-be-true gate |
#### 21.2.1 Static metrics (`evaluators/builtins/`)
Source is parsed **once** into a `ModuleModel` (`evaluators/parse.py`, which also owns the shared `_cyclomatic` helper and the stable scope keys `<label>::<qualname>` / `<label>`); each available static `Metric` reads that model via its module-level `_measure` helper. All are stdlib-`ast`-only except MI, which is the lone radon-backed one. The grading-side policy (the warn/fail bounds + regression tolerance below) lives on the *check*, not the metric: the shared per-metric defaults are `evaluators/policy.py::METRIC_DEFAULTS`, applied by `metric_check()` when a `[metrics]` config has no override.
| `name` | scope | `higher_is_worse` | default warn/fail | default `max_worsening` | requires |
| --- | --- | --- | --- | --- | --- |
| `cyclomatic_complexity` | FUNCTION/METHOD | true | `warn=10, fail=20` | `max_worsening=0` | — |
| `wmc` | CLASS | true | `fail=50` | `max_worsening=0` | — |
| `lcom4` | CLASS | true | `warn=2` | `max_worsening=0` | — |
| `dit` | CLASS | true | `warn=5` | `max_worsening=0` | — |
| `cbo` (≈) | CLASS | true | `warn=14` | `max_worsening=0` | — |
| `maintainability_index` | FILE | **false** | `fail=65` | `max_worsening=0` | `radon` |
Algorithms: **CC** = 1 + decision points (`If/For/AsyncFor/While`, comprehension `if`s, `BoolOp` operands−1, `ExceptHandler`, `IfExp`, `match` guards, `assert`); **WMC** = Σ of method CC; **LCOM4** = connected components of the method graph (shared `self.x` attr or `self.m()` call); **DIT** = longest resolvable base chain (external base = depth 1); **CBO≈** = distinct external types referenced (labeled approximate — undercounts under duck typing); **MI** = `radon.metrics.mi_visit(source, multi=True)`, the SEI 0–100 variant. `maintainability_index` is the engine's only optional extra (`pip install 'coding-agent-playbook[metrics]'`): it self-registers like every builtin, but radon is imported **lazily inside `measure`** and `available()` returns `False` when radon is absent, so the gate transparently skips MI and the engine still loads air-gapped with nothing extra installed.
#### 21.2.2 Execution metrics (`evaluators/execution/`)
Deterministic, but they need to **run the target's test suite**, so they add **no playbook dependency**: a `ProjectHandle` (`execution/project.py`) runs a configurable command (default `python -m pytest --junitxml=… --cov --cov-report=xml:… -q`) in the target, and the metrics parse the standard **junit XML** + **coverage XML** with stdlib `xml.etree.ElementTree` (`execution/junit.py`, `execution/coverage_xml.py`). The target supplies `pytest`/`pytest-cov`. The convenience check factories `TestsPassCheck()`/`CoverageCheck()` (`evaluators/checks/execution.py`) are thin `ThresholdCheck` wrappers bound to these metrics with the conventional default bounds.
| `name` | scope | `higher_is_worse` | default warn/fail | default `max_worsening` | needs |
| --- | --- | --- | --- | --- | --- |
| `test_pass_rate` | MODULE (suite) | false | `fail=1.0` (all must pass) | `0` (no new failures) | `ctx.project` |
| `coverage` | FILE (+MODULE total) | false | `warn=80` | `0` (must not drop) | `ctx.project` |
- **One run, both metrics:** `ProjectHandle.run()` executes the suite once and caches the parsed junit + coverage reports; both metrics read that cache (no double run).
- **Flaky tolerance:** `test_pass_rate` is DETERMINISTIC but supports an optional flaky-retry (`ProjectHandle.flaky_retries`; reruns and takes the best observed pass rate); off (`0`) by default.
- **Non-regression needs two runs.** Standalone with `--baseline git:<ref>` materialises the ref via a temporary `git worktree add` (heavier than the static `git show`); `--baseline <dir>` runs the suite there. Absolute mode (single run on the current tree) is the lighter default.
- **Opt-in & cost-gated:** running tests has side effects and cost, so execution metrics are opt-in (`--run-tests`); their checks are EXECUTION-tier (the scheduler runs them after the deterministic tier) and are **excluded from the default pre-commit hook** — it stays static-only.
#### 21.2.3 Judged criteria — the rubric, as checks (`evaluators/checks/judged.py`)
A rubric criterion is a `JudgeCheck`: a graded SCORE whose value comes from a *judge* (LLM/human). It is **parameterized**, not a registered singleton — `rubric_for_task` instantiates one per rubric line, each carrying its own `criterion` text, `weight`, and a `0-1` `threshold` floor (id `judge:<slug>`, `determinism=JUDGED`, `cost=JUDGED`). `grade` calls `ctx.judge.score_criterion(self.criterion, ctx.artifact, n=ctx.samples) -> float` and averages over `ctx.samples` to damp LLM noise; the score feeds the composite and the `passed` gate is `score >= threshold`. It is **dormant without a judge**: `available()` returns `True` only when `ctx.judge` is set, so a `Rubric` evaluated with no judge records each `JudgeCheck` as `status="skipped"` (never sinking the gate). Because `JudgeCheck` is JUDGED-cost, the cost-tiered scheduler (§21.4) runs it **last** — a failing deterministic gate short-circuits it away, so a failed `[expected]`/metric check never spends an LLM call.
> **Judge signature — reconciled (R2), still closed.** `JudgeCheck.grade` calls `ctx.judge.score_criterion(criterion, artifact, n) -> float` — the **canonical per-criterion primitive** (Option A). The `Judge` ABC's batch `score(rubric, transcript, scratch_dir_state) -> list[float]` is a thin wrapper that maps `score_criterion` over the rubric, so the two shapes are the *same* operation at different granularities. `ctx.judge` is typed as the structural `JudgeLike` protocol **defined in `evaluators/types.py`** (not `evals`) so `evaluators` never imports `evals` — avoiding the `evaluators` ↔ `evals` cycle; the concrete `Judge` satisfies it structurally. Tests exercise `JudgeCheck` via the deterministic `StubJudge`.
#### 21.2.4 File checks + boolean composers (`evaluators/checks/`)
The four `[expected]` predicates are first-class deterministic `Check`s (`evaluators/checks/files.py`): `FileExistsCheck` (`files_created`), `FileContainsCheck` (`files_must_contain`, path + regex), `FileUnchangedCheck` (`files_unchanged`, byte-identical to the `setup/` snapshot via `ctx.baseline_tree`), and `FileForbiddenCheck` (`files_forbidden`). Each ignores the `MeasurementSet` and reads `ctx.tree` directly, is a pure gate (`required=True`, `weight=0.0`), and its `passed` comes straight from the predicate (`available()` is `False` without a candidate tree). The boolean composers `AllOf`/`AnyOf`/`Not` (`evaluators/checks/compose.py`) are themselves checks that fold child checks through the scheduler (an unavailable child is *neutral*, not a failure), so any check tree nests freely inside a `Rubric`.
### 21.3 Registry — decorator + entry points
In-tree metric builtins self-register via the `@register_metric` class decorator (each `builtins/*` and `execution/*` module decorates its class; `builtins/__init__` and `execution/__init__` import them so the decorators fire). Out-of-tree **metrics** register through the `coding_agent_playbook.metrics` entry-point group (renamed from the old `…​.evaluators`); out-of-tree **custom grader checks** register through the new `coding_agent_playbook.checks` group. **In-tree builtins win** over an entry point reusing a registered name. The list is never hardcoded. Metric selection helpers (`evaluators/metric.py`):
- `all_metrics()` — builtins + entry points, deduped by name.
- `static_metrics()` — every metric with `not needs_project` (the `playbook metrics` default set).
- `execution_metrics()` — every metric with `needs_project` (`coverage`, `test_pass_rate`); `--run-tests` adds these.
- `get_metric(name)` — a fresh instance, or `KeyError`.
### 21.4 Aggregation — `Rubric.evaluate` + the cost-tiered scheduler
`Rubric.evaluate(ctx, measurements, *, strict=False, fail_fast=False, max_workers=1) -> EvaluationReport` replaces the old free `grade()`. It runs its ordered checks through the cost-tiered scheduler (`evaluators/scheduler.py`) and folds the `CheckResult`s into one report. Each metric-backed check (`_MetricCheck`) decides per scope, matching the baseline by `(metric.name, scope_key)`:
- **existing scope:** `worsening = (cand − base)` if `higher_is_worse` else `(base − cand)`; `> max_worsening` ⇒ `fail`/`kind="regression"`; otherwise the absolute level. The per-scope `score` is the normalized `0-1` ramp around the warn/fail bounds.
- **new scope:** absolute only, `kind="new"`. **removed scope:** ignored.
**Gate-boundary semantics** are asymmetric: on the **higher-is-worse** side the bound is **inclusive** (`value >= bound` breaches — CC of exactly `20` fails); on the **higher-is-better** side it is **strict** (`value < bound` breaches — coverage of exactly `80` is `ok`, `test_pass_rate` of exactly `1.0` is `ok` even with `fail=1.0`).
Two aggregates fall out: the **gate** (`passed` = every *required, run* check passes; under `strict` no required run check may carry a `warn` leaf; skipped checks are neutral) and the **composite** (weight-normalized mean of the run checks' `score` over checks with `weight > 0`, spanning all families uniformly; `None` when no weights are set). The metric-backed check `mode` is `regression` (default), `absolute`, or `both` (regression failure takes precedence, then absolute), resolved by `metric_check()` from the `[metrics]` config.

**The scheduler (`evaluators/scheduler.schedule`)** is the Strategy a `Rubric` (and the composers) use to run checks: **cheapest-tier-first** (`DETERMINISTIC` → `EXECUTION` → `JUDGED`), results always returned in **authored order**, with an optional **short-circuit** (`op="and"` stops descending into costlier tiers the moment a required check fails; `op="or"` stops on the first pass) and optional within-tier `concurrent.futures` concurrency (`max_workers > 1`; the default `1` is the deterministic path CI uses). The headline guarantee: a lost deterministic gate **never grades the JUDGED tier** — the LLM judge is never invoked. `Rubric.evaluate` defaults to `fail_fast=False` (complete report); the runner passes `fail_fast=True` for cost-saving, which `playbook eval --run --full-scoring` flips off.
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
### 21.6 Eval `[metrics]`/`[rubric]`/`[expected]` wiring — live (v1.1)
The eval task schema (§15) carries a top-level `[metrics]` block, a **sibling of `[expected]`/`[rubric]`**, parsed into `EvalTask.metrics: MetricConfig | None` (`evals/task.py`) and validated (`evals/validator.py` rule 7: a valid `mode`, every named metric registered — static **or** execution like `coverage`/`test_pass_rate` — and numeric bounds/deltas/weights; violations are aggregated, never raised). `rubric_for_task(task, config)` compiles **all three blocks into one `Rubric` of checks** (block order metrics → rubric → expected, for a stable findings order):
- `[metrics]` → one metric-backed `ThresholdCheck`/`NonRegressionCheck` per metric named in `thresholds`/`regression`/`weights` (deduped), via the shared `metric_check()` factory.
- `[rubric]` → one `JudgeCheck` per criterion (uniform `1/len` weights when omitted; `required=False`, dormant without a `ctx.judge`).
- `[expected]` → one deterministic file check per `ExpectedOutcome` entry (`FileExistsCheck`/`FileContainsCheck`/`FileUnchangedCheck`/`FileForbiddenCheck`, each `required=True`, `weight=0.0`).
The `Rubric` is named `task.id`. The scoring bridge (§15.3.1) measures the referenced metrics over the candidate (vs the pristine `setup/` snapshot) and runs `Rubric.evaluate` — so all three families flow through **one report**, gate + composite.
```toml
# task.toml — [metrics] sibling of [expected]/[rubric]  (UNCHANGED — zero authoring migration)
[metrics]
mode = "regression"
[metrics.regression]
cyclomatic_complexity = { max_worsening = 0 }
coverage              = { max_worsening = 0 }   # coverage must not drop
test_pass_rate        = { max_worsening = 0 }   # no newly-failing tests
[rubric]
criteria = ["Findings prioritized correctly", "Each finding proposes a concrete fix"]
weights  = [0.5, 0.5]
```
With no judge configured the `[rubric]` `JudgeCheck`s skip and the report is the deterministic `[metrics]` + `[expected]` layers only; with `--judge llm` they score against the captured diff and fold in. The authored TOML is identical to PR M — the R6 refactor changed only the engine internals, not the task format.
### 21.7 Invariants
- **Single responsibility — `Metric` measures, `Check` grades, `Rubric` aggregates.** No fused `Evaluator`; no free `grade()` (it is `Rubric.evaluate`); no `value_kind`/`to_score`/`default_*`/`extra_evaluators`. A metric becomes a gateable thing only by wrapping it in a `Check` (a threshold). A `Rubric` is also a `Metric`, so check trees compose (Composite) and nest.
- **Air-gapped / no new hard deps.** Core is stdlib-only (`ast`, `dataclasses`, `enum`, `subprocess`, `xml.etree`, `tempfile`, `importlib.metadata`); `radon` is the only optional extra (`[metrics]`, lazy import via `available()`); execution metrics shell out to the *target's* `pytest` and parse XML with stdlib — no playbook dep. The engine + static `playbook metrics` run with nothing extra installed.
- **Registry via decorator AND entry points** — metrics under `coding_agent_playbook.metrics` (`@register_metric`), out-of-tree grader checks under `coding_agent_playbook.checks`, named rubrics under `coding_agent_playbook.rubrics` (`@register_rubric("name")`, referenced from a task's `[rubric] ref`); never hardcode the list; never instantiate out-of-tree metrics/checks/rubrics directly. In-tree builtins/registrations win on a name clash.
- **Cost-tiered short-circuit.** The scheduler runs checks `DETERMINISTIC` → `EXECUTION` → `JUDGED`, so a failing deterministic gate **never invokes the LLM judge**; results stay in authored order. `--full-scoring` forces every check.
- **Non-regression is primary** (new scopes fall back to absolute). Deterministic static/execution compare exactly (`max_worsening=0`); judged uses a `threshold` floor + n-sample averaging; `test_pass_rate` has an optional flaky-retry.
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
- `.coding-agent-playbook.toml`
- `.coding-agent-playbook.local.toml`
- updated `.gitignore`
- merged `.pre-commit-config.yaml`
- runs `pre-commit install`
- runs `playbook sync`
### A.4 Step 3: result
Generated files (all with sentinel headers):
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
Engineer commits the diff. The team reviews the change like any other config change.
### A.7 Step 6: drift detection
A junior developer hand-edits `.continue/rules/50-python-typing.md` without going through the source.
```bash
$ git commit -m "tweak rule"
[pre-commit running]
playbook-sync-check:
✗ Drift detected:
  .continue/rules/50-python-typing.md
    Generated content differs from on-disk content.
    Either revert the manual edit, or update the canonical template
    in coding-agent-playbook / playbook-rules-bnp and bump the version.
[commit blocked]
```
The dev either reverts, or files a PR against the overlay to make the change properly.
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
*End of SPEC.md v0.12.*
---
## Changelog
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
