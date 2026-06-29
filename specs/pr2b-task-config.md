# PR 2b refined — Task config redesign (gate / rubric / verdict / aggregate)

> **Supersedes** the `[expected]` / `[metrics]` / `[rubric]` task-authoring format
> (the triple the PR-R / PR-R6 docs describe). It builds **on top of** the
> `Metric` / `Check` / `Rubric` engine from `specs/prR6-check-rubric.md` (which is
> unchanged — measure / grade / aggregate); this PR reshapes only the *authored
> task format* and the compile path from TOML → `Rubric`. SPEC §6.5.3, §15, §21
> are the as-built reference; out-of-tree migration is `MIGRATION.md`.

## Goal

Replace the flat `[expected]` / `[metrics]` / `[rubric]` triple with a **layered,
expression-composed** task config that (a) makes the success criteria a small
boolean algebra over named *handles*, (b) normalizes every metric threshold to a
0–1 goodness so direction never leaks into the grader, and (c) adds a cross-trial
reliability layer (`pass@k` / `pass^k`). This is a **destructive cutover** of the
authored format (no backward compat); all 10 in-tree tasks are migrated in the
same change.

## The layered model

A task declares up to four blocks, three of which share one
`[<layer>.bind]` + `[<layer>].expr` shape:

```toml
[setup] / [invocation]                         # unchanged

[gate.bind]                                    # DETERMINISTIC boolean layer
build = { all_of = [ {check="threshold", metric="cyclomatic_complexity", fail=0.5},
                     {check="non_regression", metric="coverage", max_worsening=0.0} ] }
sec   = { ref = "security_gate" }              # a registered composed gate
[gate]
expr  = "build and sec"

[rubric.bind]                                  # LLM-JUDGE weighted layer
quality = { rubric = [ {judge="clear naming", weight=0.4}, {judge="edge cases", weight=0.6} ], fail=0.8 }
no_drop = { check="non_regression", judge="overall quality", max_worsening=0.1 }
review  = { ref = "code_review" }              # a registered named rubric
[rubric]
expr  = "quality and no_drop and review"

[verdict]
trial = "gate and rubric"                      # boolean expr over the two layers; default

[aggregate.bind]                               # OPTIONAL cross-trial reliability; omit ⇒ single trial
reliable = { metric = "pass_at_k", k = 5, over = "verdict", fail = 0.9 }
[aggregate]
expr  = "reliable"
```

### The handle (a `[<layer>.bind]` entry)

A handle is one of six mutually-exclusive shapes (plus the aggregate `metric`
fallback), resolved by `evals/_handles.py::build_handles` (a **Factory** that, for
the boolean groups, recurses as a **Composite**):

| Shape | Builds |
|---|---|
| `{ all_of = […] }` / `{ any_of = […] }` / `{ not = … }` | a `compose.py` `AllOf` / `AnyOf` / `Not` over recursively-built children |
| `{ rubric = [{judge, weight},…], fail = 0.8 }` | a `Rubric.of(...)` (weighted `JudgeCheck`s, weights sum to 1.0) wrapped in a `ThresholdCheck` on its 0–1 composite |
| `{ check = "<id>", …kwargs }` | `get_check(id, **kwargs)` (a registered `Check` factory) |
| `{ ref = "<name>" }` | `get_gate(name)` in the gate layer, else `get_rubric(name)` |
| `{ metric = "pass_at_k"|"pass_pow_k", k, over }` (aggregate fallback) | `get_check(metric, …)` — the aggregate check |

Every handle is a **boolean** `Check`; weights live only *inside* a `rubric`
group. The 0–1 thresholds (`warn` / `fail` / `max_worsening`) are cutoffs on the
normalized score.

### A check = `(type) × (metric | judge) × kwargs`

`check = "threshold" | "non_regression"` over either a registered `metric=` name
(a `Metric`) or a `judge=` criterion (a `JudgeMetric` — an llm-judge criterion
**is a metric**, `Identity`-normalized). Non-regression therefore works on **any**
metric, including judged. The file predicates (`file_exists` / `file_contains` /
`file_unchanged` / `file_forbidden`) are their own check ids. There is **no
`[expected]` block** — file predicates are ordinary gate handles.

### Expressions + the derived verdict

`[<layer>].expr` and `[verdict].trial` are tiny boolean expressions
(`and` / `or` / `not` / parens) over handle names. `evals/_expr.py` is a
self-contained **Interpreter** (tokenizer + recursive-descent parser → small AST →
fold into a `compose.py` tree via `compile_expr`); no `eval`/`exec`/`ast`, no
third-party dep. `evals/_compile.py::compile_task` builds each layer's handle map,
compiles its `expr` into one named layer check (`id="gate"` / `id="rubric"`), and
assembles the present layers into one per-trial `Rubric`.

The **verdict is derived, not re-run**: the per-trial `Rubric` evaluates `gate` and
`rubric` *once*, and `[verdict].trial` is a boolean fold (`eval_bool` /
`verdict_passed`) over their already-decided `passed` results with
**skipped-neutral** semantics (a layer that did not run — e.g. the rubric layer
with no judge — is neutral, like an unavailable `AllOf`/`AnyOf` child). Folding the
verdict from the layer results instead of compiling a third check is what keeps the
judge / test-suite single-shot.

## 0–1 normalization (`Normalizer`)

Every `Metric` owns a `Normalizer` (`evaluators/normalizer.py`) mapping its raw
value to a 0–1 **goodness** where 1.0 is best and **higher is always better**:

- `RampNormalizer(good, bad)` — a linear ramp (`good`→1.0, `bad`→0.0, clamped). One
  direction-free formula serves both a worse-when-larger metric (`good < bad`) and
  a better-when-larger one (`good > bad`).
- `PercentNormalizer()` — the 0–100 → 0–1 case (coverage, MI).
- `Identity()` — already on 0–1 (test pass rate, judge scores).

Folding direction into the normalizer is what let the per-metric `higher_is_worse`
flag be **deleted**: the `Check` grades on the normalized score, so it never
reasons about direction, the gate boundary is uniformly higher-is-better
strict-below, and every threshold is a 0–1 cutoff. (`evaluators/policy.py` carries
the 0–1 per-metric defaults.)

## Cross-trial aggregate (pass@k / pass^k)

`[aggregate]` is the same bind+expr shape over `pass_at_k` / `pass_pow_k` handles
(`k` kwarg, `over ∈ {gate, rubric, verdict}`, 0–1 `warn`/`fail`). The compiler
computes `trials_needed = max(k)`; the runner runs `N = trials_needed` trials,
collects one `TrialResult` each, and the `AggregateCheck` reduces the selected
`over` axis to `(n, c)` and estimates the standard sampling probability
(`PassAtK` = "≥1 success in a random k-subset", `PassPowK` = "all-success
k-subset"). Omit `[aggregate]` ⇒ a single trial, byte-identical to the
non-aggregate path.

## Registries

| Group | Decorator | Resolves | Ships builtins? |
|---|---|---|---|
| `coding_agent_playbook.metrics` | `@register_metric` | a task `metric=` | yes (CC/WMC/LCOM4/DIT/CBO≈/MI + execution) |
| `coding_agent_playbook.checks` | `@register_check` | a task `{check="<id>"}` | yes (threshold/non_regression/file_*/pass_*) |
| `coding_agent_playbook.gates` (new) | `@register_gate("name")` | a gate `{ref="<name>"}` | **no** |
| `coding_agent_playbook.rubrics` | `@register_rubric("name")` | a rubric `{ref="<name>"}` | **no** |

In-tree builtins win on a name clash. Gates/rubrics are pure third-party extension
points.

## The C1–C8 track list

| Track | What | Kind |
|---|---|---|
| C1 | `Normalizer` strategy (`evaluators/normalizer.py`) | additive |
| C2 | Check + Gate registries (`checks/registry.py`, `gates.py`) + `JudgeMetric` adapter | additive |
| C3 | Normalization cutover — `higher_is_worse` → per-metric `Normalizer`, thresholds → 0–1 | isolated, high-risk |
| C4 | Expression Interpreter (`evals/_expr.py`) | additive |
| C5 | Handle builder (`evals/_handles.py`) — Factory + Composite | additive |
| C6 | Task compiler (`evals/_compile.py`) + derived verdict | additive |
| C7 | Parser swap + validator + migrate all 10 authored tasks | destructive cutover |
| C8 | Aggregate layer + multi-trial runner (`checks/aggregate.py`); N=1 default | additive |
| C9 | Docs (this file, SPEC, README, MIGRATION, prR6 pointer, docstring fixes) | docs |

## SOLID / pattern map

- **Strategy** — `Normalizer` (raw→0–1 per metric); `PassAtK` / `PassPowK` (the
  two estimators behind `AggregateCheck`). Direction and reliability-estimation are
  swappable behaviors, not branches in the grader.
- **Interpreter** — `evals/_expr.py` (the `[<layer>].expr` / `[verdict].trial`
  boolean DSL).
- **Factory + Composite** — `evals/_handles.py` (binding → `Check`; boolean groups
  recurse into a `compose.py` tree).
- **Registry** — checks (`coding_agent_playbook.checks`) + gates
  (`coding_agent_playbook.gates`), joining the existing metrics/rubrics groups.
- **Adapter** — `JudgeMetric` (a judge criterion presented as a `Metric` so the
  ordinary threshold/non-regression checks grade it).
- **Template method** — the runner's per-trial pipeline (unchanged), now looped
  `N = max(k)` times for the aggregate layer.

The through-line: the success criteria become a **composable boolean algebra over
checks** (handles + expressions), grading is **direction-free** (normalized 0–1),
and the verdict is a **derived fold** over single-shot layers — so a new check
kind or composition drops in by registration + an expression, with no new grade
path.

## Locked decisions

1. **No `[expected]` block.** File predicates are gate `check`s — one fewer
   special case, one uniform handle algebra.
2. **0–1 normalized thresholds.** Direction lives in the `Normalizer` on the
   `Metric`; `higher_is_worse` is deleted. Every cutoff is a 0–1 goodness.
3. **A judge criterion is a metric.** `JudgeMetric` makes `threshold` /
   `non_regression` work over a `judge=` criterion (incl. non-regression), the
   same machinery as any metric; the weighted `rubric` group is the other shape.
4. **The verdict is derived.** `[verdict].trial` folds the already-run gate/rubric
   results (skipped-neutral); it is never a third check, so the judge / suite runs
   once per trial.
5. **`[aggregate]` is opt-in.** Omit ⇒ a single trial. The runner runs
   `N = max(k)`; `pass@k` / `pass^k` reduce the `over` axis. `max_worsening` vs
   baseline trials is accepted by the validator but not yet executed.
6. **Destructive cutover.** No compat shim for the old triple; all 10 in-tree
   tasks migrated in C7. The only stability guarantee is the new layered format.

## Gate

Lands green under the full cache-free, no-optional-extras CI-parity gate
(`rm -rf .mypy_cache && ruff check . && ruff format --check . && mypy && pytest -q`,
no path args).
