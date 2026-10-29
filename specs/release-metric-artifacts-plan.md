# Release metric artifacts: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every release publishes a metric-change bundle on GitHub and GitLab.
Record runs reuse any committed result with the same inputs and setup, and
re-grade stored answers when only the judge changed.

**Architecture:** New pure `evals` modules do the work, each one fed by the
record command and the release scripts:

| Module | Job |
|---|---|
| `result_index` | reuse lookup |
| `answers_store` | stored answers |
| `rejudge` | re-scoring |
| `judge_agreement` | old vs new judge |
| `release_report` | report data |

`scripts/release_report.py` adds the charts. CI jobs on the release tag build
the bundle and attach it to the forge release. The maintainer still runs the
paid evals.

**Tech stack:**
- Python 3.12, stdlib `gzip`/`json`/`csv`, pytest;
- matplotlib in `scripts/` and the publish jobs only;
- GitHub Actions with `gh`;
- GitLab CI with release-cli and the Releases API.

**Spec:** [`specs/release-metric-artifacts.md`](release-metric-artifacts.md),
decisions D1-D11. ADR: `docs/adr/0014-…`.

## Global Constraints

- No new engine dependency. matplotlib only in `scripts/release_report.py`
  and the CI publish jobs, imported lazily.
- Engine code goes only in `evals` or `commands`. The import-linter layers put
  `release` below `evals`.
- Every new top-level `evals` module is listed in `evals.setup_digest`:
  - `rejudge` in `SCORING_MODULES`;
  - `result_index`, `answers_store`, `judge_agreement` and `release_report` in
    `SCORING_EXEMPT`, with a one-line reason.

  `test_every_scoring_module_is_listed` (or its current name) must stay green.
- Code shape:
  - type hints on every signature;
  - functions of about 4-20 lines;
  - files under 500 lines;
  - nesting depth of 2 or less;
  - errors carry the offending value. Reuse `ExitTwoError` subclasses for CLI
    refusals.
- Commits:
  - Conventional Commit subjects; engine and CI changes are `feat`, test-only
    changes are `test`;
  - **no `Co-Authored-By` trailer**;
  - never `--author` or `-S`;
  - don't hand-edit anything under `catalog/releases/`.
- The gate, run before claiming any task green:

  ```bash
  ruff check .
  ruff format --check .
  mypy
  pytest -q
  ```

  Run it cache-free, without optional extras, and in Python 3.12 too.
- The answers file path is `catalog/releases/<v>/answers/<target>.jsonl.gz`.
- Record-side defaults:
  - answers are written beside `OUT` as `OUT.answers.jsonl.gz`;
  - the Markdown limit is `120_000` characters;
  - agreement compares the rubric pass verdict and the weighted rubric score.

## Review Focus

1. **The in-progress release indexes itself.** `prepare --eval` writes into
   `catalog/releases/<new>/metrics/`, which is inside the index root. The record
   must never index its own `--record OUT` path. Test in Task 2.
2. **`--jobs N` mixes answers between samples.** Each run's captured judge calls
   must stay with that run. Test in Task 6.
3. **`--resume` loses answers.** A resumed record must write the answers of
   checkpointed samples too. Test in Task 6.
4. **No run to compare when the judge changed.** All re-judged runs may have
   failed their gate under fail-fast. Then `judge_change` is not written, and
   there is no division by zero. Test in Task 9.
5. **A release that adds or drops a target.** The report shows an added target
   as "no baseline" and ignores a dropped one, without crashing. Test in Task 11.

---

## Phase A: reuse every committed result (D1-D3)

### Task 1: Result index over all release metrics files

**Files:**
- Create: `src/coding_agent_playbook/evals/result_index.py`
- Modify: `src/coding_agent_playbook/evals/release_carry.py`: `CarryPlan` gains
  `sources: Mapping[str, str] = field(default_factory=dict)` (sample id to
  `"<release> (<target>)"`).
- Modify: `src/coding_agent_playbook/evals/setup_digest.py`: `SCORING_EXEMPT`
  gets `"evals.result_index": "finds committed entries to carry; decides no score"`.
- Test: `tests/evals/test_result_index.py`, with fixtures built by
  `tests/evals/release_metrics_files.py`.

**Interfaces:**
- Produces:
  - `IndexedFile(path: Path, release: str, target: str, data: Mapping[str, Any])`;
  - `ReleaseIndex.load(root: Path, *, exclude: Path | None = None) -> ReleaseIndex`.
    It reads `root/*/metrics/*.json`, and records each file it skipped in
    `skipped: tuple[str, ...]` as `"<path>: <reason>"`.
  - `ReleaseIndex.plan(*, target_name: str, setup: Mapping[str, object], inputs: Mapping[str, str]) -> CarryPlan`.

- [ ] **Step 1: Write the failing tests**
  - `test_a_sample_found_in_an_older_release_is_carried_from_it`: the index has
    0.2.0 and 0.3.0 with the same setup. The sample is only in 0.2.0 at that
    digest. Assert `plan.carried["t/a"]["measured_in"] == {"release": "0.2.0", "commit": "c2"}`
    and `plan.sources["t/a"] == "0.2.0 (opus)"`.
  - `test_the_newest_release_wins`: both releases hold the key. Assert the
    source is `0.3.0`.
  - `test_the_targets_own_file_wins_within_a_release`: files `alpha.json` and
    `opus.json` in 0.3.0 hold the key, and `target_name="opus"`. Assert the
    source is `0.3.0 (opus)`.
  - `test_another_target_name_with_the_same_setup_is_reused`: only `alpha.json`
    holds it. Assert the sample is carried from `0.3.0 (alpha)`.
  - `test_a_file_with_another_setup_is_skipped`: `harness_version` differs.
    Assert the sample reruns, with the reason starting
    `"every sample reruns"` and naming `harness_version`.
  - `test_files_without_digests_or_invalid_are_skipped_and_named`: assert
    `skipped` contains both paths with their reasons.
  - `test_unknown_version_never_matches`.
  - `test_measured_in_survives_a_second_carry`: an entry already carried keeps
    its original `measured_in`.
  - `test_exclude_leaves_out_the_record_output` (Review Focus 1): `exclude=OUT`,
    with `OUT` inside the root. Assert it is not indexed.
  - `test_a_new_sample_and_a_changed_digest_have_their_reasons`:
    `"new sample"` and `"inputs digest changed"`.
  - `test_reported_model_comes_from_the_newest_source`.

- [ ] **Step 2: Run them**

  ```bash
  pytest tests/evals/test_result_index.py -q
  ```

  Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `result_index.py`**
  - Validate with `validate_release_metrics` and match setups with
    `setups_match`.
  - Order releases with `packaging.version.Version`. Within a release, the own
    target comes first, then the rest sorted.
  - Build each entry with `carried_entry`, passing the source file's
    `release`/`commit`.
  - With no usable file, every sample reruns. The reason lists the first three
    skips, then `and N more`.
  - `reported_model` comes from the newest source file used.

- [ ] **Step 4: Run them** (same command). Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(evals): a result index finds committed entries to carry across every release"
  ```

### Task 2: `--carry-from DIR` in the record command

**Files:**
- Modify: `src/coding_agent_playbook/commands/_eval_record_flags.py`:
  `carry_from_path` accepts a directory, and the help text says so.
- Modify: `src/coding_agent_playbook/commands/_eval_record.py`:
  - `run_record` loads `ReleaseIndex.load(dir, exclude=out_path)` for a
    directory, else `load_baseline` as today;
  - `_plan_carry` dispatches on the baseline's type.
- Modify: `src/coding_agent_playbook/evals/release_carry.py`: `carry_plan_lines`
  adds one indented line per source, `  carried from <source>: <n>`, sorted by
  source.
- Modify: `docs/checks.md`: the `--carry-from` paragraph says it also takes the
  releases directory.
- Test: `tests/cli/test_eval_record_carry_dir.py`, with the fake runner and
  `StubJudge` as in the existing `--carry-from` CLI tests.

**Interfaces:**
- Consumes: `ReleaseIndex` (Task 1).
- Produces: the `carry plan:` stdout format plus the `  carried from` lines,
  which `scripts/release_eval.carry_plan_lines` already forwards (indented).

- [ ] **Step 1: Write the failing tests**
  - `test_carry_from_a_directory_carries_from_any_release`: assert exit 0, the
    file's `summary["carried"] == 1`, and stdout contains
    `"  carried from 0.2.0 (opus): 1"`.
  - `test_carry_from_a_file_is_unchanged`: the existing assertions, re-run
    against the dispatch.
  - `test_the_record_output_inside_the_directory_is_not_indexed`.
  - `test_carry_from_a_directory_still_needs_all`: `RecordRefusedError`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement the dispatch** (a type union `Baseline = Mapping[str, Any] | ReleaseIndex`).
- [ ] **Step 4: Run them, plus `pytest tests/evals/test_release_carry.py tests/cli -q`.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(eval): record --carry-from takes the releases directory"
  ```

### Task 3: A carried entry from an older release is compared (D2)

**Files:**
- Modify: `src/coding_agent_playbook/evals/release_regression.py`: in
  `_verdict`, a `MEASURED_IN_KEY` entry is `carried` only when `old` exists
  and both entries have the same inputs digest. Otherwise it falls through to
  the normal comparison, with `"measured in <measured_in.release>"` appended
  to `reasons`.
- Test: `tests/evals/test_release_regression.py` (extend).

- [ ] **Step 1: Write the failing tests**
  - `test_a_carried_entry_with_another_inputs_digest_is_compared`: the previous
    mean is 0.9, the carried mean is 0.6, and the digests differ. Assert the
    verdict is `regression`, `blocks` is true, and a reason contains
    `"measured in 0.2.0"`.
  - `test_a_carried_entry_with_the_same_digest_stays_carried`.
  - `test_a_carried_entry_without_a_previous_entry_is_new`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `pytest tests/evals/test_release_regression.py -q`.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(evals): a regression check compares an entry carried from an older release"
  ```

### Task 4: `prepare --eval` passes the releases directory (D3)

**Files:**
- Modify: `scripts/release_eval.py`:
  - `record_release_metrics` passes `tools.cwd / _CATALOG / "releases"`, not
    `_previous_file(...)`, unless `request.full`;
  - `_mode` adds `" (K from older releases)"` when a carried entry's
    `measured_in.release != previous`;
  - `_previous_file` is deleted if unused.
- Test: `tests/release/test_release_prepare_eval.py`: update `_carry_from`
  assertions and add the K-line test.

- [ ] **Step 1: Update the failing tests**
  - Both targets receive `str(checkout / "catalog" / "releases")`.
  - `--full` still passes none.
  - `test_the_mode_line_counts_entries_carried_from_older_releases`: assert
    `"changed-only: 1 rerun, 2 carried (1 from older releases)"`.
- [ ] **Step 2: Run `pytest tests/release/test_release_prepare_eval.py -q`.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run it.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(release): prepare --eval reuses results from every committed release"
  ```

## Phase B: releases keep their answers (D8)

### Task 5: The answers store

**Files:**
- Create: `src/coding_agent_playbook/evals/answers_store.py`
- Modify: `src/coding_agent_playbook/evals/setup_digest.py` (`SCORING_EXEMPT`:
  `"stores answers; evals.rejudge decides the scores"`).
- Modify: `src/coding_agent_playbook/evals/release_metrics.py`: rename
  `_run_check_scores` to the public `run_check_scores`. Update its callers.
- Test: `tests/evals/test_answers_store.py`

**Interfaces:**
- Produces:
  - `StoredCriterion(criterion: str, weight: float, score: float | None, n: int)`.
  - `StoredRun(sample: str, inputs_digest: str, run: int, artifact: str | None, checks: Mapping[str, float], criteria: tuple[StoredCriterion, ...], judge: Mapping[str, object], artifact_ref: ArtifactRef | None = None)`.
  - `ArtifactRef(release: str, target: str)` points at the release whose file
    holds the artifact (D9 re-judged runs). `artifact` is `None` when fail-fast
    skipped the judge, or when `artifact_ref` is set.
  - `CapturingJudge(inner: Judge)`, a `Judge` that records
    `calls: list[tuple[str, str, float, int]]` (criterion, artifact, score, n).
  - `write_answers(path: Path, runs: Iterable[StoredRun]) -> None` (gzip,
    sorted by `(sample, run)`, one JSON line each).
  - `read_answers(path: Path) -> list[StoredRun]`, which raises
    `AnswersError(ExitTwoError)` naming the path and line number.
  - `answers_path(releases_root: Path, release: str, target: str) -> Path`.

- [ ] **Step 1: Write the failing tests**
  - `test_round_trip_keeps_every_field`.
  - `test_the_file_is_gzip_one_line_per_run_sorted`.
  - `test_a_fail_fast_run_stores_null_scores_and_no_artifact`.
  - `test_a_bad_line_names_the_path_and_line`: assert
    `AnswersError` matches `r"answers\.jsonl\.gz:2"`.
  - `test_capturing_judge_records_calls_and_returns_the_inner_score`
    (`StubJudge(default=0.7)`).
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** (`gzip.open(..., "wt", encoding="utf-8")`;
  `json.dumps(sort_keys=True)`).
- [ ] **Step 4: Run `pytest tests/evals/test_answers_store.py tests/evals/test_release_metrics.py -q`.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(evals): an answers store keeps each run's graded answer, checks and criterion scores"
  ```

### Task 6: The record writes answers

**Files:**
- Modify: `src/coding_agent_playbook/evals/release_metrics.py`:
  - `SampleRuns` gains `answers: tuple[StoredRun, ...] = ()`;
  - `SampleRecord` gains `answers: tuple[Mapping[str, object], ...] = ()` (the
    JSON form, so the checkpoint keeps it);
  - `sample_record` copies it.
- Modify: `src/coding_agent_playbook/evals/record_checkpoint.py`: the line
  round-trips `answers`. A line without the key reads as `()`.
- Modify: `src/coding_agent_playbook/commands/_eval_record.py` (move the new
  helpers to `commands/_eval_record_answers.py` to keep the file under 500
  lines):
  - `_run_once` wraps `self.judge` in a new `CapturingJudge` per run;
  - it builds `StoredRun` from the captured calls, the sample's rubric weights,
    and `run_check_scores(result)`;
  - `run_record` writes the answers of every fresh `sample` unit, not controls,
    to `args.answers` or `Path(f"{out_path}.answers.jsonl.gz")`.
- Modify: `src/coding_agent_playbook/commands/_eval_record_flags.py`: add
  `--answers PATH`.
- Modify: `scripts/release_eval.py`: `_Recording` passes
  `--answers <release_dir>/answers/<name>.jsonl.gz`.
- Test: `tests/cli/test_eval_record_answers.py`, plus
  `tests/release/test_release_prepare_eval.py` (`--answers` argv).

- [ ] **Step 1: Write the failing tests**
  - `test_record_writes_one_answer_line_per_run`: 2 samples × 3 runs gives 6
    lines.
  - `test_carried_samples_write_no_answer_lines`.
  - `test_answers_of_parallel_runs_are_not_mixed` (Review Focus 2): with
    `--jobs 2` and a stub judge that returns a different score per sample,
    assert each line's criteria scores belong to its own sample.
  - `test_a_resumed_record_writes_the_checkpointed_answers` (Review Focus 3):
    kill after one sample by raising in the runner on the 2nd unit, then
    `--resume`. Assert both samples' lines are present.
  - `test_prepare_passes_answers_into_the_release_dir`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `pytest tests/cli tests/evals/test_record_checkpoint.py tests/release -q`.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(eval): record writes each fresh run's answers beside the metrics file"
  ```

## Phase C: a judge change re-grades stored answers (D9-D11)

### Task 7: Re-score one stored run

**Files:**
- Create: `src/coding_agent_playbook/evals/rejudge.py`
- Modify: `src/coding_agent_playbook/evals/setup_digest.py`: add
  `"evals.rejudge"` to `SCORING_MODULES`.
- Test: `tests/evals/test_rejudge.py`

**Interfaces:**
- Produces:
  - `RunScore(gate_passed: bool, rubric_passed: bool | None, rubric_score: float | None, passed: bool, aggregate_score: float, checks: Mapping[str, float])`.
  - `rescore_run(sample: EvalSample, stored_checks: Mapping[str, float], criterion_scores: Mapping[str, float]) -> RunScore`.
    It recomputes the rubric layer from `criterion_scores` (criterion text to
    the 0-1 mean) and the stored deterministic leaves, then the verdict from the
    gate and rubric, using the sample's own compiled expressions
    (`compile_eval_sample(sample).per_trial` and its verdict AST; see
    `evals.compile.compiler.verdict_passed` / `weighted_verdict`).
  - `judge_parts(setup: Mapping[str, object]) -> dict[str, object]` returns the
    five judge parts.
  - `JUDGE_PARTS: Final = ("judge_model", "judge_endpoint_fingerprint", "judge_samples", "judge_version", "judge_reasoning_effort")`.

- [ ] **Step 1: Write the failing tests**
  - `test_rescoring_with_the_recorded_scores_reproduces_the_run`: this is the
    anchor property. For `review/spot-the-bug`, `review/crbug-basic-auth-not`
    and `characterize/legacy-pricing` (its rubric mixes a judge threshold and
    `test_pass_rate`):
    1. run once with `FakeRunner` and a `CapturingJudge(StubJudge(...))`;
    2. take `run_check_scores` and the captured calls;
    3. assert `rescore_run(...)` equals the original `passed`,
       `aggregate_score` and `checks`.
  - `test_lower_criterion_scores_fail_the_rubric`: scores of 0.2 give
    `rubric_passed is False` and `passed is False`.
  - `test_a_failed_gate_stays_failed_whatever_the_scores`.
  - `test_judge_parts_picks_the_five_judge_keys`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Read the per-trial rubric layer's bound checks.
  Score each judge-backed leaf from `criterion_scores`, the same way
  `grading.judged.JudgeCheck` does, and take every other leaf from
  `stored_checks`. No sample has an `[aggregate]` block, so `rescore_run`
  raises `RejudgeError(ExitTwoError)` for one, with the sample id.
- [ ] **Step 4: Run `pytest tests/evals/test_rejudge.py -q`.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(evals): re-score a stored run from its checks and new criterion scores"
  ```

### Task 8: The record re-judges samples found only in agent-compatible files

**Files:**
- Modify: `src/coding_agent_playbook/evals/result_index.py`:
  - `ReleaseIndex.plan` also indexes agent-compatible files, where
    `differing_setup_parts` is a non-empty subset of `JUDGE_PARTS`;
  - `CarryPlan` gains `rejudge: Mapping[str, RejudgeSource] = field(default_factory=dict)`;
  - a key in a fully matching file still carries.
- Modify: `src/coding_agent_playbook/evals/record_checkpoint.py`: `UnitKind`
  adds `"rejudge"`.
- Modify: `commands/_eval_record.py` / `_eval_record_answers.py`:
  - each `rejudge` sample is a `RecordUnit("rejudge", ...)` whose run:
    1. reads the stored runs with `read_answers`, following an `artifact_ref`;
    2. grades each run's `artifact` with the record's judge (skipping runs with
       `artifact is None`);
    3. calls `rescore_run`;
    4. folds an entry like a fresh one, plus
       `rejudged_from: {release, commit, judge: <old judge parts>}` and
       `measured_in` (the answers' origin);
  - the new answer lines carry `artifact=None, artifact_ref=ArtifactRef(src_release, src_target)`.
- Modify: `src/coding_agent_playbook/evals/release_carry.py`: `merge_carried`
  adds `rejudged` to the summary.
- Modify: `src/coding_agent_playbook/evals/release_metrics_schema.py`: allow
  the optional `rejudged_from` entry key and the `summary.rejudged` count.
- Test: `tests/evals/test_result_index.py` (extend) and
  `tests/cli/test_eval_record_rejudge.py`.

**Interfaces:**
- Produces: `RejudgeSource(release: str, commit: str | None, target: str, entry: Mapping[str, Any], judge: Mapping[str, object])`.

- [ ] **Step 1: Write the failing tests**
  - `test_a_judge_only_difference_plans_a_rejudge`.
  - `test_a_full_match_wins_over_a_rejudge`.
  - `test_a_non_judge_difference_still_reruns`.
  - `test_without_stored_answers_the_sample_reruns`, with the reason
    `"answers not stored"`.
  - `test_rejudge_calls_the_judge_but_never_the_runner`: a `FakeRunner` that
    raises if invoked; assert the judge call count is runs × criteria.
  - `test_a_rejudged_entry_records_its_sources`: `rejudged_from.release`,
    `measured_in.release` and `summary.rejudged == 1`.
  - `test_a_fail_fast_gate_failure_is_not_regraded`.
  - `test_an_unreadable_answers_file_reruns_its_samples`, with the reason
    starting `"answers unreadable:"`.
  - `test_a_judge_error_while_regrading_refuses_the_record`: a judge that
    raises `JudgeError` gives `RecordRefusedError`, and the checkpoint keeps
    the samples that finished.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `pytest tests/evals tests/cli -q`.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(eval): a judge change re-grades stored answers instead of rerunning the agents"
  ```

### Task 9: Judge agreement (D10)

**Files:**
- Create: `src/coding_agent_playbook/evals/judge_agreement.py`
- Modify: `src/coding_agent_playbook/evals/setup_digest.py`: `SCORING_EXEMPT`
  gets `"compares two judges' scores of the same answers; decides no score"`.
- Modify: `commands/_eval_record_answers.py`: collect an `AgreementRun` per
  re-graded run, then write `judge_change` and print the line before writing
  the file.
- Modify: `src/coding_agent_playbook/evals/release_metrics_schema.py`: allow
  the optional top-level `judge_change`.
- Test: `tests/evals/test_judge_agreement.py`

**Interfaces:**
- Produces:
  - `AgreementRun(task: str, old_passed: bool, new_passed: bool, old_score: float, new_score: float)`.
    Both sides go through `rescore_run`.
  - `judge_change(runs: Sequence[AgreementRun], *, old: Mapping[str, object], new: Mapping[str, object]) -> dict[str, object] | None`.
    It returns `None` for no runs; otherwise
    `{"from", "to", "runs", "pass_agreement", "mean_abs_score_diff", "tasks"}`,
    rounded like the metrics file's other values.
  - `agreement_line(change: Mapping[str, object]) -> str` returns
    `"judge change: <old model> -> <new model>: pass agreement 93% over 96 runs, mean |Δ| 0.04"`.

- [ ] **Step 1: Write the failing tests**
  - `test_pass_agreement_and_mean_abs_diff_on_a_hand_computed_set`: 4 runs, one
    pass flip, score diffs 0.1, 0, 0.2, 0.1. Assert `pass_agreement == 0.75`
    and `mean_abs_score_diff == 0.1`.
  - `test_tasks_are_split`.
  - `test_no_runs_gives_none` (Review Focus 4).
  - `test_the_line_reads_as_specified`.
  - A CLI test: `test_a_rejudged_record_writes_judge_change_and_prints_it`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `pytest tests/evals/test_judge_agreement.py tests/cli -q`.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(evals): measure and record how closely a new judge agrees with the old one"
  ```

### Task 10: The regression check across a judge change (D11)

**Files:**
- Modify: `src/coding_agent_playbook/evals/release_regression.py`:
  - `SampleStatus` adds `"rejudged"`;
  - an entry with `rejudged_from` gets `rejudged`, whose delta is
    `mean - previous_mean` and which never blocks;
  - `--accept` refuses it, like `carried`;
  - when `new` has `judge_change`, every compared sample gets the reason
    `"judge changed since <previous>: pass agreement <x>%"`.
- Modify: `src/coding_agent_playbook/evals/release_regression_format.py`: the
  tally counts `rejudged`.
- Test: `tests/evals/test_release_regression.py` (extend).

- [ ] **Step 1: Write the failing tests**
  - `test_a_rejudged_entry_never_blocks_and_shows_the_judge_delta`.
  - `test_accept_refuses_a_rejudged_sample`.
  - `test_compared_samples_carry_the_judge_change_note`.
  - `test_the_tally_counts_rejudged`.
- [ ] **Step 2-4: Run, implement, run `pytest tests/evals/test_release_regression.py -q`.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(evals): the regression check gives re-judged entries their own status"
  ```

## Phase D: report and publishing (D4-D7)

### Task 11: The report module

**Files:**
- Create: `src/coding_agent_playbook/evals/release_report.py`. If it grows past
  about 400 lines, split the Markdown into `release_report_markdown.py`.
- Modify: `src/coding_agent_playbook/evals/setup_digest.py`: `SCORING_EXEMPT`
  gets `"renders committed metrics; decides no score"` for each new report
  module.
- Test: `tests/evals/test_release_report.py`, with a golden file at
  `tests/fixtures/release_report/report.md`. Fixture history: 0.2.0, 0.3.0 and
  0.4.0, two targets, one judge change at 0.4.0.

**Interfaces:**
- Produces:
  - `load_history(releases_root: Path) -> MetricsHistory` (validated files by
    release, then by target).
  - `release_report(history: MetricsHistory, version: str) -> ReleaseReport`,
    which raises `ReleaseReportError(ExitTwoError)` naming the missing path and
    the versions that exist.
  - `ReleaseReport.markdown(limit: int = 120_000) -> str`. When over `limit`, it
    cuts at a section boundary and appends
    `"\n…truncated; the full report is report.md in the release assets.\n"`.
    The per-task table header is exactly
    `| task | previous pass rate | pass rate | Δ pass rate | previous mean | mean | Δ mean | regressions | improvements | carried | rejudged | new |`.
  - `ReleaseReport.csv_rows() -> list[dict[str, str]]`, with the D4 columns.
  - `ReleaseReport.agreement_rows() -> list[dict[str, str]]`.
  - `ReleaseReport.tasks: tuple[TaskDelta, ...]` and
    `ReleaseReport.trend: tuple[TrendPoint, ...]`, for the charts (Task 13).
  - `TaskDelta(target: str, task: str, previous_pass_rate: float | None, pass_rate: float, previous_mean: float | None, mean: float, counts: Mapping[str, int])`.
  - `TrendPoint(release: str, target: str, task: str, pass_rate: float, mean: float, judge_changed: bool)`.

- [ ] **Step 1: Write the failing tests**
  - `test_task_deltas_pool_passes_over_runs`.
  - `test_verdicts_match_check_regressions`: every sample status equals
    `check_regressions(new, previous)`.
  - `test_a_target_without_a_baseline_says_so` (Review Focus 5), and
    `test_a_dropped_target_is_ignored`.
  - `test_controls_are_a_separate_table`.
  - `test_the_trend_marks_the_judge_change`.
  - `test_csv_has_the_d4_columns_and_one_row_per_release_target_sample`.
  - `test_markdown_is_truncated_at_the_limit_with_a_pointer`.
  - `test_markdown_matches_the_golden_file`.
  - `test_an_unknown_version_names_the_versions_that_exist`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Reuse `check_regressions` for the verdicts, and
  `entries_summary`-style pooling for the pass rates.
- [ ] **Step 4: Run `pytest tests/evals/test_release_report.py -q`.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(evals): a release report of metric changes, trends and judge agreement"
  ```

### Task 12: The release PR body is the report

**Files:**
- Modify: `scripts/release_eval.py`: `metrics_body` returns the `_mode` lines
  then `release_report(load_history(...), version).markdown(limit=60_000)`
  under `## Release metrics`. The limit is half, to leave room for the rest of
  the PR body.
- Test: `tests/release/test_release_prepare_eval.py`

- [ ] **Step 1: Write the failing test** `test_the_pull_request_body_holds_the_change_report`: assert the body contains the per-task table header `"| task | previous pass rate | pass rate |"`.
- [ ] **Step 2-4: Run, implement, run.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(release): the release pull request shows the metric change report"
  ```

### Task 13: The bundle script

**Files:**
- Create: `scripts/release_report.py` (CLI `--version X --out DIR [--no-charts]`)
  and `scripts/release_report_charts.py` (matplotlib, imported only when charts
  are on).
- Test: `tests/release/test_release_report_script.py`

**Interfaces:**
- Consumes: `release_report`, `load_history` (Task 11).
- Produces: `build_bundle(checkout: Path, version: str, out: Path, *, charts: bool) -> list[Path]`.
  It writes the D5 files, plus `judge-agreement.csv` only when there are
  agreement rows.

- [ ] **Step 1: Write the failing tests**
  - `test_bundle_files_without_charts`: assert the sorted names are
    `["metrics-history.csv", "metrics/opus.json", "report.md"]` for a release
    without a judge change.
  - `test_metrics_files_are_byte_copies`.
  - `test_charts_are_written` (`pytest.importorskip("matplotlib")`): the three
    PNGs exist and are non-empty.
  - `test_no_baseline_writes_no_delta_charts`.
- [ ] **Step 2-4: Run, implement, run.**
  - Charts: paired horizontal bars per task (previous vs new; blue for new,
    gray for previous).
  - Sample grid: diverging blue-red with gray at 0 and every cell labelled.
  - Trend: one line per target, with a dashed vertical line at each
    `judge_changed` release.
  - Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(release): a script builds the release metric bundle with charts"
  ```

### Task 14: `release.py tag --github-output`

**Files:**
- Modify: `scripts/release_tag.py`: `tag_release` returns
  `TagResult(message: str, tagged: str | None)`. `tagged` is the version only
  on CREATE or PUSH.
- Modify: `scripts/release.py`: the `tag` command takes `--github-output PATH`
  and appends `version=<v>\n` when `tagged` is set.
- Test: `tests/release/test_release_tag.py` (or the existing tag tests).

- [ ] **Step 1: Write the failing tests**
  - `test_a_created_tag_writes_the_version_output`.
  - `test_an_existing_tag_at_the_commit_writes_nothing`.
  - `test_nothing_to_tag_writes_nothing`.
- [ ] **Step 2-4: Run, implement, run.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(release): the tag command reports the version it tagged for CI"
  ```

### Task 15: GitHub publishes the bundle

**Files:**
- Modify: `.github/workflows/ci.yml`:
  - `tag-release` passes `--github-output "$GITHUB_OUTPUT"` and exposes
    `outputs.version`;
  - a new `publish-release` job:
    - `needs: tag-release`;
    - `if: always() && (needs.tag-release.outputs.version != '' || github.event_name == 'workflow_dispatch')`.
      `always()` is needed because `tag-release` is skipped on dispatch, and a
      skipped need would skip this job too.
    - `V` is `${{ needs.tag-release.outputs.version || inputs.version }}`;
    - `permissions: contents: write`;
    - checks out the tag;
    - runs `pip install -e . matplotlib` and
      `python scripts/release_report.py --version $V --out release-report`;
    - then `gh release view "v$V" && { gh release upload "v$V" release-report/* --clobber; gh release edit "v$V" --notes-file release-report/report.md; } || gh release create "v$V" --title "v$V" --notes-file release-report/report.md release-report/*`;
  - `on.workflow_dispatch.inputs.version` (required string). `test`,
    `tag-release` and `playbook-ci` get
    `if: github.event_name != 'workflow_dispatch'` (merged into their existing
    conditions).
- Modify: `docs/checks.md` (or the release section of `docs/overview.md`):
  three lines on where the bundle appears and how to backfill.
- Test: `tests/integration/test_ci_publish_job.py`, in the same style as
  `test_ci_tag_job.py`.

- [ ] **Step 1: Write the failing tests**
  - `test_publish_needs_tag_release_and_runs_on_its_output`.
  - `test_publish_is_the_only_new_job_with_contents_write`.
  - `test_dispatch_takes_a_version`.
  - `test_publish_runs_on_dispatch_even_when_tag_release_is_skipped`: its `if`
    starts with `always() &&`.
  - `test_dispatch_skips_the_test_and_tag_jobs`.
  - `test_publish_updates_an_existing_release`: the run script contains
    `--clobber` and `gh release edit`.
  - `test_only_first_party_actions`.
- [ ] **Step 2-4: Run, implement, run `pytest tests/integration -q`.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(ci): publish each release's metric bundle as a GitHub Release"
  ```

### Task 16: GitLab publishes the bundle

**Files:**
- Modify: `.gitlab-ci.yml`:
  - stage `build`;
  - variable `RELEASE_CLI_IMAGE: "registry.gitlab.com/gitlab-org/release-cli:latest"`;
  - job `release-report` (rules `$CI_COMMIT_TAG =~ /^v\d+\.\d+\.\d+$/`;
    artifacts `release-report/`, `expire_in: never`);
  - job `release` (`needs: [release-report]`). It creates the release with
    `release-cli create`, with asset links to
    `$CI_PROJECT_URL/-/jobs/$REPORT_JOB_ID/artifacts/file/release-report/<file>`
    (the job id passed through a dotenv artifact). When creation fails because
    the release exists, it falls back to
    `curl --request PUT ... /releases/$CI_COMMIT_TAG` with `JOB-TOKEN`.
- Test: `tests/integration/test_gitlab_release_jobs.py` (parse the YAML).

- [ ] **Step 1: Write the failing tests**
  - `test_release_jobs_run_only_on_version_tags`.
  - `test_release_needs_the_report_job`.
  - `test_images_are_variables`.
  - `test_the_report_artifacts_never_expire`.
- [ ] **Step 2-4: Run, implement, run.** Expected: PASS.
- [ ] **Step 5: Commit**

  ```bash
  git commit -m "feat(ci): publish each release's metric bundle as a GitLab Release"
  ```

### Task 17: Whole-branch gate and backfill notes

- [ ] **Step 1:** Run the full gate (Global Constraints) in Python 3.12 and 3.13,
  without extras. Expected: green.
- [ ] **Step 2:** Run `python scripts/release_report.py --version 0.4.0 --out /tmp/rr`
  and open `report.md` and the PNGs. The bundle must hold v0.4.0 against 0.3.0,
  with no judge change.
- [ ] **Step 3:** Open the PR. After merge, the maintainer runs
  `workflow_dispatch` for 0.2.0, 0.3.0 and 0.4.0 on GitHub, then *Run pipeline*
  on those tags on GitLab.
