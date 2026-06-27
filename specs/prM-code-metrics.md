# PR M — code-quality evaluators: static metrics + execution (tests/coverage) + non-regression gate (unified `Evaluator` registry)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
>
> **Commit policy (overrides any tooling default):** every commit is authored **solely by `msobroza`** — **never** add a `Co-Authored-By:` trailer, never pass `--author`, never sign. Subagents/dispatchers obey this too. **No `git push` / `gh pr create` until the user gate approves the diff.** Every dispatch prompt MUST start with `cd <worktree-path>` as its first tool call, and default to the `opus` model for every role. (Local git identity is repo-scoped to `msobroza`; verify `git config user.email` before committing.)

## Core idea — one abstraction: `Evaluator`

A **rubric criterion, a code metric, a coverage number, and a test-pass rate are all the same thing** — a *graded measurement over a scope*, differing only in **who produces the value**, the **value kind** (number / score / bool), and **how it's used** (a hard gate vs a weighted score). This PR introduces one `Evaluator` abstraction with **three producer families**:

| Authoring | Evaluator family | value kind | producer (`determinism` / needs) | primary use |
| --- | --- | --- | --- | --- |
| `[metrics]` CC, WMC, MI, LCOM4, DIT, CBO≈ | **static** | NUMERIC | DETERMINISTIC · needs source/AST (ast/radon) | threshold + **non-regression** |
| `[metrics]` `test_pass_rate`, `coverage` | **execution** | SCORE / NUMERIC | DETERMINISTIC · needs a **runnable project** (shells out to `pytest`) | threshold + **non-regression** |
| `[rubric]` criteria + weights | **judged** | SCORE 0–1 | JUDGED · needs a **judge** (LLM/human) | weighted composite + non-regression (tolerance) |
| `[expected]` file checks | static (bool) | BOOL | DETERMINISTIC · needs source/files | must-be-true gate |

Every evaluator yields a **raw value per scope** (feeds the threshold + non-regression *gate*) **and** a normalized **`to_score()` 0–1** (feeds the weighted *composite*). One registry, one `grade()`/aggregate, one non-regression comparator — for static metrics, execution metrics, and judged criteria alike. Readable `[expected]`/`[metrics]`/`[rubric]` blocks stay (backward-compatible) and **compile to `Evaluator` instances**. Each evaluator declares what it **needs** (`available(ctx)`); the runner provides only what it can, so evaluators degrade gracefully.

**Goal (v1 shippable):** the `Evaluator` registry + static metric evaluators + the **execution evaluators** (`test_pass_rate`, `coverage`) + a standalone `playbook metrics` command/pre-commit hook. Static metrics run by default (fast, air-gapped); execution evaluators are **opt-in** (`--run-tests`, they invoke the test suite) and are **not** in the default pre-commit hook. **Reserved for v1.1:** judged evaluators (the rubric, generalized) + executing the eval `[metrics]`/`[rubric]` blocks against agent output (static **and** execution: "did the agent's tests pass and coverage not drop?") — wired to the *same* registry when `HarnessRunner`/`Judge` land.

**Why this static set (verified):** radon/lizard natively compute only **CC**; radon adds **MI**; **`cohesion` is not LCOM4** (GPLv3, avoid as a dep); **CBO/RFC/DIT have no dep-light Python lib**. High-signal static set: **CC, WMC, MI, LCOM4** + soft **DIT, CBO≈**. Excluded: **RFC, NOC, Abstractness, Distance, LCOM1/2, standalone Halstead**. Engine stays stdlib-only; **radon is an optional extra** (MI); execution evaluators add **no playbook dep** (they shell out to the target project's `pytest`/`pytest-cov` and parse standard junit/coverage XML with stdlib `xml.etree`).

## Architecture & tracks

| Track | Files | LoC | Depends on |
| --- | --- | --- | --- |
| M1 — evaluator core | `evaluators/{__init__,types,scope,registry,parse,grade}.py`, `evaluators/builtins/{__init__,cyclomatic,wmc,lcom4,dit,cbo}.py` + `tests/evaluators/*` | ~750 | — |
| M2 — radon MI evaluator | `evaluators/builtins/maintainability.py`, `pyproject.toml` `[metrics]` extra, tests | ~150 | M1 |
| M3 — standalone gate (static) | `commands/metrics.py`, `cli.py`, `config.py` (`[metrics]`), `.pre-commit-hooks.yaml` + resources, `tests/cli/test_metrics.py` | ~350 | M1 |
| M4 — execution evaluators | `evaluators/execution/{__init__,project,junit,coverage_xml,test_pass,coverage}.py`, `commands/metrics.py` (`--run-tests`), tests | ~400 | M1, M3 |
| M5 — judged evaluators + dormant eval wiring | `evaluators/judged.py`, `evals/task.py` (block-compiler + `EvalTask.metrics`), `evals/loader.py`, `evals/validator.py`, tests | ~300 | M1 |
| M6 — docs | `SPEC.md`, `README.md`, `CLAUDE.md` | — | M1–M5 |
| Integration | merge + CI gate (`mypy` + `pytest -q` + `ruff`, no path args) + PR | — | all |

**Tech Stack:** Python 3.12+, **stdlib only** for the core (`ast`, `dataclasses`, `enum`, `subprocess`, `xml.etree.ElementTree`, `tempfile`, `importlib.metadata`). `radon>=6.0` optional (M2). Execution evaluators add no playbook dep (target supplies `pytest`/`pytest-cov`).

---

## Context for fresh subagents

Engine complete; eval **runner + judge are v2 placeholders raising `NotImplementedError`** (`evals/runner.py`, `evals/judge.py`), so eval-output scoring (rubric, and eval-output execution metrics) does not execute in v1. This PR adds the evaluator **engine + standalone gate (static now, execution opt-in)** and compiles eval blocks to evaluators the v1.1 runner will execute. Required reading: this spec; `evals/task.py` (`ExpectedOutcome`/`Rubric`/`EvalTask`, `CheckResult`); `evals/judge.py` (`Judge` ABC); `pyproject.toml` (frozen deps, optional-deps, entry-point groups); `config.py` + `commands/check.py`; `.pre-commit-hooks.yaml` + `resources/precommit/`; SPEC §6.5/§15/§13/§20 + the air-gapped/no-new-deps invariant.

---

## §A — The `Evaluator` abstraction & registry

Source is parsed **once** into a `ModuleModel`; each registered + available evaluator gets an `EvalContext` and emits **one `Measurement` per scope**.

```python
class Scope(Enum):       FUNCTION; METHOD; CLASS; FILE; MODULE     # MODULE = whole target/suite
class ValueKind(Enum):   NUMERIC; SCORE; BOOL                       # SCORE/BOOL already 0–1 / 0|1
class Determinism(Enum): DETERMINISTIC; JUDGED                      # regression semantics + v1/v1.1 routing

class Evaluator(ABC):
    name: str
    scope: Scope
    value_kind: ValueKind
    determinism: Determinism
    higher_is_worse: bool                 # CC/WMC/CBO/DIT/LCOM4 True; MI/coverage/test/SCORE False
    requires: str | None = None           # optional dep/capability (e.g. "radon"); None = stdlib
    default_absolute: AbsoluteThreshold
    default_regression: RegressionPolicy  # max_worsening: 0 deterministic-static/exec; >0 judged
    default_weight: float = 0.0           # >0 ⇒ contributes to the weighted composite

    def available(self, ctx: EvalContext) -> bool:
        """True if computable here: deps importable AND the needed context is present
        (module for static, ctx.project for execution, ctx.judge for judged)."""
    @abstractmethod
    def evaluate(self, ctx: EvalContext) -> list[Measurement]: ...  # one per scope
    def to_score(self, value: float, policy: ResolvedPolicy) -> float:
        """Normalize raw value → 0–1 (higher = better) for the composite. Default ramp around
        warn/fail (inverted when higher_is_worse=False); SCORE/BOOL default to identity."""
```

`EvalContext` provides what each family needs, decoupled:
- **static:** `module: ModuleModel | None`, `source: str`, `label: str`.
- **execution:** `project: ProjectHandle | None` — a runnable root + resolved test command + temp report dir; execution evaluators `available()` ⇔ `ctx.project is not None`.
- **judged:** `judge: Judge | None`, `artifact`, `samples: int`.

**Registration:** in-tree `@register_evaluator` decorator (each builtin self-registers on import; `builtins/__init__` + `execution/__init__` import them); out-of-tree entry-point group `coding_agent_playbook.evaluators`. `all_evaluators()` / `static_evaluators()` / `deterministic_evaluators()` / `get_evaluator(name)` for selection. **Parse once** in `evaluators/parse.py` (`ModuleModel`, `parse_module`, the shared `_cyclomatic` helper, stable scope keys `…<label>::<qualname>` / `<label>`).

### §A.1 — How the families are differentiated (no `kind` enum)

The families (static metric · execution · judged/rubric · file-check) are **emergent from orthogonal axes**, not a single `type` field — the engine never switches on a "kind":

| Family | `determinism` | `needs_project` | `value_kind` | `available(ctx)` needs | authoring block | examples |
|---|---|---|---|---|---|---|
| **static metric** (§B) | DETERMINISTIC | `False` | NUMERIC | source/AST (always) | `[metrics]` | `cyclomatic_complexity`, `maintainability_index` |
| **execution** (§B2) | DETERMINISTIC | `True` | SCORE/NUMERIC | `ctx.project` | `[metrics]` | `test_pass_rate`, `coverage` |
| **judged / rubric** (§B3) | JUDGED | `False` | SCORE | `ctx.judge` | `[rubric]` | `JudgedCriterion` |
| **file check** | DETERMINISTIC | `False` | BOOL | source/files | `[expected]` | file-exists / regex |

Two views of the same thing:
- **Authoring** — you differentiate by **TOML block** (`[metrics]` / `[rubric]` / `[expected]`); `evaluators_for_task` (§D) compiles each block into `Evaluator` instances.
- **Engine** — it reads the three axes above. Selection helpers *are* the partition: `static_evaluators()` = `DETERMINISTIC and not needs_project`; `deterministic_evaluators()` = `DETERMINISTIC` (static + execution); judged runs only when `ctx.judge` is set (so v1, with no judge, never runs it).

**Why no enum:** "deterministic? needs to run code? needs a model?" are independent questions, so encoding them as separate fields keeps **one `grade()` path** (raw value → gate; `to_score()` → composite — a rubric score and a CC count flow through the same comparator), **routes by capability** (`available(ctx)`) instead of a type switch, and lets a new kind (e.g. a `needs_project` security scan) drop in by choosing axis values — no enum to extend.

---

## §B — Static metric evaluators (each owns its defaults)

| `name` | scope | `higher_is_worse` | `default_absolute` | `default_regression` | requires | track |
|---|---|---|---|---|---|---|
| `cyclomatic_complexity` | FUNCTION/METHOD | true | `warn=10, fail=20` | `max_worsening=0` | — | M1 |
| `wmc` | CLASS | true | `fail=50` | `max_worsening=0` | — | M1 |
| `lcom4` | CLASS | true | `warn=2` | `max_worsening=0` | — | M1 |
| `dit` | CLASS | true | `warn=5` | `max_worsening=0` | — | M1 |
| `cbo` (≈) | CLASS | true | `warn=14` | `max_worsening=0` | — | M1 |
| `maintainability_index` | FILE | **false** | `fail=65` | `max_worsening=0` | `radon` | M2 |

Algorithms (stdlib `ast`): **CC** = 1 + decision points (`If/For/AsyncFor/While`, comprehension `if`s, `BoolOp` operands−1, `ExceptHandler`, `IfExp`, `match` guards, `assert`); **WMC** = `sum(_cyclomatic(m) …)`; **LCOM4** = connected components of the method graph (shared `self.x` attr or `self.m()` call); **DIT** = longest resolvable base chain (external base = depth 1); **CBO≈** = distinct external types referenced (labeled approximate; undercounts under duck typing); **MI** = `radon.metrics.mi_visit`, 0–100 SEI variant pinned in docs.

---

## §B2 — Execution evaluators — M4 (standalone opt-in now; eval-output v1.1)

Deterministic but require **running the project's test suite**. They add **no playbook dependency**: a `ProjectHandle` runs a configurable command (default `python -m pytest --junitxml=<tmp>/j.xml --cov --cov-report=xml:<tmp>/c.xml -q`) in the target, and the evaluators parse the standard **junit XML** + **coverage XML** with stdlib `xml.etree.ElementTree`. The target project supplies `pytest`/`pytest-cov`.

| `name` | scope | value_kind | `higher_is_worse` | `default_absolute` | `default_regression` | needs |
|---|---|---|---|---|---|---|
| `test_pass_rate` | MODULE (suite) | SCORE (passed/total) | false | `fail < 1.0` (all must pass) | `max_worsening=0` (no new failures) | `ctx.project` |
| `coverage` | FILE (+MODULE total) | NUMERIC (% 0–100) | false | `warn < 80` | `max_worsening=0` (coverage must not drop) | `ctx.project` |

- **One test run, many evaluators:** `ProjectHandle.run()` executes the suite once and caches the parsed junit + coverage reports; both evaluators read that cache (no double run). Findings' `detail` carries `passed/failed/errors/total` and per-file line/branch counts.
- **Flaky tolerance:** `test_pass_rate` is DETERMINISTIC but supports an optional **flaky-retry** (rerun failed tests up to N times before counting a failure); off by default, configurable.
- **Non-regression needs two runs** (baseline + candidate). Standalone with `--baseline git:<ref>` ⇒ a temporary `git worktree add` of the ref (heavier than the static `git show`); with `--baseline <dir>` ⇒ run there. Absolute mode (single run on the current tree) is the lighter default. Eval (v1.1): the runner runs the suite on `setup/` (baseline) and on the agent's output (candidate).
- **Safety/heaviness:** running tests has side effects and cost, so execution evaluators are **opt-in** (`--run-tests`) and **excluded from the default pre-commit hook** (pre-commit stays static-only).

---

## §B3 — Judged evaluator (rubric, generalized) — M5, dormant until v1.1

```python
# NOT a registered singleton — the block-compiler instantiates one JudgedCriterion per rubric line.
class JudgedCriterion(Evaluator):
    # name=f"judged:{slug(criterion)}"; scope=FILE/MODULE; value_kind=SCORE; determinism=JUDGED
    # higher_is_worse=False; requires="<judge backend>"; default_weight=<rubric weight>
    # default_absolute=AbsoluteThreshold(fail=<min score>)   # optional
    # default_regression=RegressionPolicy(max_worsening=0.1) # tolerance (stochastic)
    criterion: str; weight: float
    def evaluate(self, ctx):  # ctx.judge.score(self.criterion, ctx.artifact, n=ctx.samples) → 0–1
```
Judged specifics: non-regression uses a **tolerance band** (`max_worsening≈0.1`) **+ optional n-sample averaging** (`ctx.samples`) to damp LLM noise; deterministic evaluators stay exact (`0`). Makes "the judged score must not drop vs baseline" a first-class (advisory) gate. `available()` is False without a configured `Judge`, so v1 never runs it.

---

## §C — Grade + aggregate — `evaluators/grade.py`

`grade(candidate, baseline|None, policy: GradePolicy) -> EvaluationReport`. `GradePolicy` = `(mode, thresholds, regression, weights)` exposed by both the standalone `MetricConfig` and the eval block-compiler (read via a `Protocol`). Per candidate `Measurement`, resolve effective policy (`evaluator.default_*` ← config) and match baseline by `(evaluator, scope_key)`:
- **existing scope:** `worsening = (cand−base)` if `higher_is_worse` else `(base−cand)`; `> max_worsening` ⇒ `fail`/`regression`; else absolute at `warn`.
- **new scope:** absolute ⇒ `kind="new"`. **removed:** ignored.

**Two aggregate outputs:** the **gate** (`passed = no fail`; exit non-zero when `fail_on_breach`; warnings fail only under `strict`) and the **composite** (weighted mean of `to_score()` over evaluators with `weight>0` — spanning static, execution, and judged uniformly). Modes: `regression` (default), `absolute`, `both`.

---

## §D — Consumers, one registry

### v1 — standalone gate — M3 (static) + M4 (execution opt-in)
`playbook metrics [PATHS…] [--baseline git:REF|DIR] [--mode …] [--run-tests] [--test-cmd "…"] [--strict] [--format text|json]`, `run(args)->int`.
- Default: `static_evaluators()` (fast, air-gapped). `--run-tests` adds execution evaluators (builds a `ProjectHandle`, runs the suite once). Static baseline via `git show`; execution baseline via temp `git worktree`. Non-zero exit on breach (like `playbook check`). `[metrics]` config in `.coding-agent-playbook.toml`.
- Pre-commit: a `repo: local` hook runs `playbook metrics --baseline git:HEAD` (**static only**; execution opt-in via a separate, off-by-default hook or CI).

### v1.1 — eval blocks compile to evaluators (dormant now) — M5
`[expected]`/`[metrics]`/`[rubric]` stay readable; `evaluators_for_task(task, config) -> list[Evaluator]` compiles `[metrics]`→static **and** execution evaluators, `[rubric]`→`JudgedCriterion`s, `[expected]`→bool evaluators. The v1.1 `HarnessRunner` runs them routed by `available(ctx)` (static + execution against `setup/`-vs-output; judged via the `Judge`), producing the gate + composite via the same `grade()`. v1 **parses + validates** the blocks (incl. top-level `[metrics]`, sibling of `[rubric]`) but executes nothing.

```toml
# task.toml — [metrics] sibling of [expected]/[rubric]
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

---

## §E — Dataclasses (parallel `ExpectedOutcome`/`CheckResult`)

```python
@dataclass(frozen=True) class AbsoluteThreshold: warn: float|None=None; fail: float|None=None
@dataclass(frozen=True) class RegressionPolicy:  max_worsening: float = 0.0
@dataclass(frozen=True) class Measurement:       evaluator: str; scope_key: str; value: float
@dataclass(frozen=True) class Finding:           evaluator; scope_key; value; baseline: float|None; \
                                                 bound: float|None; score: float; level: str; kind: str
@dataclass class EvaluationReport: findings: list[Finding]; warn_count; fail_count; composite: float|None; passed: bool

@dataclass class ProjectHandle:    # execution context
    root: Path; test_cmd: list[str]; report_dir: Path
    def run(self) -> "RunArtifacts": ...   # runs once, caches parsed junit + coverage

@dataclass class MetricConfig:     # parsed [metrics] (standalone); satisfies GradePolicy
    mode="regression"; fail_on_breach=True; strict=False; run_tests=False; test_cmd: list[str]|None=None
    thresholds: dict[str, AbsoluteThreshold]=field(default_factory=dict)
    regression: dict[str, RegressionPolicy]=field(default_factory=dict)
    weights:    dict[str, float]=field(default_factory=dict)
```
`level ∈ {ok,warn,fail}`, `kind ∈ {absolute,regression,new}`.

---

## §F — Invariants

- **Air-gapped / no new hard deps** — core stdlib-only; `radon` optional (`[metrics]` extra, lazy import via `available()`); execution evaluators shell out to the **target's** `pytest` and parse XML with stdlib (no playbook dep). Engine + static `playbook metrics` run with nothing extra installed.
- **Registry via decorator AND entry points** (`coding_agent_playbook.evaluators`); never hardcode the list; never instantiate out-of-tree evaluators directly.
- **No generated files** ⇒ no sentinel concerns. **Execution is opt-in** and never in the default pre-commit (side effects/cost).
- **Don't break the v2 eval ABCs** — judged/execution eval-output wiring is inert in v1; nothing calls the placeholder runner/judge.
- **CI parity** — `mypy` + `pytest -q` + `ruff`, no path args; ≥80% coverage on new files; strict mypy, fully typed.

---

## §G — Track tasks (TDD; checkbox per step)

### M1 — evaluator core (BLOCKER)
- [ ] `scope.py` (`Scope`/`ValueKind`/`Determinism`); `parse.py` (`ModuleModel`, `parse_module`, shared `_cyclomatic`, scope keys).
- [ ] `types.py` (`AbsoluteThreshold`, `RegressionPolicy`, `Measurement`, `Finding`, `EvaluationReport`, `MetricConfig`, `EvalContext`, `GradePolicy` Protocol).
- [ ] `registry.py` (`Evaluator` ABC + `to_score` ramp, `register_evaluator`, `all/static/deterministic_evaluators`, `get_evaluator`, entry-point loading).
- [ ] `builtins/` — `cyclomatic`, `wmc`, `lcom4`, `dit`, `cbo` (self-registering); `builtins/__init__` imports all.
- [ ] `grade.py` — `grade()` per §C (matching, `higher_is_worse`, modes, gate + composite).
- [ ] Tests — per-evaluator values on fixtures; grade tests (regression/new/removed/modes/composite); registry tests (decorator + fake entry-point + filters); `to_score` ramp. Gate green; ≥80% on new files; ruff clean.

### M2 — radon MI evaluator (optional extra)
- [ ] `builtins/maintainability.py` (`requires="radon"`, `higher_is_worse=False`, `available()` guard, `mi_visit`). `pyproject.toml` `[project.optional-dependencies] metrics=["radon>=6.0"]`.
- [ ] Tests — value under `pytest.importorskip("radon")`; skipped-when-absent test (monkeypatch `find_spec`).

### M3 — standalone command + pre-commit (static)
- [ ] `commands/metrics.py` (`run(args)->int`, baseline via `git show`, text+json, exit codes, `static_evaluators()` default) + register in `cli._SUBCOMMANDS`. `config.py` parses `[metrics]`→`MetricConfig`. `.pre-commit-hooks.yaml` + resources: a `repo: local` static metrics hook.
- [ ] `tests/cli/test_metrics.py` — absolute fail; regression pass/fail vs `--baseline` dir; `--strict`; json; missing-path exit.

### M4 — execution evaluators (test/coverage)
- [ ] `execution/project.py` (`ProjectHandle.run()` → one suite run; resolves/validates the test command; temp report dir) + `execution/junit.py` + `execution/coverage_xml.py` (stdlib `xml.etree` parsers).
- [ ] `execution/test_pass.py` (`test_pass_rate`, optional flaky-retry) + `execution/coverage.py` (`coverage`, per-file + total), self-registering.
- [ ] `commands/metrics.py` — `--run-tests`/`--test-cmd`; execution baseline via temp `git worktree`; merge execution findings into the report.
- [ ] Tests — fixture mini-project with passing/failing tests + known coverage: absolute fail on a failing suite; coverage warn under threshold; **regression**: introduce a failing test / drop coverage vs a `--baseline` dir → fail; one-run caching (assert the suite runs once); flaky-retry behavior; graceful skip when no project/`pytest`.

### M5 — judged evaluators + dormant eval wiring
- [ ] `evaluators/judged.py` (`JudgedCriterion`: SCORE/JUDGED, weight, tolerance + n-sample, `available()` False without a `Judge`).
- [ ] `evals/task.py` — top-level `[metrics]`→`EvalTask.metrics` (sibling of `expected`/`rubric`); `evaluators_for_task(task, config)` compiling blocks→evaluators (static + execution + judged). Reuse `evaluators/types.py`.
- [ ] `evals/validator.py` — validate `[metrics]` (known evaluator names incl. `coverage`/`test_pass_rate`, numeric bounds/deltas, valid mode) + rubric weights sum 1.0; aggregate violations.
- [ ] Tests — compile blocks→evaluators; judged + execution skipped without judge/project; parse/validate `[metrics]`; reject unknown names/modes; no v2 runner/judge call.

### M6 — docs
- [ ] `SPEC.md` — evaluator subsystem (abstraction, three families, registry, builtins+defaults, execution model + no-dep XML parsing, non-regression incl. judged tolerance, gate + composite, standalone + `--run-tests` + pre-commit, eval blocks→evaluators, radon extra); version/changelog bump.
- [ ] `README.md` — `playbook metrics` + `--run-tests` + `[metrics]` extra.
- [ ] `CLAUDE.md` — tracks table + evaluator invariants (stdlib-default, radon optional, execution-shells-out/no-dep + opt-in, register-via-decorator+entry-point, non-regression primary, rubric=judged evaluator).

---

## §H — Locked decisions

1. **Umbrella `Evaluator`** with three families — **static** (ast/radon), **execution** (run tests: `test_pass_rate`, `coverage`), **judged** (rubric). Decorator `@register_evaluator`, group `coding_agent_playbook.evaluators`.
2. **Unify, keep readable blocks** — `[expected]`/`[metrics]`/`[rubric]` compile to evaluators; runner routes by `available(ctx)` / `determinism`.
3. **Scope:** engine + static standalone gate now; **execution opt-in (`--run-tests`) now**, eval-output execution + judged dormant until the v1.1 runner/judge.
4. **Static set:** CC, WMC, MI, LCOM4 + DIT, CBO≈. RFC + noise excluded. **Execution set:** `test_pass_rate`, `coverage`.
5. **No new hard deps:** radon optional extra (MI); execution shells out to the target's `pytest` + parses junit/coverage XML with stdlib.
6. **Register pattern + per-scope;** raw value → gate, `to_score()` → composite.
7. **Non-regression primary** (new scopes → absolute). Deterministic static/execution exact (`max_worsening=0`); judged tolerance (`≈0.1`) + n-sample; `test_pass_rate` optional flaky-retry.
8. **Execution is opt-in & excluded from default pre-commit** (side effects/cost); coverage/test non-regression needs a baseline run (temp `git worktree`).

## §I — Open caveats (documented, not blocking)

- **CBO≈** undercounts under duck typing; rendered approximate. **DIT** cross-module bases approximated; low signal in idiomatic Python. **MI** variant pinned (0–100 SEI). **RFC** intentionally absent.
- **Execution cost/flakiness:** running tests is slow and may be flaky; non-regression on tests is exact only modulo flaky-retry; coverage non-regression assumes a stable test set. Two-run baseline (git worktree) is the cost.
- **Judged non-regression is stochastic** — meaningful only with tolerance + ≥N samples; single-sample judged regression is advisory.
