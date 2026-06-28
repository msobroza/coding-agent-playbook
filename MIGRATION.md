# Migration guide

## v0.12 — `Evaluator` → `Metric` / `Check` / `Rubric` (PR R6)

The code-quality evaluator subsystem (SPEC §21) was refactored from one fused
`Evaluator` ABC + a free `grade()` function into **three single-responsibility
abstractions**: `Metric` (measure) → `Check` (grade) → `Rubric` (aggregate).
Authoritative design: `specs/prR6-check-rubric.md`.

### TL;DR — who needs to do anything

| You are… | Migration |
|---|---|
| An **eval-task author** (writing `task.toml` with `[expected]`/`[metrics]`/`[rubric]`) | **Nothing.** The authored TOML is unchanged. |
| A **`playbook metrics` / `playbook eval --run` user** | **Nothing.** Same commands, same flags (plus the new `--full-scoring` on `eval --run`). |
| An **out-of-tree extender** registering a custom evaluator | **Port it** — see below. |

The only breaking change is for **out-of-tree packages** that registered a custom
`Evaluator` or called the engine's evaluator API directly. The authored task
format and the CLI are unchanged.

### 1. `Evaluator` subclass → `Metric` subclass

Drop the grading-side and value-shape fields; keep (and rename) the measurement:

| Old `Evaluator` | New `Metric` |
|---|---|
| `class MyMetric(Evaluator)` | `class MyMetric(Metric)` |
| `evaluate(self, ctx) -> list[Measurement]` | **`measure(self, ctx) -> list[Measurement]`** (renamed; same body) |
| `value_kind = ValueKind.NUMERIC` | **deleted** — a metric is always a raw measurement |
| `to_score(self, value, policy)` | **deleted** — normalization is the `Check`'s job |
| `default_absolute` / `default_regression` / `default_weight` | **deleted** — grading policy lives on the `Check`, not the metric |
| `name`, `scope`, `higher_is_worse`, `requires`, `needs_project` | **kept, unchanged** |
| `available(self, ctx)` | **kept** (default still gates on deps + the needed ctx slot) |

```python
# before
from coding_agent_playbook.evaluators.registry import Evaluator, register_evaluator
from coding_agent_playbook.evaluators.scope import Scope, ValueKind, Determinism

@register_evaluator
class MyMetric(Evaluator):
    name = "my_metric"
    scope = Scope.FUNCTION
    value_kind = ValueKind.NUMERIC
    determinism = Determinism.DETERMINISTIC
    higher_is_worse = True
    default_absolute = AbsoluteThreshold(warn=10, fail=20)
    default_regression = RegressionPolicy(max_worsening=0)
    def evaluate(self, ctx): ...
    def to_score(self, value, policy): ...

# after
from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.scope import Scope

@register_metric
class MyMetric(Metric):
    name = "my_metric"
    scope = Scope.FUNCTION
    higher_is_worse = True            # the only direction field; the Check reads it
    def measure(self, ctx): ...        # was evaluate(); same body
```

The default warn/fail bounds and regression tolerance that used to live on the
metric now live in `evaluators/policy.py::METRIC_DEFAULTS` (for the builtins) and,
for your metric, are supplied by whoever builds the `Check` — a `[metrics]`
config override or a `ThresholdCheck(...)` you construct.

### 2. Entry-point group rename: `…​.evaluators` → `…​.metrics`

```toml
# pyproject.toml — before
[project.entry-points."coding_agent_playbook.evaluators"]
my_metric = "my_pkg.metrics:MyMetric"

# after
[project.entry-points."coding_agent_playbook.metrics"]
my_metric = "my_pkg.metrics:MyMetric"
```

In-tree builtins still win on a name clash.

### 3. Custom graders register under the new `coding_agent_playbook.checks`

A custom *grading strategy* (beyond the built-in threshold / non-regression /
file / judge checks) is now a `Check`, registered under the **new**
`coding_agent_playbook.checks` entry-point group:

```toml
[project.entry-points."coding_agent_playbook.checks"]
my_check = "my_pkg.checks:MyCheck"
```

A `Check` implements `grade(self, ctx, measurements) -> CheckResult` and sets
`id`, `weight`, `required`, `determinism`, and `cost: CostTier`. See
`evaluators/check.py` (`ThresholdCheck`/`NonRegressionCheck`) and
`evaluators/checks/` (file/judge/compose) for the built-in shapes.

### 4. `grade()` → `Rubric.evaluate`

If you called the engine's grading function directly, build a `Rubric` and call
`evaluate` instead. The `extra_evaluators` side-channel is gone — every check
(metric-backed, file, judged, composed) is just an entry in the rubric's ordered
check list:

```python
# before
from coding_agent_playbook.evaluators.grade import grade
report = grade(candidate, baseline, policy, extra_evaluators={name: inst})

# after
from coding_agent_playbook.evaluators.rubric import Rubric
from coding_agent_playbook.evaluators.check import MeasurementSet
rubric = Rubric([check1, check2, ...])              # ordered list of Checks
report = rubric.evaluate(ctx, MeasurementSet(candidate, baseline))
```

Both return an `EvaluationReport` (`passed`, `composite`, `findings`, `checks`).
To build the metric-backed checks for a `[metrics]`-style config, reuse the
shared factory `evaluators/policy.py::metric_check(name, config)` (the same one
`playbook metrics` and `rubric_for_task` use), so your gate honours identical
per-metric policy.

### 5. Deleted symbols (no compatibility shim)

`Evaluator`, `evaluators/registry.py`, `evaluators/grade.py` (`grade()`),
`evaluators/expected.py`, `evaluators/judged.py` (`JudgedCriterion`),
`ValueKind`, `to_score`, the `default_absolute`/`default_regression`/`default_weight`
fields, and `evals/task.py::evaluators_for_task` are **removed**. Their
replacements: the file checks live in `evaluators/checks/files.py`, the judged
check in `evaluators/checks/judged.py` (`JudgeCheck`), and the task compiler is
`evals/task.py::rubric_for_task` (returns a `Rubric`).

### Not changed

- The authored `[expected]` / `[metrics]` / `[rubric]` task TOML — byte-identical.
- The `playbook metrics` and `playbook eval` CLI surface (the only addition is
  `playbook eval --run --full-scoring`, which forces every check to run instead
  of short-circuiting once the deterministic gate is lost).
- The metric algorithms (CC/WMC/LCOM4/DIT/CBO≈/MI, `coverage`/`test_pass_rate`),
  their defaults, and the non-regression semantics.
- The `radon` optional extra (`pip install 'coding-agent-playbook[metrics]'`),
  still backing `maintainability_index` only and still lazy.
