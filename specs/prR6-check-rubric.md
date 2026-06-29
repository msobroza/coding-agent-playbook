# PR R6 — `Metric` / `Check` / `Rubric`: split the fused `Evaluator` (clean-slate refactor)

> **Supersedes** the `Evaluator` + free `grade()` design in `specs/prM-code-metrics.md` (and the eval-scoring shape in `specs/prR-eval-runner.md` / `specs/prR2-judge-r3-opencode.md`) for the **abstraction**. The PR-M/PR-R metric algorithms, family taxonomy, non-regression semantics, and the eval `[metrics]`/`[rubric]`/`[expected]` task schema are unchanged — only the engine abstraction (and the out-of-tree extension surface) is refactored. SPEC §21 is the as-built reference.
>
> **Superseded for the task format by `specs/pr2b-task-config.md`** (the "2b refined" redesign, Tracks C1–C8): the `[expected]`/`[metrics]`/`[rubric]` triple this doc preserved is replaced by the layered `[gate]`/`[rubric]`/`[verdict]`/`[aggregate]` model, `higher_is_worse` by a per-`Metric` `Normalizer`, and `rubric_for_task` by the `evals/_compile.py` task compiler. The `Metric`/`Check`/`Rubric` engine below is unchanged and reused underneath.
>
> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development; checkbox steps.
>
> **Commit policy (overrides any tooling default):** commits authored **solely by `msobroza`** — no `Co-Authored-By`, no `--author`, no signing. Subagents `cd` first, default `opus`, **no push/PR until the user gate**. Run the **full cache-free, no-optional-extras CI-parity gate** (`uv pip uninstall radon -y; rm -rf .mypy_cache; ruff check . && ruff format --check . && mypy && pytest -q`, no path args) before claiming green — see [[ci-parity-gate-pitfalls]].

## Goal

Replace the single fused `Evaluator` ABC + the free `grade()` function with **three single-responsibility abstractions** — `Metric` (measure), `Check` (grade), `Rubric` (aggregate) — plus a cost-tiered short-circuit `scheduler`. This is a **clean-slate** refactor: the old symbols are deleted outright (no compatibility shim), the consumers are cut over in the same PR, and the authored task TOML is left **byte-for-byte unchanged** so there is zero authoring migration. The framing realizes Anthropic's *"Demystifying Evals for AI Agents"* model — a **Check ≈ a grader's pass/fail assertion** (deterministic or LLM-as-judge), a **Rubric = a weighting of checks**, and **a metric becomes a check via a threshold**.

## Why — the 5 SOLID smells in the fused `Evaluator`

The PR-M `Evaluator` fused *measuring*, *grading*, and *aggregating* into one class + one free function. Five concrete smells fell out:

1. **`extra_evaluators` side-channel (SRP/OCP).** `grade()` graded the *registered* measured metrics, but `[expected]` BOOL checks and judged `[rubric]` criteria were un-registered parameterized instances, so they had to be smuggled in through a `grade(..., extra_evaluators={name: instance})` map — a second, parallel path that every consumer had to thread. Adding a new check kind meant touching `grade()`'s signature and every caller.
2. **The weight-0 / fail-floor `[expected]` hack (LSP).** A file check is a *boolean predicate*, but to ride the numeric `grade()` it was forced into the `Evaluator` shape: `value_kind=BOOL`, `weight=0` (so it never feeds the composite) and a hand-set `fail` floor of `1.0` (so `0.0` gates). A predicate masquerading as a graded measurement — it doesn't substitute cleanly for a real metric.
3. **The `value_kind` + `to_score` + threshold triple-encoding (SRP).** Whether a value was a raw NUMERIC, an already-0–1 SCORE, or a 0|1 BOOL was encoded *three* times: the `value_kind` enum, the `to_score()` normalization branch, and the threshold bounds. They had to be kept consistent by hand; a SCORE evaluator with the wrong `to_score` branch silently mis-scored.
4. **Smeared rubric weights (SRP/cohesion).** A "rubric" was not an object — it was a *convention*: a set of weights smeared across the per-evaluator `default_weight` fields + the `[metrics].weights` config + the composite loop inside `grade()`. There was no `Rubric` you could construct, nest, or test in isolation; the weighting logic lived in three places.
5. **`higher_is_worse` control-coupling (SRP).** `grade()` branched on each evaluator's `higher_is_worse` to pick the regression direction, the absolute-bound inclusivity, *and* the `to_score` ramp direction — one boolean steering three unrelated decisions deep inside the free function, so the grading policy could not move off the measurement.

The through-line: **measuring, grading, and aggregating are three responsibilities**, and the fused class made every new requirement (a new check kind, a composable rubric, a cost-tiered scheduler) a change to the shared `grade()` and every caller.

## The model — `Metric` → `Check` → `Rubric`

Three abstractions, each one responsibility, in `src/coding_agent_playbook/evaluators/`:

### `Metric` (measure) — `metric.py`
`measure(ctx) -> list[Measurement]`; fields `name`, `scope`, `higher_is_worse`, `requires`, `needs_project`. It carries **only the measurement-side descriptors** — the grading-side policy (thresholds, regression tolerance, weight) is gone from here. Registry: `@register_metric` decorator + the **`coding_agent_playbook.metrics`** entry-point group (renamed from `…​.evaluators`); selection helpers `all_metrics()` / `static_metrics()` / `execution_metrics()` / `get_metric()`. Builtins: CC / WMC / LCOM4 / DIT / CBO / `maintainability_index` (radon, lazy) + execution `coverage` / `test_pass_rate`.

### `Check` (grade) — `check.py` + `checks/`
`grade(ctx, measurements) -> CheckResult`. A `CheckResult` is a **boolean `passed` gate + a `score: float | None` partial-credit + `subresults`/`status`**; fields `id`, `weight`, `required`, `determinism`, `cost: CostTier`. The check carries the grading policy that used to live on the metric. Subtypes:
- **`ThresholdCheck` / `NonRegressionCheck`** (`check.py`) — metric + absolute warn/fail and/or regression tolerance. `cost` is derived from `metric.needs_project` (EXECUTION vs DETERMINISTIC). The per-scope decision (`_to_score`/`_decide`/`_absolute_level`/`_regressed`) is the canonical deterministic grading logic — the single home for the boundary rules (inclusive on the higher-is-worse side, strict on the higher-is-better side).
- **`FileExistsCheck` / `FileContainsCheck` / `FileUnchangedCheck` / `FileForbiddenCheck`** (`checks/files.py`) — the four `[expected]` predicates as real checks: `passed` comes straight from the predicate over `ctx.tree` (and `ctx.baseline_tree` for unchanged). No more weight-0/fail-floor hack — a predicate is just a check whose `passed` is the predicate.
- **`JudgeCheck`** (`checks/judged.py`) — one rubric criterion, LLM-as-judge: `grade` calls `ctx.judge.score_criterion(criterion, ctx.artifact, n=ctx.samples)` (the structural `JudgeLike` protocol, so `evaluators` never imports `evals`), `passed = score >= threshold`. JUDGED-cost so the scheduler runs it last; dormant without a judge.
- **`TestsPassCheck` / `CoverageCheck`** (`checks/execution.py`) — thin `ThresholdCheck` factories bound to the execution metrics with conventional default bounds.
- **`AllOf` / `AnyOf` / `Not`** (`checks/compose.py`) — boolean composers that are themselves checks, folding children through the scheduler (an unavailable child is *neutral*).

Registry for out-of-tree grader checks: the new **`coding_agent_playbook.checks`** entry-point group.

### `Rubric` (aggregate) — `rubric.py`
A weighted set of checks; `evaluate(ctx, measurements, *, strict, fail_fast, max_workers) -> EvaluationReport`. **Gate** = all `required` checks pass (+ under `strict`, no required check carries a `warn` leaf); **composite** = `Σ(weight·score)/Σweight` over run checks with `weight > 0`. This **replaces `grade()`** — the rubric *is* the aggregator, an object you construct, nest, and test in isolation (smell 4 closed). The old `extra_evaluators` side-channel is gone: every check (metric-backed, file, judged, composed) is just an entry in the rubric's ordered check list (smell 1 closed).

### Composite — a `Rubric` is also a `Metric`
`Rubric` subclasses `Metric` and exposes its composite as one MODULE-scope `Measurement` via `measure()`. So a rubric **thresholds into a `ThresholdCheck`** and **nests** into a parent rubric — a composable check/rubric algebra. `measure()` self-builds its `MeasurementSet` from the additive `EvalContext.candidate_measurements`/`baseline_measurements`, guards a re-entrant self-measure (`ValueError`), and memoizes per `ctx`.

### Scheduler — `scheduler.py`
Cost-tiered (`CostTier` DETERMINISTIC < EXECUTION < JUDGED) short-circuit evaluation with optional within-tier `concurrent.futures` concurrency. Runs checks **cheapest-tier-first**, results always in **authored order**. `op="and"` short-circuits on the first required failure (so **a failing deterministic check never invokes the LLM judge**); `op="or"` on the first pass. The runner is **fail-fast by default**; `playbook eval --run --full-scoring` forces every check to run. The composers reuse the same `schedule()` Strategy.

### Named-rubric registry — `rubrics.py` (+ `Rubric.of`/`define`/`CRITERIA`)
A code-defined rubric can be **shared across tasks by name**, bridging a Python `Rubric` subclass and the TOML authoring surface. Three additive pieces:

- **`Rubric.of(*pairs, name=…, threshold=0.5, normalize=True)`** and **`Rubric.define(**kw)`** (classmethods on `Rubric`). `of` builds a `Rubric` of non-gating `JudgeCheck`s from `(criterion, weight)` pairs, normalizing the weights to sum `1.0` by default (parity with the `[rubric].weights` rule; the all-zero case is left untouched). `define()` is `cls.of(*cls.CRITERIA, name=cls.__name__, **kw)` — it builds the subclass from its class-level `CRITERIA: tuple[tuple[str, float], …]`.
- **`evaluators/rubrics.py`** — the registry, mirroring `metric.py`: the `coding_agent_playbook.rubrics` entry-point group, `@register_rubric("name")` (a decorator **factory** keyed on an explicit string, since a rubric has no intrinsic `cls.name`), `get_rubric(name) -> Rubric` (resolves the class — in-tree registrations before entry points — and returns `cls.define()`; raises `KeyError` if unknown), and `all_rubric_names()` for validator messages. The engine ships **no** builtin rubrics — this is purely the out-of-tree extension point.
- **TOML `ref`** — `evals/task.py`'s authoring `Rubric` gains `ref: str | None`. `ref` and `criteria` are mutually exclusive (both set / neither set → `ValueError` at parse, mirrored in the validator); when `ref` is set, `criteria`/`weights` stay empty and the weight-sum check is skipped. `rubric_for_task` resolves `get_rubric(task.rubric.ref)` and **splices its `JudgeCheck`s in alongside** the `[expected]`/`[metrics]` checks (so a task carries `ref` + `[expected]` + `[metrics]` together); the task `Rubric`'s `name` stays `task.id`. The validator adds rule 8: an unknown `ref` errors with the known-rubric list.

### Where the smells land
| smell | fixed by |
|---|---|
| 1 — `extra_evaluators` side-channel | every check is a `Rubric` list entry; no second path |
| 2 — weight-0/fail-floor `[expected]` hack | file checks are real `Check`s; `passed` = predicate |
| 3 — `value_kind` + `to_score` + threshold triple-encoding | a `Metric` measures; a `Check` grades; no `value_kind`/`to_score` |
| 4 — smeared rubric weights | `Rubric` is an object; weighting lives in one `evaluate()` |
| 5 — `higher_is_worse` control-coupling | direction lives on the `Metric`; the check reads it in one place |

## Consumers (cut over in the same PR)

- **`evals/scoring.py::score()`** builds a `Rubric` via **`evals/task.py::rubric_for_task`** (compiling `[metrics]` → metric-backed checks, `[rubric]` → `JudgeCheck`s, `[expected]` → file checks into one ordered list), pre-measures the referenced metrics over the candidate (vs the pristine `setup/` snapshot), and runs `Rubric.evaluate`. `score(...)` gains a `fail_fast` arg (the runner default; `--full-scoring` flips it off).
- **`commands/metrics.py`** builds a standalone `Rubric` (one metric-backed check per gated metric) and grades the pre-built measurements through `Rubric.evaluate(..., fail_fast=False)` — the complete report.
- **Shared metric-default policy** lives in **`evaluators/policy.py`** (`METRIC_DEFAULTS` + the `metric_check()` factory) so both consumers grade with identical per-metric policy and never drift.

## Locked decisions

1. **Name = `Check`** (not `Grader`/`Assertion`). Matches the Anthropic eval framing (a grader's pass/fail assertion) and reads naturally for `AllOf(FileExistsCheck(...), ...)`.
2. **Hybrid scoring on `CheckResult`** — a boolean `passed` gate **plus** an optional `score: float | None` partial-credit. The gate is what `required` checks vote on; the score is what the weighted composite averages. A pure predicate sets `score` from `passed`; a metric ramps it.
3. **Clean-slate, no shim.** The `Evaluator` ABC, `grade.py`, `expected.py`, `judged.py`, `ValueKind`, and `evaluators_for_task` are **deleted**, and the consumers are cut over in the same PR. No deprecation alias — the only public stability guarantee is the authored task TOML.
4. **Entry-point groups renamed/split.** Out-of-tree metrics: `coding_agent_playbook.metrics` (was `…​.evaluators`). Out-of-tree custom grader checks: the new `coding_agent_playbook.checks`. In-tree builtins win on a name clash.
5. **Authored task TOML unchanged.** `[expected]`/`[metrics]`/`[rubric]` parse + validate identically; the validator's rule 7 still checks metric names against `all_metrics()`. Zero migration for task authors.

## What was deleted

`evaluators/registry.py` (the `Evaluator` ABC + `@register_evaluator` + `all/static/deterministic_evaluators`/`get_evaluator`), `evaluators/grade.py` (the free `grade()` + `resolve_policy`), `evaluators/expected.py` (the BOOL file `Evaluator`s — re-homed as real checks in `checks/files.py`), `evaluators/judged.py` (`JudgedCriterion` — re-homed as `checks/judged.py::JudgeCheck`), the `ValueKind` enum, and `evals/task.py::evaluators_for_task` (replaced by `rubric_for_task`). The `coding_agent_playbook.evaluators` entry-point group is renamed to `coding_agent_playbook.metrics`.

## Gate

Docs/refactor land green under the full cache-free, no-optional-extras CI-parity gate (`rm -rf .mypy_cache && ruff check . && ruff format --check . && mypy && pytest -q`, no path args). The authored eval tasks score identically before/after (golden parity).
