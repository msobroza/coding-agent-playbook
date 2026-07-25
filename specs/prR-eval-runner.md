# PR R1 — `HarnessRunner`: make eval execution live (deterministic layers)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development; steps use checkbox (`- [ ]`) syntax.
>
> **Commit policy (overrides any tooling default):** every commit authored **solely by `msobroza`** — no `Co-Authored-By`, no `--author`, no signing. Subagents `cd` first, default `opus`, **no `git push`/`gh pr create` until the user gate**. Verify `git config user.email` is real before committing. Run the **full cache-free CI-parity gate** (`rm -rf .mypy_cache && ruff check . && ruff format --check . && mypy && pytest -q`, no path args) before claiming green — see [[ci-parity-gate-pitfalls]].

**Goal:** implement the `HarnessRunner` (today a v2 placeholder raising `NotImplementedError`, `evals/runner.py`) so an eval task executes **end-to-end** against an agent and is **scored through the PR-M unified `Evaluator`/`grade()` model** — making the **deterministic** scoring layers (`[expected]` file checks + `[metrics]` static/execution evaluators, incl. non-regression vs `setup/`) live. **Judged/rubric scoring is deferred to R2** (no judge ⇒ `available()` skips it). This is track **R1** of the v1.1 roadmap (`specs/v1.1-eval-execution.md`).

## Locked decisions (from the R1 brainstorm)

1. **Agent boundary = seam + fake + one thin real runner.** `HarnessRunner` is the per-assistant ABC (entry-point group `coding_agent_playbook.runners`, already reserved). A deterministic **`FakeRunner`** is the hermetic default + test driver; **one thin `ClaudeCodeRunner`** ships (opt-in, never exercised in CI). Continue/OpenCode runners deferred.
2. **Result model = Option B — evolve `TaskResult` to carry an `EvaluationReport`.** Drop the inert `programmatic_checks`/`rubric_scores`; embed the unified report (full per-finding fidelity, one model, renders like `playbook metrics`). This deliberately revises the §15 placeholder shape — sanctioned because v1.1 *is* the v2-activation milestone and those fields have no consumers yet.
3. **Captured candidate state = tree + diff vs `setup/` + transcript.** The scratch repo is git-init'd with `setup/` as the baseline commit; after the agent runs, capture the post-agent tree, a `git diff` against the baseline, and the transcript. (The diff/transcript become the judge's `artifact` in R2.)
4. **`[expected]` (one sliver of R3 pulled forward):** to keep Option B's single-report model coherent, R1 compiles `[expected]` file checks into **BOOL findings** so one `EvaluationReport` covers expected + metrics. The full registered-evaluator `[expected]` compile inside `evaluators_for_task` remains **R3**.

## Architecture & tracks

| Track | What | Files |
| --- | --- | --- |
| R1a — result types + runner ABC | evolve `TaskResult`/`EvalReport` (Option B); `HarnessRunner` template-method ABC + `_invoke_agent` hook; `AgentRun`; `FakeRunner`; entry-point group | `evals/runner.py`, `evals/fake_runner.py`, `pyproject.toml`, tests |
| R1b — orchestration + scoring | `materialize` (setup→scratch, git baseline, mock facts), `render_prompt`, `capture` (tree/diff/transcript), and the scoring bridge (`evaluators_for_task` + `EvalContext` build + `[expected]`→BOOL + `grade()`) | `evals/runner.py` (orchestration helpers) + `evals/scoring.py`, tests |
| R1c — real runner | thin `ClaudeCodeRunner` (Claude Code SDK/CLI) + opt-in smoke test (skipped without CLI/auth) | `evals/claude_code_runner.py`, tests |
| R1d — CLI | `playbook eval <id> --run [--runner …] [--run-tests]` + report rendering (reuse `commands/metrics.py` text/json) | `commands/eval.py`, `cli.py`, tests |
| R1e — docs | SPEC §15 (runner live) + README + CLAUDE.md | — |

**Tech Stack:** Python 3.12+, stdlib (`subprocess` for `git`/agent CLI, `tempfile`, `shutil`). No new hard deps. The real `ClaudeCodeRunner` uses whatever the Claude Code CLI/SDK provides, imported lazily + opt-in (like radon).

---

## §1 — The runner (template method + per-assistant hook)

```python
@dataclass
class AgentRun:
    transcript: str
    returncode: int  # 0 = the agent loop completed


class HarnessRunner(ABC):
    name: str  # entry-point key; group coding_agent_playbook.runners

    def run_task(self, task: EvalTask, scratch_dir: Path) -> TaskResult:  # CONCRETE template
        baseline = materialize(
            task, scratch_dir
        )  # copy setup/ + mock facts; git init + commit baseline
        prompt = render_prompt(task)  # render prompt_id body + invocation (StrictUndefined)
        started = monotonic()
        run = self._invoke_agent(prompt, scratch_dir)  # ← ONLY per-assistant step
        candidate = capture(
            scratch_dir, baseline
        )  # post-agent tree + diff vs setup/ + run.transcript
        report = score(task, baseline, candidate)  # [expected]→BOOL + [metrics] via grade() (§2)
        return TaskResult(
            task_id=task.id,
            harness=self.name,
            report=report,
            passed=report.passed,
            aggregate_score=report.composite
            if report.composite is not None
            else float(report.passed),
            duration_seconds=monotonic() - started,
            transcript=run.transcript,
        )

    @abstractmethod
    def _invoke_agent(self, prompt: str, scratch_dir: Path) -> AgentRun: ...
```

- **`FakeRunner`** (`name="fake"`): `_invoke_agent` applies a deterministic mutation — a configured patch, a file-writes dict, or a `Callable[[Path], None]` — and returns a canned transcript. This is the hermetic default and the unit-test driver; **no network, no CLI**.
- **`ClaudeCodeRunner`** (`name="claude_code"`, R1c): `_invoke_agent` drives the Claude Code CLI/SDK bound to `scratch_dir`, captures the transcript. Lazy import; `available()`-style guard; its smoke test is `importorskip`/env-gated and never runs in CI.
- Discovery via `coding_agent_playbook.runners` (reserved entry-point group); never instantiate directly.

## §2 — Scoring bridge (`evals/scoring.py`)

`score(task, baseline, candidate) -> EvaluationReport`:
1. **`[metrics]`** — `evals = evaluators_for_task(task, task.metrics)` (static + execution; judged present but `available()` False without a judge → skipped). Build measurements:
   - static evaluators: per source file in the candidate tree, `EvalContext(module=parse_module(...), source, label)`.
   - execution evaluators: a `ProjectHandle` on the candidate tree (`ctx.project`), with the **baseline run on `setup/`** for non-regression.
2. **`[expected]`** — compile `task.expected` (`ExpectedOutcome`) into **BOOL measurements** (`file_exists`/`file_contains`(regex)/`file_unchanged`/`file_forbidden`) over the candidate (vs baseline for `unchanged`). *(Interim; R3 moves this into `evaluators_for_task`.)*
3. `grade(candidate_measurements, baseline_measurements, policy=task.metrics)` → one `EvaluationReport` (findings across expected+metrics, `composite`, `passed`). Deterministic exact (`max_worsening=0`); new scopes → absolute.

## §3 — Evolved result types (Option B) — `evals/runner.py`

```python
@dataclass
class TaskResult:
    task_id: str
    harness: str
    report: EvaluationReport  # findings (score/level/kind), composite, passed  ← REPLACES checks/rubric_scores
    passed: bool  # = report.passed (convenience)
    aggregate_score: float  # = report.composite (or 1.0/0.0 fallback)
    duration_seconds: float
    transcript: str


@dataclass
class EvalReport:  # aggregate over tasks; now reads report.passed
    engine_version: str
    harness: str
    task_results: list[TaskResult]
    aggregate_pass_rate: float  # mean(tr.passed for tr in task_results)
    timestamp: str
```
`CheckResult` may be retired (its role is now a BOOL `Finding`) or kept only if a consumer needs it — prefer retiring for one model.

## §4 — CLI — `commands/eval.py`

Extend the existing list/show command with execution:
`playbook eval <task-id> --run [--runner fake|claude_code] [--run-tests] [--format text|json]`
- Loads the task, picks the runner (default `fake`), runs it, renders the `EvaluationReport` (reuse `commands/metrics.py`'s text/json rendering of findings + gate + composite). Exit non-zero on `not report.passed`. v1 `--list`/`--show` unchanged.

## §5 — Invariants

- **Hermetic + air-gapped by default.** `FakeRunner` needs no network/CLI; all unit tests use it. The real `ClaudeCodeRunner` is opt-in and **never in CI**.
- **Judged deferred (R2).** Runner sets `EvalContext.judge = None` ⇒ judged evaluators skip; `report` is deterministic-only. No call to the v2 `Judge` placeholder.
- **Don't break the v1 public surface.** The `Evaluator`/`grade`/`evaluators_for_task` API and the `[metrics]`/`[rubric]`/`[expected]` schema stay stable; only the eval *result* types (`TaskResult`/`EvalReport`) evolve, which is the sanctioned v2-activation change (note it in SPEC §15).
- **Registry via entry points** (`coding_agent_playbook.runners`); never instantiate runners directly.
- **Full cache-free CI gate** before green (the radon/mypy-cache + ruff-whole-repo lessons).

## §6 — Tests (TDD; hermetic)

- **`FakeRunner` round-trips** — a `refactor` fixture (`setup/` has a long function + a passing test): a fake patch that *extracts a helper* → assert the report passes, CC went **down** (non-regression), tests still pass; a fake patch that *worsens* CC / breaks a test → assert the gate **fails** with the right `Finding.kind` (regression/absolute) and `level`.
- **`[expected]` BOOL findings** — `files_created`/`files_must_contain`/`files_unchanged`/`files_forbidden` produce passing/failing BOOL findings in the unified report.
- **Execution non-regression** — a fixture where the fake drops coverage / introduces a failing test → `coverage`/`test_pass_rate` findings fail vs the `setup/` baseline (gated behind a runnable mini-project, `--run-tests`).
- **Result model** — `TaskResult.report` is an `EvaluationReport`; `EvalReport.aggregate_pass_rate` reads `report.passed`.
- **CLI** — `eval <id> --run` exits 0 on a clean fake patch, non-zero on a failing one; `--format json` shape.
- **`ClaudeCodeRunner`** — smoke test skipped without the CLI/auth env (no CI dependence).

## §7 — Out of scope (later tracks)

- **R2** — `Judge` (`LLMJudge`/`ProgrammaticOnlyJudge`) + the `Judge.score` signature reconciliation; wires `EvalContext.judge` so `[rubric]` scores.
- **R3** — full `[expected]`→bool inside `evaluators_for_task` (R1 uses an interim inline compile); execution-evaluator wiring polish.
- **Continue/OpenCode runners**; multi-task `EvalReport` orchestration / `playbook eval --all`.
