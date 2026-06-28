# PR R2+R3+OpenCode — judged scoring + unified `[expected]` + a second real runner

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development; checkbox steps.
>
> **Commit policy (overrides any tooling default):** commits authored **solely by `msobroza`** — no `Co-Authored-By`, no `--author`, no signing. Subagents `cd` first, default `opus`, **no push/PR until the user gate**. Run the **full cache-free, no-optional-extras CI-parity gate** (`uv pip uninstall radon -y; rm -rf .mypy_cache; ruff check . && ruff format --check . && mypy && pytest -q`, no path args) before claiming green — see [[ci-parity-gate-pitfalls]].

**Goal:** three v1.1 tracks on one PR, building on R1 (eval runner is live for deterministic layers):
- **J (R2)** — activate **judged `[rubric]` scoring**: reconcile the `Judge` interface, implement `LLMJudge` (opt-in) + wire `EvalContext.judge` so `JudgedCriterion` scores.
- **E (R3)** — **unify `[expected]`** into BOOL evaluators inside `evaluators_for_task` (replacing R1's interim inline compile in `scoring.py`), so all three layers flow through one `grade()`.
- **O** — **`OpenCodeRunner`**, a second real runner (mirror the opt-in `ClaudeCodeRunner`).

## Locked decisions
1. **Judge interface = Option A** — per-criterion primitive `score_criterion(criterion, artifact, n) -> float` is canonical; the batch `Judge.score(rubric, transcript, scratch_dir_state) -> list[float]` becomes a thin wrapper over it. `JudgedCriterion` stays a real evaluator (computes its own `Measurement`, routed by `available()`).
2. **`LLMJudge` = claude-CLI shell-out, opt-in** (mirror `ClaudeCodeRunner`): `available()`-gated on the `claude` binary, configurable command, **never in CI**; n-sample averaging by invoking n times. **No `ProgrammaticOnlyJudge` class** — "deterministic-only" is simply *no judge configured* (`ctx.judge is None` ⇒ `JudgedCriterion.available()` False). This refines the roadmap (which named `ProgrammaticOnlyJudge`); document the equivalence in SPEC §15.3.
3. **R3 = unify** — `[expected]`→BOOL deterministic evaluators in `evaluators_for_task`; remove the R1 interim from `scoring.py`.

---

## Track J (R2) — the judge

### `evals/judge.py`
```python
class Judge(ABC):
    name: str
    @classmethod
    def available(cls) -> bool: return True          # real judges override (e.g. shutil.which)
    @abstractmethod
    def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float: ...  # 0–1, n-sample avg
    def score(self, rubric: Rubric, transcript: str, scratch_dir_state: dict[str, Any]) -> list[float]:
        return [self.score_criterion(c, transcript, n=1) for c in rubric.criteria]       # batch = sugar
```
- **`LLMJudge`** (`name="llm"`): `score_criterion` shells out to the `claude` CLI (arg-list, no shell, configurable command) with a fixed grading prompt embedding the criterion + `artifact` (the candidate diff/transcript), parses a 0–1 score from stdout; averages `n` invocations. `available()` ⇒ `shutil.which("claude") is not None`. Lazy/stdlib only; **never run in CI** (its real test is env-gated like the `ClaudeCodeRunner` smoke test). Registered via the `coding_agent_playbook.judges` entry-point group (reserved).
- **`StubJudge`** (tests only, not registered): deterministic `score_criterion` from a dict — drives all judged unit tests hermetically.
- Keep the existing v2 `NotImplementedError` contract gone — `Judge` is now concrete-able.

### `evaluators/judged.py` + `evaluators/types.py`
- `JudgedCriterion.evaluate(ctx)` calls **`ctx.judge.score_criterion(self.criterion, ctx.artifact, n=ctx.samples)`** (rename from the duck-typed `.score`), returns one SCORE `Measurement`. `available(ctx)` stays `ctx.judge is not None`.
- Type `EvalContext.judge` as **`Judge | None`** (replace `Any`); keep the import `TYPE_CHECKING`-guarded to avoid a runtime cycle.

### Scoring + runner + CLI wiring
- `evals/scoring.py`: when `ctx.judge` is set, judged evaluators (`JudgedCriterion`) are included (their `available()` is True) → SCORE findings in the report (composite via `to_score`; absolute gate if the criterion has a `fail` min-score; non-regression tolerance applies only when a baseline judged measurement exists). With no judge ⇒ judged skipped (unchanged deterministic-only).
- `evals/runner.py`: `run_task` sets `ctx.judge` (when one is configured) + `ctx.artifact` (the captured diff/transcript) + `ctx.samples`.
- `commands/eval.py`: `playbook eval <id> --run [--judge llm] [--samples N]`. `--judge` selects a registered judge from `coding_agent_playbook.judges` (default: none ⇒ deterministic-only); unavailable judge (`claude` absent) ⇒ exit 2 with a clear message. `--samples` (default 1).

### Tests (hermetic via `StubJudge`)
- `score_criterion`/batch `score` wrapper; n-sample averaging.
- `JudgedCriterion.evaluate` with a `StubJudge` → SCORE measurement; `available()` False without a judge.
- A task with `[rubric]` run via `FakeRunner` + `StubJudge` → judged findings appear in the report, contribute to the composite, and a low criterion score fails the gate (if a min-score is set).
- `LLMJudge.available()` False when `claude` absent (monkeypatch `shutil.which`); the real `claude` test env-gated (`PLAYBOOK_E2E_CLAUDE=1`), never CI.
- CLI `--judge llm` when `claude` absent ⇒ exit 2; `--judge` omitted ⇒ deterministic-only.

---

## Track E (R3) — unify `[expected]` into evaluators

- Add BOOL deterministic evaluators for the four `[expected]` checks: `file_exists`, `file_contains` (regex), `file_unchanged` (vs baseline), `file_forbidden`. `value_kind=BOOL`, `determinism=DETERMINISTIC`, `higher_is_worse=False`, must-be-true gate (absolute `fail` on False).
- They need the candidate tree + (for `file_unchanged`) the baseline tree. **Extend `EvalContext`** with `tree: Path | None` (candidate root) and `baseline_tree: Path | None`; the runner sets both; static/execution/judged evaluators ignore them. The `[expected]` evaluators read them via `available(ctx)` (⇔ `ctx.tree is not None`).
- **`evaluators_for_task`** compiles `task.expected` (`ExpectedOutcome`) into these evaluator instances (parameterized by path/pattern), alongside `[metrics]` and `[rubric]`.
- **`evals/scoring.py`**: remove the interim inline `[expected]`→BOOL compile; `[expected]` now flows through `evaluators_for_task` + `grade()` like everything else (one model, one report). Behaviour preserved (the R1 expected tests still pass).
- Tests: each `[expected]` evaluator (pass + fail) via the unified path; `evaluators_for_task` emits them; scoring no longer special-cases `[expected]`; the R1 runner expected-findings tests still green.

---

## Track O — `OpenCodeRunner`

- `evals/opencode_runner.py`: `OpenCodeRunner(HarnessRunner)`, `name="opencode"`, `requires_resolved_prompt=True`. `_invoke_agent` shells out to the `opencode` CLI bound to `scratch_dir` (configurable command template with a `{prompt}` token, arg-list, no shell), captures transcript + returncode. `available()` ⇒ `shutil.which("opencode") is not None`. Lazy/stdlib only; **opt-in, never in CI** (env-gated smoke test). Register `opencode` under `coding_agent_playbook.runners`.
- Tests: `available()` toggling via monkeypatched `shutil.which`; subprocess plumbing via a fake command (writes a file into `cwd`); strict-prompt raise (inherited); discoverable via the entry point; real smoke env-gated.

---

## Invariants
- **Air-gapped:** `LLMJudge`/`OpenCodeRunner`/`ClaudeCodeRunner` shell out to external CLIs, opt-in, `available()`-gated, **never in CI**; no new hard deps. Deterministic-only (no judge) stays the default. Tests hermetic (`StubJudge`, `FakeRunner`, fake commands).
- **Don't break v1/R1:** the `Evaluator`/`grade`/`evaluators_for_task` API and the task schema stay stable; the R1 runner/CLI/result-model unchanged except the additive `--judge`/`--samples` + `EvalContext` fields.
- **Registry via entry points** (`coding_agent_playbook.judges`, `coding_agent_playbook.runners`); never instantiate directly.
- **Full cache-free, no-extras gate** before green.

## Build order (sequential — one branch, one PR)
1. **J (R2)** — judge ABC + `LLMJudge` + `StubJudge` + `JudgedCriterion` rewire + `EvalContext.judge` typing + scoring/runner/CLI wiring + tests.
2. **E (R3)** — `[expected]` BOOL evaluators + `EvalContext.tree/baseline_tree` + `evaluators_for_task` compile + remove `scoring.py` interim + tests.
3. **O** — `OpenCodeRunner` + tests.
4. **Docs** — SPEC §15.3 (judge live; no `ProgrammaticOnlyJudge` — None = deterministic-only), §21.2.3 (the reconciled `score_criterion` interface — debt closed), §12.8 (`--judge`/`--samples`), README, CLAUDE.md, `specs/v1.1-eval-execution.md` (R2/R3 + OpenCode landed). Don't touch CLAUDE.md policy sections.

## Out of scope
- `ContinueCLIRunner`; multi-task `playbook eval --all`; batching LLM judge (N→1 call) optimization; judged non-regression baselining for eval (judged is absolute + composite in eval; the tolerance path is exercised where a baseline judged measurement exists).
