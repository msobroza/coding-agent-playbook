# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Source of truth: SPEC.md

The design lives in `SPEC.md` (v0.9, draft). Read it before making structural changes — it defines the architecture, repo layout, artifact model, adapter contract, configuration, CLI surface, eval format, the code-quality evaluator subsystem, and rollout plan. If the spec is ambiguous, surface the question rather than guessing.

## What this project is

`coding-agent-playbook` is a Python-first engine that takes one canonical source of organizational coding context (rules, prompts, skills, eval tasks in markdown + YAML frontmatter) and renders it into whatever each AI coding assistant expects: `.continue/`, `.claude/`, `.opencode/`, and the universal `AGENTS.md`.

Distribution model:
- The engine ships generic content.
- Organization-specific overlay packages (e.g. `playbook-rules-bnp`) layer on top.
- Consumer repos can override locally via a `playbook/` directory.

The CLI binary is `coding-agent-playbook` with alias `playbook`. The workhorse command is `playbook sync`. Drift between canonical source and rendered output fails a pre-commit hook.

## Repository status

The core engine is **complete**: detector, renderer, filesystem sources, the CLI, the Tier 0 eval schema, and the four original adapters (Continue, Claude Code, OpenCode, AGENTS.md). The original 14-PR build-out (≈3,900 LoC Python + ≈800 lines of content) is implemented; the layout matches SPEC §5.1.

**Agent Harness support (PR H)** is implemented on top of that engine: the opt-in `agent_harness` output adapter (`adapters/agent_harness_adapter.py`), the `playbook import-harness` and `playbook validate-harness` commands (`commands/import_harness.py`, `commands/validate_harness.py`), and the shared `harness/` core module (`models`, `leaf_detectors`, `parser`, `emitter`, `manifest`) with the `.playbook/manifest.toml` round-trip sidecar. Its design lives in `specs/prH-agent-harness.md`; the SPEC sections are §10.7 (adapter), §12.9/§12.10 (CLI), §20.10/§20.11 (sidecar + client-runtime scope).

**Code-quality evaluator subsystem (PR M, refactored in PR R6)** is implemented on top of that engine. **As of PR R6 it is the `Metric` / `Check` / `Rubric` model** (clean-slate refactor of the original fused `Evaluator` ABC + free `grade()`): `Metric` (`evaluators/metric.py`, `measure(ctx) -> list[Measurement]`) measures, `Check` (`evaluators/check.py` + `evaluators/checks/`, `grade(ctx, measurements) -> CheckResult`) grades (a boolean gate + optional partial-credit score), and `Rubric` (`evaluators/rubric.py`, `evaluate(...) -> EvaluationReport`) aggregates (gate + weighted composite) — and a `Rubric` is **also a `Metric`** (Composite, so check trees nest). Three families: static metrics (`evaluators/builtins/*`: CC, WMC, LCOM4, DIT, CBO≈ via `ast`; `maintainability_index` via the optional `radon` extra) + execution metrics (`evaluators/execution/*`: `test_pass_rate`, `coverage`, shelling out to the target's `pytest`) wrapped in `ThresholdCheck`/`NonRegressionCheck`; the `[expected]` file checks (`evaluators/checks/files.py`); and judged `JudgeCheck` (`evaluators/checks/judged.py`, the rubric line generalized, dormant without a judge). Plus the shared core (`scope`, `types`, `parse`, `policy`, `scheduler`) and the standalone `playbook metrics` command (`commands/metrics.py`) with a `repo: local` static pre-commit hook. The refactor design lives in `specs/prR6-check-rubric.md` (the original `specs/prM-code-metrics.md` is superseded for the abstraction); out-of-tree migration in `MIGRATION.md`; the SPEC section is §21. **The live eval-task wiring described here (`[expected]`/`[metrics]`/`[rubric]` + `rubric_for_task`) was redesigned in v0.13 — see the "Task-config redesign" paragraph below for the current `[gate]`/`[rubric]`/`[verdict]`/`[aggregate]` format.**

**Eval runner (PR R1, v1.1)** is implemented on top of PR M: the former v2 placeholder is now **live for the deterministic layers**. `HarnessRunner` (`evals/runner.py`) is a concrete **template method** (`run_task` = `materialize` → `render_prompt` → `_invoke_agent` → `capture` → `score`; `_invoke_agent` is the only per-assistant hook), the scoring bridge (`evals/scoring.py`) compiles the task's eval blocks into one `Rubric` (`rubric_for_task`) and grades `[expected]` file checks + `[metrics]` static/execution metrics (non-regression vs the pristine `setup/` snapshot) through `Rubric.evaluate` into one `EvaluationReport`, and runners ship via the `coding_agent_playbook.runners` entry-point group: the hermetic `FakeRunner` (`evals/fake_runner.py`, default test driver) and the opt-in `ClaudeCodeRunner` (`evals/claude_code_runner.py`, `available()`-gated, never in CI) — joined by `OpenCodeRunner` in R3 (see below). The CLI gains `playbook eval <id> --run [--runner …] [--format …]` (`commands/eval.py`). **Judged `[rubric]` scoring landed in PR R2** and the `[expected]` checks were unified into real evaluators in PR R3 (see below). Its design lives in `specs/prR-eval-runner.md`; the roadmap is `specs/v1.1-eval-execution.md`; the SPEC sections are §15.3/§15.3.1 (runner + scoring) and §12.8 (the `--run` CLI).

**Judge (PR R2, v1.1)** is implemented on top of PR R1: the former `Judge` placeholder is now **concrete-able** and judged `[rubric]` scoring is live. The `Judge` ABC (`evals/judge.py`) is **Option A** — the per-criterion primitive `score_criterion(criterion, artifact, n=1) -> float` (0–1, n-sample average) is canonical and the batch `score(rubric, transcript, scratch_dir_state) -> list[float]` is a thin wrapper over it. The opt-in `LLMJudge` (`name="llm"`) shells out to the `claude` CLI (arg-list, configurable command template, `available()`-gated, **never in CI**, registered in the `coding_agent_playbook.judges` group); `StubJudge` (unregistered) drives hermetic tests. `JudgeCheck.grade` (`evaluators/checks/judged.py`, the PR-R6 home of the rubric criterion) calls `ctx.judge.score_criterion(...)` through the structural `JudgeLike` Protocol defined in `evaluators/types.py` (so `evaluators` never imports `evals` — no cycle); `EvalContext.judge` is typed `JudgeLike | None`. The `[rubric]` `JudgeCheck`s are JUDGED-cost entries in the task's `Rubric`, so `Rubric.evaluate` folds their SCORE leaves into the same report; `run_task(task, scratch, *, judge=None, samples=1)` threads the judge on, and the CLI gains `playbook eval <id> --run [--judge llm] [--samples N]`. **"Deterministic-only" = no judge configured** (no `ProgrammaticOnlyJudge`). Design: `specs/prR2-judge-r3-opencode.md` (Track J), refactored by `specs/prR6-check-rubric.md`; SPEC §15.3/§15.3.1, §15.4, §21.2.3 (debt closed), §12.8.

**`[expected]` unification + OpenCodeRunner (PR R3, v1.1)** is implemented on top of PR R2:
- **Track E — `[expected]` unified.** The four `ExpectedOutcome` file checks are deterministic `Check`s (since PR R6: `evaluators/checks/files.py`: `FileExistsCheck` / `FileContainsCheck` / `FileUnchangedCheck` / `FileForbiddenCheck`), compiled by `rubric_for_task` (`evals/task.py`) into the task's `Rubric` alongside `[metrics]` and `[rubric]`. Each is `required=True`, `weight=0.0`, DETERMINISTIC-cost, with `passed` straight from the predicate; it reads the candidate tree from `EvalContext.tree` (and the pristine `setup/` snapshot from `EvalContext.baseline_tree` for `file_unchanged`). This **removes the R1 interim** that compiled `[expected]` into BOOL findings outside the grader; `[expected]` + `[metrics]` + (with a judge) `[rubric]` now flow through one `Rubric.evaluate` into one `EvaluationReport`.
- **Track O — `OpenCodeRunner`.** A second thin, opt-in real runner (`evals/opencode_runner.py`, `name="opencode"`, registered in `coding_agent_playbook.runners`), the same shape as `ClaudeCodeRunner`: its `_invoke_agent` drives the OpenCode CLI via a plain `subprocess` arg-list (default `opencode run <prompt>`, `cwd=scratch_dir`, configurable `command`/`timeout`), is lazy/stdlib-only, `available()`-gated on the `opencode` binary, **never in CI**, and sets `requires_resolved_prompt=True`.

Design: `specs/prR2-judge-r3-opencode.md` (Tracks E + O), with Track E refactored to the `Check` model by `specs/prR6-check-rubric.md`; SPEC §15.3/§15.3.1, §15.4, §12.8.

**Evaluator subsystem refactor (PR R6, v1.1)** replaced the fused `Evaluator` ABC + free `grade()` with the `Metric` / `Check` / `Rubric` model (see the PR-M paragraph above and the invariants below). Design: `specs/prR6-check-rubric.md`; out-of-tree migration: `MIGRATION.md`; SPEC §21 (and the §0.12 changelog).

**Task-config redesign (PR "2b refined", Tracks C1–C8, v0.13)** is the **current authored eval-task format** and supersedes the `[expected]`/`[metrics]`/`[rubric]` triple in the PR-M / R1–R6 paragraphs above. A task now declares **layers** sharing one `[<layer>.bind]` + `[<layer>].expr` shape: a deterministic **`[gate]`** (file/metric `check`s composed by a tiny boolean `expr`), an llm-judge **`[rubric]`** (weighted criteria, thresholded to a boolean), a **`[verdict]`** (`trial`, a boolean expr over the two layers — the verdict is *derived* from the layer results, not re-run), and an optional cross-trial **`[aggregate]`** (`pass@k`/`pass^k`). There is **no `[expected]` block** — file predicates are gate `check`s (`file_exists`/`file_contains`/`file_unchanged`/`file_forbidden`). Thresholds are **0–1 normalized**: every `Metric` owns a `Normalizer` (`evaluators/normalizer.py`: `RampNormalizer`/`PercentNormalizer`/`Identity`) and `higher_is_worse` is **deleted**. A check is `(type) × (metric|judge) × kwargs` — `check = "threshold"|"non_regression"` over a registered `metric=` or a `judge=` criterion (a `JudgeMetric`, `evaluators/checks/judge_metric.py` — an llm-judge criterion *is* a metric). New registries: checks (`@register_check` + `coding_agent_playbook.checks`, `evaluators/checks/registry.py`) and **gates** (`@register_gate` + the new `coding_agent_playbook.gates`, `evaluators/gates.py`); a handle `{ref="name"}` resolves a registered composed **gate** or **rubric**. The compile path is `evals/_expr.py` (the boolean-expression Interpreter) → `evals/_handles.py` (the handle Factory/Composite) → `evals/_compile.py` (the layer compiler + derived verdict); `evals/task.py` carries `EvalTask.gate/rubric/verdict/aggregate` `Layer`s + `compile_eval_task` (the old `rubric_for_task`/`ExpectedOutcome` are **deleted**). The runner runs `N=max(k)` trials for the aggregate layer (`evaluators/checks/aggregate.py`). Design: `specs/pr2b-task-config.md`; migration: `MIGRATION.md`; SPEC §6.5.3, §15.2/§15.3/§15.3.1, §21 (and the §0.13 changelog). **The standalone `playbook metrics` command + its `[metrics]` engine config in `.coding-agent-playbook.toml` are unchanged.**

## Where to read in the spec

- **§4** — architecture overview & end-to-end `playbook sync` data flow.
- **§5.1** — engine repo layout (target).
- **§6** — canonical artifact model.
  - 6.0 `.md` vs `.md.j2` dispatch.
  - 6.2.5 rule inclusion in prompts (`includes_rules:` + `{{ rule() }}`).
  - 6.5 eval task schema (Tier 0).
  - 6.6 canonical typed dataclasses + round-trip contract.
- **§8** — detector facts inventory & project-kind inference.
- **§9** — renderer (Jinja env, `rule()` helper, format post-processing).
- **§10** — adapter ABC + the four built-in adapters (Continue, Claude Code, OpenCode, AGENTS.md); §10.7 the opt-in `agent_harness` adapter.
- **§11** — three-layer overlay merge semantics.
- **§12** — CLI contract with example output for every subcommand; §12.9/§12.10 `import-harness` / `validate-harness`.
- **§15** — eval abstractions: the live `HarnessRunner` template method + the scoring bridge; §15.2 the `EvalTask`/`Layer` task schema (the `[gate]`/`[rubric]`/`[verdict]`/`[aggregate]` layers), §15.3/§15.3.1 the runner + scoring (derived verdict).
- **§20** — storage source abstraction (`ArtifactSource`, `StateSource`); §20.10 the `.playbook/manifest.toml` round-trip sidecar; §20.11 client-runtime out-of-scope note.
- **§21** — code-quality evaluator subsystem (the `Metric` / `Check` / `Rubric` model + the families, the per-`Metric` `Normalizer` (§21.1), the `coding_agent_playbook.metrics`/`.checks`/`.gates`/`.rubrics` registries (§21.3), `Rubric.evaluate` gate + composite, the cost-tiered scheduler/short-circuit + the Composite (Rubric-is-a-Metric), `JudgeMetric` (§21.2.3) + aggregate `pass@k`/`pass^k` (§21.2.5) + the expression DSL/derived verdict (§21.2.6), `playbook metrics` + static pre-commit hook, the live eval `[gate]`/`[rubric]`/`[verdict]`/`[aggregate]` wiring (§21.6), and the radon extra).
- **`specs/prH-agent-harness.md`** — the authoritative Agent Harness design (artifact catalog §A, canonical→harness mapping §B, sidecar §C, locked decisions §D).
- **`specs/pr2b-task-config.md`** — the authoritative design for the **current task-config format** (the `[gate]`/`[rubric]`/`[verdict]`/`[aggregate]` layers, the handle Factory/Composite + expression DSL + derived verdict, 0–1 normalization, `JudgeMetric`, pass@k, the C1–C8 track list, the SOLID/pattern map). **Supersedes the `[expected]`/`[metrics]`/`[rubric]` task schema** in the PR-M / R6 docs.
- **`specs/prR6-check-rubric.md`** — the authoritative design for the `Metric` / `Check` / `Rubric` *engine* refactor (the 5 SOLID smells fixed, the model + Composite + scheduler, locked decisions, what was deleted). **Supersedes the `Evaluator`/`grade()` abstraction in `specs/prM-code-metrics.md`**; the *task format* it describes is in turn superseded by `specs/pr2b-task-config.md`.
- **`specs/prM-code-metrics.md`** — the original code-metrics design (static metrics §B, execution metrics §B2, judged §B3, consumers §D, invariants §F, locked decisions §H). The `Evaluator`/`grade()` *abstraction* (§A, §C) is superseded by `specs/prR6-check-rubric.md`; the metric algorithms and task schema still hold.
- **`MIGRATION.md`** — the out-of-tree migration guide for the R6 refactor (`Evaluator` → `Metric`, the entry-point group rename, `grade()` → `Rubric.evaluate`; the authored task TOML is unchanged).

## Invariants enforced by the spec

- **Copies, not symlinks.** Banking-friendly, cross-platform.
- **Jinja sparingly.** Variable substitution and `{% if %}` for file-selection only — never `{% if %}` inside rule bodies.
- **Frontmatter is static YAML.** Parsed before Jinja runs; never templated.
- **`StrictUndefined`.** Typos in template variables must fail loudly.
- **Sentinel header on every generated file** (`# AUTOGENERATED — edit in coding-agent-playbook, run 'playbook sync'`).
- **`AGENTS.md` is always generated**, regardless of which adapters are enabled.
- **Rules cannot include other rules.** Only prompts have `includes_rules:`; the `rule()` Jinja helper is registered only when rendering prompts.
- **No HTTP-handler hooks by default** — the engine is air-gapped-friendly. No telemetry, ever.
- **Markdown links in artifacts are self-contained (PR L).** Every link in a rule/prompt/skill body (incl. skill `references/*.md`) must resolve to a file inside its source layer (package `resources/` or repo-local `playbook/`); `http(s)` links pass only via `[links] allowed_domains` in `.coding-agent-playbook.toml` (default empty), all other schemes and absolute paths are violations. Deterministic (stdlib, no network): `links.py` + the `playbook validate` rule; the engine's own artifacts are CI-gated by `tests/cli/test_validate_links.py`. Design: `specs/prL-markdown-links.md`; SPEC §12.6/§7.1.

### Agent Harness adapter invariants (PR H)

- **`agent_harness` is opt-in.** It is not in the default adapter set and is not force-enabled like `agents_md`; enable it via `[adapters] enabled`. `AGENTS.md` is still always generated regardless of which adapters are on.
- **Sentinel as the first body line.** Harness frontmatter must stay on line 1 (`^---`) for the parser, so the `SENTINEL` cannot be line 1 — it is written as the first body line after the closing fence. `cleanup_stale` therefore detects the sentinel *anywhere* in a file, not just on line 1.
- **`.harnessleaf` marks opaque dirs.** A directory carrying a `.harnessleaf` marker is a terminal opaque unit; the parser stops recursing into it and both the importer and validator skip its internal content (no routing-file expectation, no content inspection).
- **Copies, not symlinks for scripts.** A skill's `scripts/` and `references/` are byte-copied (`shutil.copy2`); each script's executability is recorded as a git-style single-bit `executable` flag in `.playbook/manifest.toml` (not a full octal mode) and restored on POSIX during import, no-op on Windows.

### Metric / Check / Rubric invariants (PR M, refactored PR R6; task format redesigned v0.13)

> **v0.13 note:** the bullets below describe the `Metric`/`Check`/`Rubric` *engine* (still current). Where they mention the **authored task format** (`[expected]`/`[metrics]`/`[rubric]` blocks, `rubric_for_task`, `higher_is_worse`), read the "Task-config redesign" paragraph above — those are superseded by the `[gate]`/`[rubric]`/`[verdict]`/`[aggregate]` layers, the per-`Metric` `Normalizer`, and the `evals/_compile.py` compiler.

- **Three responsibilities, three abstractions.** `Metric` measures (`measure(ctx) -> list[Measurement]`; only the measurement descriptors — `name`/`scope`/`normalizer`/`requires`/`needs_project`/`needs_judge`), `Check` grades (`grade(ctx, measurements) -> CheckResult` — a boolean `passed` gate + an optional `score` partial-credit; carries the threshold/regression/`weight`/`required`/`cost`/`determinism` policy), `Rubric` aggregates (`evaluate(...) -> EvaluationReport` — gate + weighted composite). No fused `Evaluator`; no free `grade()` (it is `Rubric.evaluate`); no `value_kind`/`to_score`/`default_*`/`extra_evaluators`/`higher_is_worse` (direction lives in the `Metric`'s `Normalizer`; v0.13). A metric only gates by being wrapped in a `Check` (a threshold).
- **A `Rubric` is also a `Metric` (Composite).** `Rubric` subclasses `Metric` and surfaces its composite via `measure()`, so a rubric thresholds into a `ThresholdCheck` and **nests** into a parent rubric; `measure()` self-builds its `MeasurementSet` from `EvalContext.candidate_measurements`/`baseline_measurements`, guards re-entrancy (`ValueError`), and memoizes per `ctx`. The boolean composers `AllOf`/`AnyOf`/`Not` (`evaluators/checks/compose.py`) are checks too.
- **Cost-tiered short-circuit scheduler.** `evaluators/scheduler.py` runs checks cheapest-tier-first (`CostTier` DETERMINISTIC < EXECUTION < JUDGED), results in authored order, with a short-circuit so a **failing required deterministic check never invokes the LLM judge**; `Rubric.evaluate` defaults `fail_fast=False` (complete report), the runner passes `fail_fast=True`, and `playbook eval --run --full-scoring` forces every check.
- **Stdlib-default core; radon is the only optional extra.** The evaluator core and the static `playbook metrics` gate are stdlib-only (`ast`, `subprocess`, `xml.etree`, …) and run with nothing extra installed. `maintainability_index` is the lone radon-backed metric (`pip install '…[metrics]'`); radon is imported **lazily inside `measure`** and `available()` returns `False` when it is absent, so the gate transparently skips MI. Never make radon a hard dep.
- **Execution metrics shell out and are opt-in.** `test_pass_rate`/`coverage` run the *target's* `pytest`/`pytest-cov` (no playbook dep) and parse junit/coverage XML with stdlib. They need `--run-tests` (or `[metrics] run_tests`), have side effects/cost, and their checks are EXECUTION-tier and **excluded from the default pre-commit hook** — the `playbook-metrics` hook is static-only. The static-vs-execution discriminator is the metric's `needs_project` flag, not the scope axis.
- **Registry via decorator AND entry points.** Metric builtins self-register with `@register_metric`; out-of-tree **metrics** use the `coding_agent_playbook.metrics` entry-point group (renamed from `…​.evaluators`), out-of-tree **custom grader checks** use the new `coding_agent_playbook.checks` group (in-tree builtins win on a name clash). Never hardcode the list; select metrics via `static_metrics()` / `execution_metrics()` / `all_metrics()` / `get_metric(name)`. Shared per-metric default policy + the `metric_check()` factory live in `evaluators/policy.py`.
- **Non-regression is primary.** The metric-backed checks default to comparing a candidate against a baseline; new scopes fall back to absolute. Deterministic static/execution compare exactly (`max_worsening=0`); judged uses a `threshold` floor + n-sample averaging. Gate boundaries are inclusive on the higher-is-worse side, strict on the higher-is-better side.
- **The rubric criterion is a `JudgeCheck`.** `JudgeCheck` (`evaluators/checks/judged.py`, one per `[rubric]` line, `determinism=JUDGED`, `cost=JUDGED`) is dormant **unless a judge is configured** (`available()` is `False` without `ctx.judge`). As of v1.1 R2 the judge is **live**: `grade` calls `ctx.judge.score_criterion(criterion, artifact, n=…)` — the canonical per-criterion primitive — through the structural `JudgeLike` Protocol in `evaluators/types.py`, so the former `Judge.score` signature debt (SPEC §21.2.3) is **closed**. `evaluators` still never imports `evals` (the protocol breaks the cycle).

### Eval runner invariants (PR R1)

- **Hermetic by default; the real runners are opt-in and never in CI.** `FakeRunner` (`name="fake"`) needs no network/CLI — its `_invoke_agent` applies a deterministic mutation (default a no-op) — and every unit test uses it. The two thin real runners — `ClaudeCodeRunner` (`name="claude_code"`, default `claude -p <prompt>`) and `OpenCodeRunner` (`name="opencode"`, default `opencode run <prompt>`, **PR R3 Track O**) — are each lazy (no top-level CLI import), `available()`-gated on their binary being on `PATH`, and never exercised in CI. All are discovered via the `coding_agent_playbook.runners` entry-point group — never instantiate runners directly.
- **`HarnessRunner` is a template method; `_invoke_agent` is the only hook.** `run_task` owns the fixed pipeline (`materialize` → `render_prompt` → `_invoke_agent` → `capture` → `score`); subclasses implement only `_invoke_agent`. Don't add per-assistant logic anywhere else in the pipeline.
- **Option B result shape.** `TaskResult` carries one `report: EvaluationReport` (+ `passed`/`aggregate_score`/`duration_seconds`/`transcript`); the old `programmatic_checks`/`rubric_scores` and `CheckResult` are retired (a programmatic check is now a BOOL `Finding`). `EvalReport.pass_rate` is the mean of `tr.passed`. This is the sanctioned v2-activation revision of the §15 placeholder — don't resurrect the retired fields.
- **Deterministic-only by default; judged is opt-in via a judge (PR R2).** With no judge configured (`run_task(..., judge=None)`, the default) the `[rubric]` `JudgeCheck`s report `available() is False` and are skipped — the report is the `[expected]` file checks (unified into `rubric_for_task` in R3) + `[metrics]` static/execution non-regression (vs the pristine `setup/` snapshot) only, exactly as R1. With a `Judge` set, the `[rubric]` criteria score against the captured diff and fold into the **same `Rubric.evaluate`** report. There is **no `ProgrammaticOnlyJudge`** — "deterministic-only" is simply the absence of a judge.
- **`render_prompt` is strict for real runners.** A runner with `requires_resolved_prompt=True` (e.g. `ClaudeCodeRunner`) raises `PromptResolutionError` on an unresolvable `prompt_id` — a live agent is never driven with a placeholder; `FakeRunner` leaves it `False` and tolerates the placeholder.
- **No `--run-tests` on `playbook eval`.** Unlike `playbook metrics`, execution intent lives in the eval task's own `[metrics]` block (`run_tests`), not a CLI flag. `playbook eval <id> --run` exits `0` pass / `1` fail / `2` usage-or-runner-unavailable.

### Judge invariants (PR R2)

- **Option A: per-criterion primitive + batch wrapper.** `score_criterion(criterion, artifact, n=1) -> float` is the canonical abstract method; `Judge.score(rubric, transcript, scratch_dir_state)` is a concrete thin wrapper that maps it over the rubric. Subclasses implement only `score_criterion`. Don't resurrect a whole-rubric abstract `score`.
- **Cycle avoidance via the `JudgeLike` Protocol.** The structural protocol `ctx.judge` consumes lives in `evaluators/types.py` (`score_criterion(criterion, artifact, n) -> float`), so `evaluators` never imports `evals`. The concrete `Judge` satisfies it structurally. `EvalContext.judge` is typed `JudgeLike | None`. Never import `evals.judge.Judge` from inside `evaluators`.
- **Judged folds into the same `Rubric.evaluate`.** `JudgeCheck` stays **unregistered** (parameterized per rubric line, id `judge:<slug>`); the task compiler (`evals/_compile.py`, via the `[rubric.bind]` `rubric` group → `Rubric.of`) appends one per criterion to the task's `Rubric`, so its SCORE leaf feeds the gate + composite as an ordinary check entry — no side-channel, no registry lookup. The `passed` gate is `score >= threshold` (the per-criterion floor).
- **`LLMJudge` is opt-in and never in CI.** It shells out to the `claude` CLI (arg-list, no shell, configurable command template with a `{prompt}` token), is `available()`-gated on the binary, lazy/stdlib-only, and registered as `llm` in `coding_agent_playbook.judges`. Its real test is env-gated (`PLAYBOOK_E2E_CLAUDE=1`) + `# pragma: no cover`. `StubJudge` (unregistered) drives every hermetic judged test.
- **`run_task`'s `judge`/`samples` are keyword-only with R1 defaults.** `run_task(task, scratch, *, judge=None, samples=1)` keeps every R1 caller/test working unchanged; the deterministic-only path is byte-identical to R1 when `judge is None`.

### `[expected]` unification + OpenCodeRunner invariants (PR R3)

- **File predicates are real deterministic `Check`s (as of v0.13, gate handles).** The four file checks (`evaluators/checks/files.py`: `FileExistsCheck`/`FileContainsCheck`/`FileUnchangedCheck`/`FileForbiddenCheck`) are authored as `[gate.bind]` `{check="file_exists"|…}` handles (no `[expected]` block since v0.13), compiled by `evals/_compile.py` into the task's `Rubric` and graded through the **same `Rubric.evaluate`**. Each is `required=True`, `weight=0.0`, DETERMINISTIC-cost, with `passed` straight from the predicate over `EvalContext.tree` / `EvalContext.baseline_tree` (`available()` is `False` without a candidate tree).
- **`OpenCodeRunner` mirrors `ClaudeCodeRunner` exactly.** Same template-method shape, same opt-in/lazy/`available()`-gated/never-in-CI discipline, `requires_resolved_prompt=True`, configurable `command`/`timeout`. The only difference is the default CLI (`opencode run <prompt>` with `cwd=scratch_dir`). Don't add per-assistant logic outside `_invoke_agent`.

The original 14-PR engine build-out is **complete** (all rows below are landed):

| PR | Track | What | LoC |
| --- | --- | --- | --- |
| 1 | 1   | Project scaffolding + adapter ABC + source ABCs | ~400 |
| 2 | 1b  | Canonical types (`Rule`/`Prompt`/`Skill`) + markdown round-trip | ~250 |
| 3 | 2a  | Detector module | ~400 |
| 4 | 2b  | Renderer module | ~250 |
| 5 | 2c  | `FileSystemArtifactSource` + `FileSystemStateSource` | ~250 |
| 6 | 3   | Continue adapter | ~300 |
| 7 | 4a  | Claude Code adapter | ~300 |
| 8 | 4b  | AGENTS.md adapter | ~200 |
| 9 | 4c  | OpenCode adapter | ~150 |
| 10 | 5  | CLI (`init`, `sync`, `check`, `validate`, `render`) | ~500 |
| 11 | 5b | Eval Tier 0 (schema + loader + validator + `playbook eval --list/--show/<stub>`) | ~250 |
| 12 | 6  | Pre-commit integration + `.pre-commit-hooks.yaml` | ~150 |
| 13 | 7  | Initial Python rule pack (5 rules + 4 prompts + 8 eval tasks) | ~800 |
| 14 | —  | SPEC.md, README, internal wiki page | — |

**PR H — Agent Harness round-trip support** (implemented; design in `specs/prH-agent-harness.md`):

| Track | What | LoC |
| --- | --- | --- |
| H1 | `harness/` core: `models`, `leaf_detectors`, `parser`, `emitter`, `manifest` (the `.playbook/` sidecar) | ~600 |
| H2 | `agent_harness` output adapter + `pyproject.toml` entry point (opt-in) | ~300 |
| H3 | `playbook import-harness` (lossless via sidecar, best-effort otherwise) | ~300 |
| H4 | `playbook validate-harness` (structural checks, `harnesses-ref`-equivalent) | ~200 |
| H5 | Docs (SPEC §10.7/§12.9/§12.10/§20.10/§20.11, README, this file) | — |

H1 is the shared substrate; H2–H4 depend on it. The harness client *runtime* (`load_content` / `run_script`, the four loading phases) is intentionally out of scope — see SPEC §20.11.

**PR M — Code-quality evaluator subsystem** (implemented; design in `specs/prM-code-metrics.md`). **The original fused `Evaluator`/`grade()` abstraction below was refactored to `Metric`/`Check`/`Rubric` in PR R6** (`evaluators/registry.py`+`grade.py`+`judged.py`+`expected.py` → `evaluators/{metric,check,rubric,scheduler,policy}.py`+`evaluators/checks/`, and `evaluators_for_task` → `rubric_for_task`); the LoC table records the original build:

| Track | What | LoC |
| --- | --- | --- |
| M1 | Evaluator core: `evaluators/{scope,types,parse,registry,grade}.py` + static `builtins/{cyclomatic,wmc,lcom4,dit,cbo}.py` (`@register_evaluator`, gate + composite) — *refactored in R6, see above* | ~750 |
| M2 | `builtins/maintainability.py` (radon-backed `maintainability_index`) + the `[metrics]` optional extra in `pyproject.toml` | ~150 |
| M3 | Standalone static gate: `commands/metrics.py`, CLI wiring, `config.parse_metrics_config` (`[metrics]`), the `playbook-metrics` `repo: local` pre-commit hook | ~350 |
| M4 | Execution evaluators: `evaluators/execution/{project,junit,coverage_xml,test_pass,coverage}.py` + `--run-tests`/`--test-cmd` (shell out to `pytest`; temp `git worktree` baseline) | ~400 |
| M5 | Judged evaluators (`evaluators/judged.py`) + dormant eval wiring (`evals/task.py` `EvalTask.metrics` + `evaluators_for_task`, `evals/validator.py` rule 7) | ~300 |
| M6 | Docs (SPEC §21 + §15 `[metrics]` block, README metrics section, this file) | — |

M1 is the shared substrate; M2–M5 depend on it. Static metrics run by default (fast, air-gapped); execution metrics are opt-in (`--run-tests`) and excluded from the default pre-commit. Judged criteria + eval-output scoring were dormant in PR M and went **live** across v1.1 (runner R1, judge R2, `[expected]` unification R3, the `Metric`/`Check`/`Rubric` refactor R6) — see SPEC §21.6 / §21.2.3.

## Working in this repo

Tooling is `uv` + `ruff` + `mypy` + `pytest`, all configured in `pyproject.toml`. CI (and the local gate) runs `mypy` and `pytest -q` from the repo root with **no path arguments** so they pick up the `[tool.mypy] files` / `[tool.pytest]` config (which includes `tests/`). Use `uv run python -m mypy` and `uv run python -m pytest -q` — the bare `uv run mypy` / `uv run pytest` forms can resolve the wrong interpreter. The canonical pre-commit config is in SPEC §13.2.

Adapters, sources, and overlays register via `[project.entry-points]` — never instantiate them directly.

## Commit policy

**All commits to this repository are authored solely by the user (`msobroza`).** This rule overrides any default tooling behavior and any contradicting guidance in skill files or subagent prompts.

- **Never add `Co-Authored-By:` trailers** — no Claude, no tooling, no other identity. Subagents, harness automations, and dispatched workers must omit them too.
- **Never pass `--author` to `git commit`** unless the user explicitly asks.
- **Never modify `git config user.name` or `user.email`** — use whatever is configured locally. If local config is wrong (e.g. placeholder email like `you@example.com`), surface the issue and ask the user to fix it; do not "help" by changing config yourself.
- **Never sign commits** (no `-S` / `--gpg-sign`) unless the user asks.

If a commit has already been made with a trailer or wrong author by mistake on a pushed branch, **stop and ask before rewriting history** (`git commit --amend`, `git rebase`, force-push). Pre-push local-only branches may be amended after the user consents.

## Subagent / dispatcher policy

When the controller dispatches subagents via the Agent tool to implement plans in this repo:

- **Default model is `opus`** (Claude Opus 4.7, `claude-opus-4-7`) for every role — implementer, spec-compliance reviewer, code-quality reviewer, final reviewer. Cheaper models have produced structural mistakes here (e.g. inserting `__post_init__` between `@classmethod` and the decorated method); opus is the floor, not the ceiling.
- **Every dispatch prompt MUST start with an explicit `cd <worktree-path>`** as the subagent's first tool call. Without this, the Agent tool can inherit the original session's CWD (the main checkout), causing commits to land on `main` instead of the feature branch.
- **Every dispatch prompt MUST forbid `git push` and `gh pr create`** until the user-gate review has approved the diff. The dispatcher (this session) handles push + PR after the gate, not the subagent.
- **Local verification commands MUST match what CI runs.** CI runs `mypy` and `pytest -q` from the repo root with no path arguments — those pick up the `[tool.mypy] files` and `[tool.pytest]` config in `pyproject.toml`, which includes `tests/`. Running `uv run mypy src` (source only) skips test-file checks and lets type errors slip past the local gate. Always run the no-args form locally before claiming a green gate.
