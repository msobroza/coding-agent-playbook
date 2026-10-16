# Migration guide

> **Heads-up:** the **v0.13 task-config redesign** (below) supersedes parts of the
> v0.12 guide. The authored `[expected]`/`[metrics]`/`[rubric]` task TOML that v0.12
> called "unchanged" is **gone** — replaced by the `[gate]`/`[rubric]`/`[verdict]`/
> `[aggregate]` layers — and `higher_is_worse` is replaced by a per-`Metric`
> `Normalizer`. Read the v0.13 section first; the v0.12 section still applies to the
> engine `Metric`/`Check`/`Rubric` API and the entry-point group renames.

## v0.16 — Out-of-tree adapters: override `stale_outputs`, not `cleanup_stale`

`playbook sync --check` now reports orphans (SPEC §12.3), so it must know what
write mode would delete without deleting it. `Adapter.stale_outputs(written_paths,
repo_root) -> list[Path]` is that read-only answer and the **only** override point
for staleness; `Adapter.cleanup_stale` deletes exactly what it returns. Who needs
to act: authors of third-party adapters (the `coding_agent_playbook.adapters`
entry-point group) that override `cleanup_stale`. Rule/prompt/skill authors and
built-in adapter users need nothing.

```python
# before (SPEC §10.1 up to v0.15)
def cleanup_stale(self, written_paths, repo_root):
    return self._default_cleanup(written_paths, repo_root)


# after: report, never delete; the ABC's cleanup_stale deletes what you return
def stale_outputs(self, written_paths, repo_root):
    return self._stale_by_sentinel(written_paths, repo_root)
```

An adapter that still overrides only `cleanup_stale` keeps working in write mode
(`_default_cleanup` is kept, deprecated), but `--check` prints
`warning: adapter '<name>' overrides cleanup_stale() but not stale_outputs()` and
reports no sentinel orphans for it. Scan helpers to reuse: `_stale_by_sentinel`
(the default), `_scan_targets` (each file once, never a symlink or a secret path)
and `_carries_sentinel` (bounded, anchored sentinel check).

## v0.13 — Task config v2 (gate / rubric / verdict / aggregate)

The eval **task config** is redesigned (Tracks C1–C8). The old
`[expected]`/`[metrics]`/`[rubric]` triple is replaced by a **layered**,
expression-composed format; this is a destructive cutover with **no backward
compat**. Authoritative design: `specs/pr2b-task-config.md`.

### TL;DR — who needs to do anything

| You are… | Migration |
|---|---|
| An **eval-task author** (`task.toml`) | **Rewrite** the `[expected]`/`[metrics]`/`[rubric]` blocks into `[gate]`/`[rubric]`/`[verdict]`. See the mapping below. |
| A **`playbook eval --run` user** | **Nothing** (same CLI; `--full-scoring` unchanged). |
| A **`playbook metrics` user** | **Nothing.** The standalone gate + its `[metrics]` engine config in `.coding-agent-playbook.toml` are unchanged. |
| An **out-of-tree `Metric` author** | Add a `normalizer` (`higher_is_worse` is gone). See below. |
| An **out-of-tree check / gate author** | Register under the new `coding_agent_playbook.checks` / `coding_agent_playbook.gates` groups. |

### 1. Block mapping (`[expected]`/`[metrics]`/`[rubric]` → `[gate]`/`[rubric]`)

There is **no `[expected]` block** and **no top-level `[metrics]` task block**.
File predicates and metric thresholds are all `[gate.bind]` *handles* (a handle is
a named entry the `[gate].expr` boolean expression references). Thresholds are now
**0–1 normalized** cutoffs, not raw units.

| Old | New (`[gate.bind]` handle) |
|---|---|
| `[expected] files_created = ["t.py"]` | `made = { check = "file_exists", path = "t.py" }` |
| `[expected] files_must_contain = [{path="t.py", pattern="def test"}]` | `has = { check = "file_contains", path = "t.py", pattern = "def test" }` |
| `[expected] files_unchanged = ["src/a.py"]` | `keep = { check = "file_unchanged", path = "src/a.py" }` |
| `[expected] files_forbidden = ["x/"]` | `nox = { check = "file_forbidden", path = "x/" }` |
| `[metrics.thresholds] cyclomatic_complexity = {fail=20}` | `cc = { check = "threshold", metric = "cyclomatic_complexity", fail = 0.5 }` *(0–1, normalized)* |
| `[metrics.regression] coverage = {max_worsening=0}` | `cov = { check = "non_regression", metric = "coverage", max_worsening = 0.0 }` |

Then compose the handles with a `[gate].expr` and (when omitted on a single-handle
layer) it defaults to that handle's name:

```toml
# OLD
[expected]
files_created = ["tests/test_calc.py"]
files_unchanged = ["src/calc.py"]
[metrics.regression]
coverage = { max_worsening = 0 }
[rubric]
criteria = ["Covers all branches", "No mocking"]
weights  = [0.6, 0.4]

# NEW
[gate]
expr = "made and keep and cov"
[gate.bind]
made = { check = "file_exists",    path = "tests/test_calc.py" }
keep = { check = "file_unchanged", path = "src/calc.py" }
cov  = { check = "non_regression", metric = "coverage", max_worsening = 0.0 }
[rubric]
expr = "quality"
[rubric.bind]
quality = { fail = 0.5, rubric = [
  { judge = "Covers all branches", weight = 0.6 },
  { judge = "No mocking",          weight = 0.4 },
] }
[verdict]
trial = "gate and rubric"   # the default; may be omitted
```

A `[rubric] ref = "name"` (named rubric) becomes a `[rubric.bind]` handle
`{ ref = "name" }`; a `[rubric] criteria/weights` becomes a `{ rubric = [{judge,weight},…] }`
group (weights still sum to 1.0), thresholded to a boolean by `fail`.

### 2. `higher_is_worse` → a per-`Metric` `Normalizer`; thresholds are 0–1

`higher_is_worse` is **deleted**. Every `Metric` now owns a `Normalizer`
(`evaluators/normalizer.py`) mapping its raw value to a **0–1 goodness** where
higher is always better, folding the metric's native direction in:

```python
# before
class MyMetric(Metric):
    higher_is_worse = True  # larger raw = worse


# after
from coding_agent_playbook.evaluators.normalizer import RampNormalizer


class MyMetric(Metric):
    normalizer = RampNormalizer(good=5, bad=20)  # 5 -> 1.0, 20 -> 0.0 (worse-when-larger)
```

Use `RampNormalizer(good, bad)` for an unbounded metric (the same class serves
both directions — pick `good < bad` for worse-when-larger, `good > bad` for
better-when-larger), `PercentNormalizer()` for a 0–100 metric (coverage, MI), or
`Identity()` for one already on 0–1 (test pass rate, judge scores). Because grading
is on the normalized score, **every threshold** (`warn`, `fail`, `max_worsening`)
is now a **0–1 cutoff**, not a raw value: a CC `fail=20` becomes `fail≈0.25`,
coverage `warn=80` becomes `warn=0.8`.

### 3. New entry-point groups: `coding_agent_playbook.checks` / `.gates`

A task `{ check = "<id>", … }` handle resolves through the **checks** registry; a
gate-layer `{ ref = "<name>" }` resolves through the new **gates** registry:

```toml
# pyproject.toml
[project.entry-points."coding_agent_playbook.checks"]
my_check = "my_pkg.checks:MyCheck"          # a Check factory; @register_check("my_check")
[project.entry-points."coding_agent_playbook.gates"]
must_touch_tests = "my_pkg.gates:must_touch_tests"   # a () -> Check factory; @register_gate("must_touch_tests")
```

The `coding_agent_playbook.rubrics` group (named rubrics, `@register_rubric`) is
unchanged. In-tree builtins win on a name clash; the engine ships no builtin
gates or rubrics.

### 4. A judged criterion is a metric (`JudgeMetric`)

You can now run `threshold` / `non_regression` over a **judge criterion**, not just
a registered metric: `{ check = "non_regression", judge = "overall quality", max_worsening = 0.1 }`
adapts the judge as a `JudgeMetric` (0–1, `Identity`-normalized) so the same
regression machinery applies. (The weighted `{ rubric = [...] }` group is the other
judged shape and is unchanged.)

### 5. Cross-trial reliability (`[aggregate]`, optional)

A new optional `[aggregate]` layer grades `pass@k` / `pass^k` across trials; omit
it and a task runs a single trial exactly as before:

```toml
[aggregate]
expr = "reliable"
[aggregate.bind]
reliable = { metric = "pass_at_k", k = 5, over = "verdict", fail = 0.9 }
```

The runner runs `N = max(k)` trials and the aggregate composes them.

### Not changed (v0.13)

- The `playbook metrics` CLI + its `[metrics]` engine config in `.coding-agent-playbook.toml`.
- The metric algorithms (CC/WMC/LCOM4/DIT/CBO≈/MI, `coverage`/`test_pass_rate`) and the non-regression semantics (now on the normalized score).
- The `radon` optional extra, still backing `maintainability_index` only.
- The `coding_agent_playbook.metrics` / `coding_agent_playbook.rubrics` / `coding_agent_playbook.judges` / `coding_agent_playbook.runners` entry-point groups.

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
| `name`, `scope`, `requires`, `needs_project` | **kept, unchanged** |
| `higher_is_worse` | **kept in v0.12; deleted in v0.13** → a `Normalizer` (see the v0.13 section above) |
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
    higher_is_worse = True  # v0.12 only — v0.13 replaces this with a Normalizer

    def measure(self, ctx): ...  # was evaluate(); same body
```

> **v0.13 update:** drop `higher_is_worse` and declare a `normalizer` instead (see
> the v0.13 section, step 2).

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

rubric = Rubric([check1, check2, ...])  # ordered list of Checks
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

### Not changed (in v0.12)

> **Superseded by v0.13:** the authored task TOML *was* byte-identical through
> v0.12, but **v0.13 replaces the `[expected]`/`[metrics]`/`[rubric]` triple with
> the `[gate]`/`[rubric]`/`[verdict]`/`[aggregate]` layers** — see the v0.13
> section above. The points below are v0.12-accurate; the first is no longer true
> as of v0.13.

- ~~The authored `[expected]` / `[metrics]` / `[rubric]` task TOML — byte-identical.~~ (redesigned in v0.13.)
- The `playbook metrics` and `playbook eval` CLI surface (the only addition is
  `playbook eval --run --full-scoring`, which forces every check to run instead
  of short-circuiting once the deterministic gate is lost).
- The metric algorithms (CC/WMC/LCOM4/DIT/CBO≈/MI, `coverage`/`test_pass_rate`),
  their defaults, and the non-regression semantics.
- The `radon` optional extra (`pip install 'coding-agent-playbook[metrics]'`),
  still backing `maintainability_index` only and still lazy.
