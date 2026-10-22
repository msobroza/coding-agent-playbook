# Checks and evals

The code-quality metrics gate, the commit-message convention, `playbook ci` and the eval runner. Back to the [README](../README.md).

## Code-quality metrics gate

`playbook metrics` is a standalone, **opt-in** code-quality gate. It measures Python with deterministic static metrics — cyclomatic complexity, weighted methods per class (WMC), LCOM4, depth of inheritance, an approximate coupling-between-objects, and (with the optional extra) the maintainability index — and grades the result either against absolute thresholds or, by default, as a **non-regression** check against a baseline. It is independent of `playbook sync`: nothing about your generated assistant context depends on it.

```bash
playbook metrics                              # measure src/ against absolute thresholds
playbook metrics --baseline git:HEAD          # fail if the working tree worsens vs HEAD
playbook metrics src tests --format json      # machine-readable findings
playbook metrics --strict                     # promote warnings to failures (non-zero exit)
playbook metrics --baseline git:origin/main --changed   # only the files a branch changed
```

It exits `0` on pass, `1` on a breach, and `2` on a usage error (bad path, bad baseline, malformed `[metrics]` config). Defaults and per-metric thresholds live in a `[metrics]` table in `.coding-agent-playbook.toml`. Under the hood each metric is wrapped in a **check** (a threshold or non-regression grader) and the checks are folded into one **rubric** report — the `Metric` / `Check` / `Rubric` model (see SPEC §21). The same `[metrics]` policy drives the pre-commit hook, the `metrics` step of [`playbook ci`](#playbook-ci) and the quality Stop stages of the lifecycle hooks, and it is read from the committed config only.

### The metrics

| Metric | Families | Selected | Measures |
| --- | --- | --- | --- |
| `cyclomatic_complexity` | `quality` | by default | 1 + the decision points of each function |
| `wmc` | `quality` | by default | the summed complexity of a class's methods |
| `lcom4` | `quality` | by default | class cohesion: groups of methods sharing no attribute |
| `dit` | `quality` | by default | depth of inheritance |
| `cbo` | `quality` | by default | coupling between objects (approximate) |
| `maintainability_index` | `quality` | by default (needs `radon`) | the SEI maintainability index, 0–100 |
| `ruff_violations` | `quality`, `docstrings` | opt-in, by name | ruff findings per file and code family: `quality` (C901, PLR0911, PLR0912, PLR0913, PLR0915), `docstrings` (D100–D107); needs `ruff` on `PATH` |
| `file_sloc` | `quality` | opt-in, by name (needs `radon`) | source lines per file |
| `docstring_example` | `docstrings` | opt-in, by name | whether each public function's docstring carries a usage example |
| `test_pass_rate` | `testing` | with `--run-tests` | the share of passing tests |
| `coverage` | `testing` | with `--run-tests` | line coverage per file and in total |
| `diff_coverage` | `testing` | with `--run-tests` | the share of the changed executable lines the suite ran |

Select with `--select` / `--extend-select` / `--ignore` (or the `select`,
`extend_select` and `ignore` keys of `[metrics]`), naming metrics or the
families `quality`, `docstrings` and `testing`. A family expands to its
default members only, so an opt-in metric is selected by its own name: an engine
upgrade never changes what an existing `[metrics]` measures. `--changed` limits
a `git:` baseline run to the Python files changed against it.

### Clean Code for AI Agents preset

Code an agent edits stays legible when functions stay short, nesting and
argument lists stay small, files stay under a few hundred lines and public
functions carry a docstring with a usage example. This turns those budgets
into the gate, without editing your own ruff configuration:

```toml
# .coding-agent-playbook.toml
[metrics]
extend_select = ["ruff_violations", "file_sloc", "docstring_example"]   # opt-in, by name

[metrics.ruff_violations]   # --config for the gate's and the post-edit feedback's ruff calls only
config = { "lint.mccabe.max-complexity" = 10, "lint.pylint.max-args" = 5, "lint.pylint.max-statements" = 20 }

[metrics.thresholds.file_sloc]   # 1.0 up to 300 source lines, 0.0 at 800
warn = 1.0                       # warn above 300 lines
fail = 0.6                       # fail above 500 lines
```

Under the default non-regression mode, existing code that already breaks a
budget stays quiet; only a change that makes a file worse fails.

### Running tests and coverage (`--run-tests`)

`--run-tests` additionally runs the **execution** metrics — `test_pass_rate`, `coverage` and `diff_coverage` — which shell out to your project's own `pytest` (and `pytest-cov`) and parse the standard junit/coverage XML. These have side effects and cost, so they are **opt-in and never part of the default pre-commit hook**; run them in CI or on demand:

```bash
playbook metrics --run-tests                          # also run the suite + measure coverage
playbook metrics --run-tests --baseline git:HEAD      # fail on new test failures / coverage drop
playbook metrics --run-tests --test-cmd "pytest -q"   # override the test command
playbook metrics --run-tests --select testing --baseline git:HEAD   # the playbook-coverage hook
```

`diff_coverage` grades the change, not the whole file: the changed executable lines must be at least 80% executed. Test files and `[metrics] exclude` are never scored, and a change with no executable line passes without a fake 100%. `[metrics] run_tests = true` makes `--run-tests` the default for CI and manual runs; `--no-run-tests` overrides it, and the `playbook-metrics` pre-commit hook always passes it, so a commit never runs your suite. The engine adds no dependency for this — your target project supplies `pytest`/`pytest-cov`.

### The `metrics` optional extra (maintainability index)

The core gate is **stdlib-only** and runs with nothing extra installed. The maintainability index is the one metric backed by [`radon`](https://radon.readthedocs.io/), so it ships as an optional extra; without it that single metric is transparently skipped:

```bash
pip install 'coding-agent-playbook[metrics]'   # adds radon for maintainability_index
```

## Commit-message convention (commitizen)

The playbook has no commit-message linter of its own: the convention is
[commitizen](https://commitizen-tools.github.io/commitizen/)'s, configured where
commitizen reads it, and every check calls `cz check`. Add commitizen to your
dev tools (`uv add --dev commitizen`), then declare the convention:

```toml
# pyproject.toml
[tool.commitizen]
name = "cz_conventional_commits"   # commitizen's default; use cz_customize + schema_pattern for your own
```

A repo with history that predates the convention sets a cut-over date, so old
commits are grandfathered:

```toml
# .coding-agent-playbook.toml
[hooks.commit_convention]
cutover_date = "2026-10-15"   # "YYYY-MM-DD", quoted: an unquoted TOML date is an error
```

Range checks skip every commit whose **committer** date is before
`cutover_date`; a commit rebased or amended after it counts as new and must
conform. Unset, every commit is checked. The convention is then enforced in
three places:

- the `playbook-commit-msg` pre-commit hook checks every new commit message,
  yours included, with no cut-over (install the `commit-msg` hook type);
- the `commit-message-convention` lifecycle hook denies an assistant's
  `git commit` whose message fails; with
  `[hooks.commit-message-convention] check_push = true` it also denies a
  `git push` whose commits after the cut-over fail (off by default: the
  commit check and `playbook-commit-msg` already see every new commit, and
  the scan can take seconds per push);
- the `commit-convention` step of `playbook ci` checks the branch's commits
  after the cut-over, plus the pull-request title when `PLAYBOOK_PR_TITLE` is
  set (in a squash-merge repo the title becomes the commit subject).

A missing `cz` fails the CI step and the pre-commit hook loudly; the lifecycle
hook fails open with a once-per-session hint to install it.

## `playbook ci`

`playbook ci` is the one required status check: it runs every off-workstation
twin of the lifecycle hooks against the merge base with the default branch,
each step as a child process (no shell, a timeout per step), and reports all of
them, with no fail-fast.

```bash
playbook ci                                   # every applicable step vs the default branch
playbook ci --base origin/main --steps validate,scan-secrets
playbook ci --steps scan-sinks                # --steps also switches on opt-in steps
playbook ci --format json                     # one {step, argv, exit, duration_s, status} per step
```

| Step | Runs | When |
| --- | --- | --- |
| `sync-check` | `playbook sync --check` | `[output] commit = true` only: under the default, a fresh clone has no output to compare |
| `validate` | `playbook validate` | always |
| `metrics` | `playbook metrics --baseline git:<merge base> --changed --no-run-tests` | always (static, never the suite) |
| `coverage` | `playbook metrics --run-tests --select testing --baseline git:<merge base>` | `[metrics] run_tests = true`, or `--steps coverage` |
| `gate-scan` | `playbook gate-scan`: new suppressions, skipped tests, loosened checker config | always |
| `scan-secrets` | `playbook scan-secrets` over the branch | always |
| `commit-convention` | `cz check` on the commits after `cutover_date`, plus `$PLAYBOOK_PR_TITLE` | `[tool.commitizen]` or `[hooks.commit_convention]` is set |
| `commit-trailers` | `playbook check-commit-trailers` over the branch | a commit-trailer row is configured |
| `check-deps` | `playbook check-deps`: newly declared dependencies against your policy | a dependency policy is configured |
| `scan-sinks` | `playbook scan-sinks` over the branch | only when `--steps` names it |

It exits `0` when every step that ran passed, `1` when one failed or timed out,
and `2` on a usage error or an unresolvable base. The job needs the full history
(`fetch-depth: 0`), and the pull-request title is attacker-controlled text: pass
it **only through `env:`**, never inside a `run:` line, so it cannot inject shell
commands:

```yaml
# .github/workflows/ci.yml
jobs:
  playbook-ci:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0                 # playbook ci diffs <merge base>..HEAD
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install the project with its dev tools (coding-agent-playbook, commitizen)
        run: python -m pip install -e ".[dev]"
      - name: playbook ci
        run: playbook ci --base origin/main
        env:
          PLAYBOOK_PR_TITLE: ${{ github.event.pull_request.title }}
```

## Running evals

`playbook eval` enumerates the prompt-to-sample graph (`--list` / `--show`); with `--run` (v1.1) it **executes** a single sample end-to-end against an agent and grades it:

```bash
playbook eval refactor-extract-helper --run --runner claude_code   # real: drive the Claude Code CLI
playbook eval refactor-extract-helper --run --runner opencode       # real: drive the OpenCode CLI
playbook eval refactor-extract-helper --run --runner fake          # hermetic demo / CI: no network, no CLI
playbook eval refactor-extract-helper --run --judge llm --judge-samples 3 # also score [rubric] via an LLM judge
playbook eval refactor-extract-helper --run --full-scoring          # run every check (no short-circuit)
playbook eval refactor-extract-helper --run --prompt-set v2         # grade the v2 prompt set (default v1)
playbook eval refactor-extract-helper --run --format json          # machine-readable report
```

A sample declares its success criteria as **layers** (SPEC §6.5.3): a deterministic `[gate]` (file + metric checks composed by a tiny boolean `expr`), an optional llm-judge `[rubric]` (weighted criteria), a `[verdict]` (a boolean expression over the two layers), and an optional cross-trial `[aggregate]` (`pass@k` / `pass^k`). They compile into one **rubric** of checks (the `Metric` / `Check` / `Rubric` model, SPEC §21): the `[gate]` layer — file predicates (`file_exists` / `file_contains` / `file_unchanged` / `file_forbidden`) and static/execution metric checks (0–1 normalized thresholds, non-regression vs the `setup/` baseline) — is scored **deterministically** into one report, rendered like `playbook metrics`, and the per-trial verdict is **derived** from the layer results. Two opt-in real runners ship — `claude_code` (the default, drives the `claude` CLI) and `opencode` (drives the `opencode` CLI) — both `available()`-gated on their binary and never exercised in CI; `--runner fake` is the hermetic driver for demos and CI. There is no `--run-tests` flag — a sample runs the suite iff its `[gate]` references an execution metric (`coverage` / `test_pass_rate`). Exit `0` on a passing report, `1` on a failing one, `2` on a usage error (unknown sample/runner/judge, or a real runner or judge whose CLI is not on `PATH`) or when the sample cannot be scored at all (its prompt fails to render, or the judge gives no score after its retries). Judged scores are labelled uncalibrated (a note in the text report, `"uncalibrated_judge": true` in JSON). Judged `[rubric]` scoring (v1.1 R2) is **opt-in via `--judge`**: pick a judge from the `coding_agent_playbook.judges` group (the shipped `llm` shells out to the `claude` CLI, `available()`-gated), and `--judge-samples N` averages N gradings per criterion (the old `samples` spelling of the flag is a deprecated alias until the next release). Omit `--judge` for a deterministic-only run (the rubric layer skips; a skipped layer is neutral in the verdict). A cost-tiered scheduler runs the cheap deterministic checks first and **short-circuits once the gate is lost** — so with the default `gate and rubric` verdict a failing file/metric check never spends an LLM call (a sample whose verdict or aggregate a skipped layer could change, e.g. `gate or rubric`, is always scored in full); `--full-scoring` forces every check to run for a complete report.

A handle can also `{ref = "name"}` a **named gate or rubric** instead of inlining: in the `[gate]` layer it resolves a composed boolean gate registered via `@register_gate` (the `coding_agent_playbook.gates` group), in the `[rubric]` layer a code-defined `Rubric` subclass registered via `@register_rubric` (the `coding_agent_playbook.rubrics` group) — so several tasks share one gate/rubric by name. The engine ships no builtin gates or rubrics; both are third-party extension points.
