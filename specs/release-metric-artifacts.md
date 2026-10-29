# Release metric artifacts and reuse of every committed eval result

Status: approved 2026-10-29, then amended the same day so a judge change re-grades
stored answers (D8-D11). Decision record: ADR 0014, amending ADR 0013.

## Problem

- **Nobody sees how the metrics moved.** `scripts/release.py prepare --eval`
  records one metrics file per target under `catalog/releases/<version>/metrics/`,
  and CI tags the release commit. Nothing is published: no release page, no
  report of what changed since the previous release, no charts, no trend.
- **Reuse looks one release back only.** ADR 0013 carries a sample when its
  inputs digest and the setup digest match the *previous release's* file of the
  *same target*. A result measured earlier with the same task, model, parameters
  and sample is paid for again. That happens when it was measured in an older
  release, after a setup that changed and changed back, or under another target
  name.
- **A judge change reruns everything.** The judge is part of the setup digest,
  and the records keep no answers, so a new judge cannot re-grade old runs. Every
  agent run is paid for again, and nothing shows whether the new judge grades
  like the old one.

## Goals

1. Every release publishes a **metric-change bundle** on both GitHub and GitLab:
   - a change report;
   - charts;
   - trends across all releases;
   - the raw data.
2. A record run **never recomputes a sample already measured** with the same
   inputs and setup in any committed release.
3. The maintainer still runs the paid evals (`prepare --eval`). CI runs no paid
   call and needs no model key or harness CLI.
4. A **judge change costs only judge calls**. The new judge re-grades the stored
   answers, and the release reports how closely it agrees with the old judge.

## Non-goals

- Running evals in CI.
- A result store outside `catalog/releases/`: benchmark and ad-hoc runs do not
  feed the reuse.
- Pinning harness versions. A new harness version is a new setup and still
  reruns every sample.
- Blocking a release on judge disagreement: agreement is reported, never gated.
- Re-grading on a judge-prompt or other scoring-code change. That stays a full
  rerun, because the scoring digest changes.
- A GitLab job that creates the tag. GitLab publishes on any `v*` tag pipeline,
  however the tag arrived (a mirror, or `scripts/release.py tag`).

## Terms

- **Task**: a prompt id with eval samples (`review`, `explain`, ...): the
  `prompt_id` of a metrics entry.
- **Inputs digest, setup digest, carried entry, `measured_in`**: as in ADR 0013.
  The setup digest covers:
  - the harness and its version;
  - the model;
  - the endpoint fingerprint;
  - the judge model, its effort and its sample count;
  - runs and fail-fast;
  - isolation;
  - the scoring code.

  It does not cover the target's name.
- **Result index**: every committed release metrics file, indexed for reuse.
- **Judge parts** of the setup: `judge_model`, `judge_endpoint_fingerprint`,
  `judge_samples`, `judge_version` and `judge_reasoning_effort`.
- **Agent-compatible file**: a committed metrics file whose setup differs from
  this run's in judge parts only.
- **Answers file**: `catalog/releases/<v>/answers/<target>.jsonl.gz`, the stored
  answers of one release's fresh runs (D8).
- **Re-judged entry**: a sample whose stored answers the new judge graded again
  (D9).

## Decisions

### D1. `--carry-from` takes the releases directory

`playbook eval --run --all --record OUT --carry-from catalog/releases` builds a
**result index** before any paid run:

- It reads every `catalog/releases/*/metrics/*.json`, of any target name.
- It skips a file that fails `validate_release_metrics`, records no setup digest,
  or whose setup parts differ from this run's (`differing_setup_parts`).
  `UNKNOWN_VERSION` never matches, as today.
- From every remaining file it indexes the entries that record an inputs digest,
  by `(sample id, inputs digest)`.
- When several files hold the same key, the **newest release wins** (SemVer
  order of the directory names). Within one release, the target's own file wins,
  then the other names in sorted order.

For each sample of the run:

- **Edition control**: always reruns, as today.
- **Key found**: a *carried entry*, built with `carried_entry`. Its `measured_in`
  is the entry's own when it was already carried, else the source file's release
  and commit. The plan line names the source, for example
  `review/x: carried from 0.3.0 (opencode-qwen)`.
- **Key not found**: reruns. The reason is `new sample` when no indexed file has
  the sample id, else `inputs digest changed`.
- **No usable file at all**: every sample reruns, and the reason lists why each
  file was skipped. The first three are named and the rest counted, for example
  `the setup differs in harness_version`.

`--carry-from FILE` keeps today's meaning (one baseline, same target name), so
nothing that passes a file changes. `reported_model` comes from the
newest source file that a carried entry came from.

A fully matching file always wins over an agent-compatible one. Agent-compatible
files are used only by D9, for keys that no fully matching file holds.

### D2. The regression check still compares with the previous release

`check_regressions(new, previous)` keeps the previous release's file for the
same target as its baseline. A carried entry whose source is not that file needs
a new rule:

- It is `carried` (never blocks) only when its inputs digest equals the previous
  file's entry for that sample.
- Otherwise its scores differ from the previous release's, for example after a
  revert to older text. It is compared like a rerun (`regression`,
  `improvement`, `ok`) and noted `measured in <release>`.

This closes the hole where a revert could hide a regression behind `carried`.

D11 adds the `rejudged` status.

### D3. `prepare --eval` passes the releases directory

`scripts/release_eval.py` passes `catalog/releases` instead of the previous
release's file. `--full` still passes nothing. The record writes each target's
answers file into `catalog/releases/<v>/answers/` (D8).

The release pull request's `Release metrics` section is the change report of D4,
up to `ReleaseReport.markdown(limit=...)` characters with a pointer to the full
bundle. The `N rerun, M carried` line now also says where the carried entries
come from, for example `M carried (K from older releases)`.

### D4. The report data lives in the engine

A new pure module, `coding_agent_playbook.evals.release_report`. It does no
plotting and adds no dependency.

It lives in `evals`, not in `release`, because it reuses `check_regressions` and
the `release` layer sits below `evals` (import-linter `engine-layers`). Like
every top-level `evals` module, it joins `SCORING_EXEMPT` with its reason ("renders
committed metrics; decides no score"), or the setup-digest guard test fails. D1's
index code also goes in `evals`, as `evals.result_index`, and joins the same list.

- `load_history(catalog_root) -> MetricsHistory`: every release's metrics files,
  validated, in SemVer order, per target name.
- `release_report(history, version) -> ReleaseReport`. For each target of
  `version`:
  - **Baseline**: the latest earlier release with a file for that target, or
    `None`.
  - **Per-sample verdicts**: `check_regressions`, so the report and the release
    gate always agree. The accepted reasons are stored.
  - **Per task**:
    - previous and new pass rate (`sum(passes) / sum(runs)`);
    - mean score;
    - delta;
    - counts of `regression`, `improvement`, `ok`, `carried`, `rejudged`, `new`,
      `not_comparable`.
  - **Edition controls**: a separate table.
  - **Trend**: per task, the pass rate and mean score in every release that has
    a file for the target, with each release whose judge changed marked.
  - **Judge change** (D10): the agreement numbers, when the file records them.
- `ReleaseReport.markdown() -> str`, which renders:
  1. a headline per target: pass rate and mean score with the delta, then
     `rerun / carried`, the setup line, and any regressions with their accepted
     reasons;
  2. a per-task table;
  3. the samples that changed;
  4. the controls;
  5. the judge change, when there is one;
  6. a trend table.

  Carried samples are counted, not listed.
- `ReleaseReport.csv_rows()`: one row per release × target × sample over the
  whole history. Columns:
  `release, target, task, sample, passes, runs, pass_rate, mean_score,
  delta_mean, verdict, measured_in_release, rejudged_from_release, judge_model,
  inputs_digest, setup_digest`.
- `ReleaseReport.agreement_rows()`: one row per task of each target with a judge
  change. Columns:
  `release, target, task, runs, pass_agreement, mean_abs_score_diff,
  old_judge, new_judge`.
  `delta_mean` and `verdict` are empty for a release with no baseline.

### D5. The bundle script adds charts

`scripts/release_report.py --version X --out DIR` (needs matplotlib) writes:

| File | Content |
|---|---|
| `report.md` | `ReleaseReport.markdown()`; also the release description |
| `metrics-history.csv` | `csv_rows()` |
| `metrics/<target>.json` | the release's files, byte copies |
| `task-deltas.png` | per target: previous vs new pass rate per task (paired bars) |
| `sample-deltas.png` | rows are samples that were not carried, columns are targets; cell color is the mean-score delta (diverging blue-red, gray at 0, labelled) |
| `task-trend.png` | per task: pass rate over releases, one line per target; a dashed vertical line at each judge change |
| `judge-agreement.csv` | `agreement_rows()`; written only for a release with a judge change |

- A release with no baseline writes no delta charts, and its report says so.
- `--no-charts` skips the PNGs, so the bundle can be built without matplotlib.
- Charts follow the repo's dataviz conventions:
  - status colors are never used for series;
  - every series is labelled;
  - there is no dual axis.

### D6. GitHub publishes in the tagging workflow

A tag pushed with `GITHUB_TOKEN` starts no workflow, so publishing runs in the
same workflow as tagging:

- **`tag-release` outputs the version** only when this run created or pushed the
  tag (new `--github-output` flag on `scripts/release.py tag`). It outputs
  nothing for "nothing to tag" and for "already points at the commit". The
  latter is what every later push to `main` gets, and it must not republish the
  release.
- **New job `publish-release`** has `needs: tag-release`, `if: version output !=
  ''` and `permissions: contents: write`. It:
  1. checks out the tag;
  2. runs `pip install -e . matplotlib`, then `python scripts/release_report.py
     --version X --out release-report`;
  3. runs `gh release create vX --title vX --notes-file release-report/report.md
     release-report/*`.

  When the release already exists, it runs `gh release upload --clobber` and
  `gh release edit --notes-file` instead, so a rerun is safe. The notes stay
  under GitHub's 125,000-character body limit through `markdown(limit=...)`.
- **Backfill:** `workflow_dispatch` with a `version` input runs `publish-release`
  alone for an existing tag. It is used once for v0.2.0, v0.3.0 and v0.4.0.

### D7. GitLab publishes on tag pipelines

New jobs in `.gitlab-ci.yml`, both with rules `if: $CI_COMMIT_TAG =~
/^v\d+\.\d+\.\d+$/`:

- **`release-report`** (stage `build`, image `$PYTHON_IMAGE`) builds the bundle
  into `release-report/` as artifacts that never expire.
- **`release`** (stage `deploy`, image `$RELEASE_CLI_IMAGE`, a variable so a
  company registry can supply it) uses `needs: [release-report]`. It creates the
  GitLab Release for `$CI_COMMIT_TAG`:
  - its description is `release-report/report.md`;
  - its asset links point to the job artifacts
    (`$CI_PROJECT_URL/-/jobs/<id>/artifacts/file/release-report/<file>`).

  On a rerun, it updates the existing release through the Releases API instead
  of failing.

`PIP_INDEX_URL` and the image variables keep working behind the company proxy,
as for the docs jobs. A tag pipeline started by hand from the GitLab UI (*Run
pipeline* on the tag) backfills older tags.

### D8. Releases keep their answers

Every record run stores, for each sample and run, one JSON line in an answers
file (gzip):

| Key | Content |
|---|---|
| `sample`, `inputs_digest`, `run` | the sample id, its inputs digest, the run index |
| `artifact` | what the judge graded: the transcript or the diff, after the runner's token redaction. `null` when fail-fast skipped the judge (D9 never re-grades such a run), and for a re-judged run, whose `artifact_ref: {release, target}` names the answers file that holds it |
| `checks` | each judge-free check's result by check id: file checks, answer patterns, the test pass rate |
| `criteria` | each rubric criterion with its weight and the judge's mean score, `null` when fail-fast skipped the judge |
| `judge` | the judge parts this run was graded with |

- `playbook eval --record OUT` writes the answers beside `OUT`, as
  `OUT.answers.jsonl.gz`, or at `--answers PATH`.
- `prepare --eval` writes them to `catalog/releases/<v>/answers/<target>.jsonl.gz`.
- A file holds only that release's fresh runs. A carried entry's answers stay in
  the release its `measured_in` names, so nothing is stored twice.
- The format is read and written by one module, `evals.answers_store`. It joins
  `SCORING_EXEMPT` ("stores answers; `evals.rejudge` decides the scores").
- `catalog/releases/` is already outside ruff, so nothing reformats the files.
- Expected size: about 1 MB per target per release.

### D9. A judge change re-grades the stored answers

For a key that no fully matching file holds but an agent-compatible file does,
and whose answers are stored in the release its entry was measured in:

1. The new judge grades every stored run's `artifact` on each rubric criterion.
   This costs judge calls only; no agent runs.
2. `evals.rejudge` recomputes each run's gate and rubric from the stored `checks`
   and the new criterion scores, with the sample's own gate and rubric
   expressions. It then folds the entry exactly as a fresh record would: passes,
   mean score, checks.
3. The entry records `rejudged_from: {release, commit, judge}`, naming the
   release whose answers it used and the old judge parts. It keeps
   `measured_in` for the answers' origin.

Other cases:

- **No stored answers** (v0.4.0 and older, or a missing or unreadable answers
  file): the sample reruns, with the reason `answers not stored`.
- **A run that failed its gate under fail-fast** is not re-graded. Fail-fast is
  not a judge part, so the setup still runs fail-fast and the verdict is still a
  fail. Its old criterion scores are `null`, so it counts in no agreement figure.

`evals.rejudge` decides scores, so it joins `SCORING_MODULES`. The summary adds a
`rejudged` count next to `rerun` and `carried`.

### D10. Judge agreement is measured and reported, never gated

For every re-judged run with old criterion scores, the record compares the old
and the new judge on:

- **pass agreement**: the share of runs whose rubric verdict (pass/fail) is the
  same;
- **mean absolute score difference** of the weighted rubric score.

The metrics file stores the result under `judge_change`:
`{from: <judge parts>, to: <judge parts>, runs, pass_agreement,
mean_abs_score_diff, tasks: {<task>: {runs, pass_agreement, mean_abs_score_diff}}}`.
It is written only when at least one entry was re-judged.

- The record prints one line before writing:
  `judge change: <old> -> <new>: pass agreement 93% over 96 runs, mean |Δ| 0.04`.
- The release PR and the report show the same numbers.
- Nothing blocks on them.

### D11. The regression check across a judge change

- A re-judged entry gets the status `rejudged`. It never blocks. Its delta is the
  new judge's mean minus the previous entry's, which is the judge effect alone,
  since the answers are the same.
- When the file records `judge_change`, the check adds a note to every compared
  (rerun) sample, so the previous release's scores are read with that in mind:
  `judge changed since <previous>: pass agreement <x>%`.
- `--accept` refuses a `rejudged` sample, as it refuses `carried`.

## Data flow

```mermaid
flowchart LR
  M["maintainer: release.py prepare --eval"] -->|"--carry-from catalog/releases"| I[result index]
  I --> R["record: rerun changed, carry the rest, re-judge on a judge change"]
  A["catalog/releases/*/answers/*.jsonl.gz"] --> R
  R --> F["catalog/releases/X/metrics/*.json + answers/*.jsonl.gz (release PR)"]
  F --> T["merge → CI tags vX"]
  T --> B["release_report.py: report.md, CSV, PNG, JSON"]
  B --> GH[GitHub Release vX]
  B --> GL[GitLab Release vX]
```

## Errors

- An unreadable or invalid metrics file in the index is skipped, and the plan
  names it. `--carry-from FILE` still refuses a bad file, as today.
- `release_report` raises `ReleaseReportError(ExitTwoError)` when `version` has
  no metrics directory. The message names the path and the versions that have
  one.
- An unreadable answers file, or a line that fails its schema, makes the samples
  it holds rerun, with the reason `answers unreadable: <path>`. It never makes up
  scores.
- A judge error during re-grading is handled like one during a fresh record: the
  record fails, and the checkpoint keeps finished samples for `--resume`.
- A publish job that fails leaves the tag in place. Rerunning the job is safe:
  it creates the release, or updates it when it exists.

## Testing

All engine tests run headless with `pytest`, using small fixture metrics files
under `tests/fixtures/release_metrics_history/`.

- **Result index:**
  - setup match and mismatch;
  - the newest release wins;
  - target-name order within a release;
  - a file without setup or inputs digests is skipped;
  - `UNKNOWN_VERSION` never matches;
  - edition controls always rerun;
  - `measured_in` is kept through a second carry;
  - `--carry-from FILE` behaves as before;
  - the plan lines name the source.
- **D2**: a carried entry from an older release whose digest differs from the
  previous file's entry is compared, so a regression blocks. One equal to it
  stays `carried`.
- **Answers store:**
  - a write and read round trip, gzip, one line per run;
  - fail-fast runs store `null` criterion scores;
  - carried entries write no lines;
  - an unreadable file or a bad line is reported, never guessed.
- **Re-judge**, with a `StubJudge` returning fixed scores:
  - a judge-only setup difference re-grades, with no runner call;
  - a fully matching file still wins over an agent-compatible one;
  - the gate comes from the stored checks;
  - the rubric verdict follows the new scores;
  - a file without answers reruns;
  - `rejudged_from` and `measured_in` are recorded;
  - the summary counts `rejudged`;
  - any non-judge setup difference still reruns.
- **Agreement:** the pass agreement and mean |Δ| on hand-computed fixtures; the
  per-task split; no `judge_change` key without re-judged entries.
- **D11:** `rejudged` never blocks; `--accept` refuses it; rerun samples carry the
  judge-change note.
- **Report:**
  - per-task aggregates and deltas;
  - agreement with `check_regressions`;
  - a release without a baseline;
  - controls;
  - the trend table;
  - CSV columns and row count;
  - the Markdown limit truncates with a pointer;
  - a golden Markdown file for one fixture history.
- **Script:** the bundle file list with `--no-charts`. The chart tests use
  `pytest.importorskip("matplotlib")`, since the CI test job installs no
  matplotlib.
- **`release.py tag --github-output`** writes `version=<v>` when it created or
  pushed the tag, and nothing for "nothing to tag" or "already points at the
  commit".
- **CI wiring**, pinned like `tests/integration/test_ci_tag_job.py`:
  - `publish-release` needs `tag-release` and runs only on its output;
  - it is the only new job with `contents: write`;
  - `workflow_dispatch` takes a `version`;
  - the GitLab jobs run only on `v*` tags.

  The jobs' behavior is checked once with `workflow_dispatch` on v0.4.0.

## Rollout

1. ADR 0014, D1, D2, D3 and D8: the engine and `prepare`. The next release's
   evals reuse every committed result and store their answers.
2. D9, D10 and D11: re-judging. This is useful from the release after the first
   one with stored answers.
3. D4: the report module, and the release PR body uses it.
4. D5: the bundle script.
5. D6: GitHub publishing, then backfill v0.2.0, v0.3.0 and v0.4.0.
6. D7: GitLab publishing, verified on the internal GitLab.

## Open questions

None at the time of writing.
