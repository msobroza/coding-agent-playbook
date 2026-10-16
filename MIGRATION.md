# Migration guide

## v0.19 — Bundled content moves to `content/`; packs become bundled plugins

The engine's own rules, prompts, eval tasks and skills move out of the Python
package into a top-level `content/` tree, and the opt-in **packs** are renamed
**bundled plugins**. Rendered output is unchanged, and old names keep working
with a warning. Authoritative design: `specs/prC-content-extraction.md`.

### TL;DR — who needs to do anything

| You are… | Migration |
|---|---|
| A **consumer** with `coding_agent_playbook.packs.<name>` in `overlays_enabled` | **Nothing breaks.** Rename it to `coding_agent_playbook.plugins.<name>` when convenient to silence the warning (below). |
| A **consumer** without bundled plugins | **Nothing.** |
| Code that imports **`coding_agent_playbook.packs`** or **`PACK_NAME`** | Use the dotted string instead (no shim). |
| An **overlay author** (`<pkg>/resources/…`) | **Nothing.** The overlay contract is unchanged. |
| An **engine content contributor** | Edit under `content/` instead of `src/coding_agent_playbook/resources/` or `packs/<name>/resources/`. See `content/README.md`. |
| A **script that parses `playbook eval --show`** | The bundled `Source:` label lost its `resources/` segment (below). |

### 1. `packs` → bundled plugins, and the deprecated alias

| Old | New |
|---|---|
| `coding_agent_playbook.packs.superpowers` | `coding_agent_playbook.plugins.superpowers` |
| `coding_agent_playbook.packs.python_design` | `coding_agent_playbook.plugins.python_design` |
| `src/coding_agent_playbook/resources/…` | `content/core/…` |
| `src/coding_agent_playbook/packs/<name>/resources/skills/…` | `content/plugins/<name>/skills/…` |
| `src/coding_agent_playbook/packs/<name>/{LICENSE,ATTRIBUTIONS.md}` | `content/plugins/<name>/{LICENSE,ATTRIBUTIONS.md}` (plus a new `README.md`) |
| `src/coding_agent_playbook/resources/precommit/config.yaml.j2` | `src/coding_agent_playbook/templates/precommit/config.yaml.j2` |

```toml
# .coding-agent-playbook.toml — before
overlays_enabled = ["coding_agent_playbook.packs.superpowers"]

# after
overlays_enabled = ["coding_agent_playbook.plugins.superpowers"]
```

- **The old spelling is a deprecated alias.** `coding_agent_playbook.packs.<name>`
  is rewritten to `coding_agent_playbook.plugins.<name>` when the config loads, so
  it renders exactly as before and causes no `sync --check` drift (the lockfile
  stores only paths and hashes). Diagnostics (`check`, `render`, `eval` labels,
  collisions) print the new name.
- **The alias stays through 0.x.** Its removal will be announced in this file one
  release ahead.
- **Nothing rewrites the committed file for you.** A deprecated name stays in
  `.coding-agent-playbook.toml` until you re-run `playbook init` with
  `--overlays …` (it writes the new names, on a first run and on a re-run) or edit
  the file. `sync` never rewrites the config, and `check --refresh` writes the
  name back as it was parsed. `.coding-agent-playbook.local.toml` is never
  rewritten by any command: edit it by hand.
- **Bundled plugins are pure content.** A plugin is just the directory
  `content/plugins/<name>/`, with no Python file. Both namespaces,
  `coding_agent_playbook.plugins.*` and `coding_agent_playbook.packs.*`, are
  reserved for bundled plugins.

### 2. The new warning lines

Every command that loads the config (`sync`, `check`, `validate`, `render`,
`eval`, and `init`'s final sync) prints exactly one stderr line per deprecated
name. `<file>` is `.coding-agent-playbook.local.toml` when that file sets
`overlays_enabled`, else `.coding-agent-playbook.toml`:

```text
warning: <file>: overlays_enabled: '<old>' is deprecated; use '<new>'
warning: .coding-agent-playbook.toml: overlays_enabled: 'coding_agent_playbook.packs.superpowers' is deprecated; use 'coding_agent_playbook.plugins.superpowers'
```

`playbook init --overlays coding_agent_playbook.packs.<name>` accepts the old
name, writes the new one, and prints once per deprecated argument, after its
overlay check passes:

```text
warning: --overlays: '<old>' is deprecated; use '<new>'
```

These are plain `warning:` lines on stderr, not a Python `DeprecationWarning`,
and the exit code is unchanged.

### 3. Removed with no shim: `coding_agent_playbook.packs` and `PACK_NAME`

The `coding_agent_playbook.packs` package, its `coding_agent_playbook.packs.<name>`
subpackages and their `PACK_NAME` constants are deleted. There is no import shim,
because a bundled plugin no longer has any Python module. Use the dotted string
instead:

```python
# before
# from coding_agent_playbook.packs.superpowers import PACK_NAME

# after
PLUGIN_NAME = "coding_agent_playbook.plugins.superpowers"
```

### 4. New preflight reasons and hint

A bundled-plugin name in `overlays_enabled` is now checked against
`content/plugins/<name>/` and never imported. `sync`, `validate`, `check` and
`init` report it with new texts:

| Entry | Before | Now |
|---|---|---|
| Unknown plugin, e.g. `coding_agent_playbook.plugins.superpower` | `not importable` | `no such bundled plugin` |
| The bare namespace `coding_agent_playbook.plugins` or `coding_agent_playbook.packs` | `importable, but ships no resources/ directory, …` (for `…packs`) | `the bundled plugin namespace, not a plugin` |
| Hint for a plugin-like typo | ` (bundled packs: …)` | ` (bundled plugins: <comma-separated sorted dotted names>)` |

```text
coding_agent_playbook.plugins.superpower: no such bundled plugin (bundled plugins: coding_agent_playbook.plugins.python_design, coding_agent_playbook.plugins.superpowers)
```

In `overlays_enabled`, a typo under the old namespace prints the deprecation
warning (recommending the new spelling) and then this error for the new
spelling. `init --overlays` warns only after its check passes, so it reports
such a typo under the new spelling alone. Overlay packages keep their reasons
(`not importable`, with the import error when there is one, or no `resources/`
directory).

The refusal headers now call each entry an overlay package or bundled plugin:

| Command | Before | Now |
|---|---|---|
| `sync` | `error: overlay package(s) in overlays_enabled are not usable here:` | `error: overlay package(s) or bundled plugin(s) in overlays_enabled are not usable here:` |
| `init` | `error: --overlays names package(s) that cannot be used as overlays here; nothing was written:` | `error: --overlays names overlay package(s) or bundled plugin(s) that cannot be used here; nothing was written:` |

### 5. The bundled `eval --show` label

The `Source:` line of `playbook eval --show` is built from the task's layer:

| Layer | Before | Now |
|---|---|---|
| Engine and bundled plugins | `coding_agent_playbook/resources/eval_tasks/<dir>/` | `<source_package>/eval_tasks/<dir>/`, e.g. `coding_agent_playbook/eval_tasks/<dir>/` |
| Third-party overlay | `<pkg>/resources/eval_tasks/<dir>/` | unchanged |
| Repo-local | `playbook/eval_tasks/<dir>/` | unchanged |

`<dir>` is the task directory's name, never the task id. Related fix: a
repo-local task under `playbook/eval_tasks/` now finds its prompt in
`playbook/prompts/` (it never found one before).

Caveat: when `playbook eval` renders a repo-local prompt, its
`{{ rule("<id>") }}` includes resolve only the engine's rules and the task's own
`setup/playbook/rules/`. A repo-local prompt that includes a rule from your
`playbook/rules/` or from an overlay renders that rule as empty text during
`playbook eval`, while `playbook sync` writes the full body. Widening that scope
is a follow-up.

### 6. A broken install fails loudly

If the engine's bundled content cannot be found, every command that loads it
(`init`, `sync`, `check`, `validate`, `render`, `eval`) now exits 2 with:

```text
error: the engine's bundled content was not found (looked in <a>, <b>); reinstall coding-agent-playbook
```

`--version`, `metrics`, `validate-harness` and `import-harness` never look for
the content, so they still run. Before, a lookup miss silently rendered zero
engine artifacts. If you build the engine yourself, build releases from the
sdist (`uv build` or `python -m build`), never with `--wheel`: the wheel copies
`content/` in with a force-include that ignores `.gitignore`.

### Not changed (v0.19)

- The third-party overlay contract: `<pkg>/resources/{rules,prompts,skills,eval_tasks}`
  and the entry-point groups.
- Rendered output, the lockfile format and the generated file set, for both the
  old and the new plugin names.
- `pip install coding-agent-playbook`: still one wheel, with the content inside.

> **Heads-up:** the **v0.13 task-config redesign** (below) supersedes parts of the
> v0.12 guide. The authored `[expected]`/`[metrics]`/`[rubric]` task TOML that v0.12
> called "unchanged" is **gone** — replaced by the `[gate]`/`[rubric]`/`[verdict]`/
> `[aggregate]` layers — and `higher_is_worse` is replaced by a per-`Metric`
> `Normalizer`. Read the v0.13 section first; the v0.12 section still applies to the
> engine `Metric`/`Check`/`Rubric` API and the entry-point group renames.

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
