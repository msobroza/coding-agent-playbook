# Review benchmark: `review-qwen3.6-27b`

Agent: `qwen/qwen3.6-27b` through OpenRouter, in OpenCode and Claude Code. Judge: `claude-opus-5-5` (medium effort). One trial per sample; a sample passes when its gate and its rubric both pass.

| Reviewer | Passed | Gate passed | Rubric passed | Mean judge score | Median agent time | Runs that edited files |
|---|---|---|---|---|---|---|
| OpenCode /review | 2/14 | 2/14 | 12/14 | 0.76 | 81 s | 0/14 |
| OpenCode + playbook v0.1.0 | 5/14 | 6/14 | 7/14 | 0.57 | 52 s | 0/14 |
| OpenCode + playbook v0.2.0 | 13/14 | 14/14 | 13/14 | 0.83 | 168 s | 1/14 |
| OpenCode + playbook v0.3.0 | 8/14 | 10/14 | 9/14 | 0.64 | 107 s | 0/14 |
| Claude Code /code-review | 2/14 | 2/14 | 10/14 | 0.61 | 217 s | 0/14 |
| Claude Code + playbook v0.2.0 | 14/14 | 14/14 | 14/14 | 0.85 | 138 s | 0/14 |
| Claude Code + playbook v0.3.0 | 14/14 | 14/14 | 14/14 | 0.88 | 252 s | 0/14 |

## By sample set (passed, mean judge score)

| Sample set | OpenCode /review | OpenCode + playbook v0.1.0 | OpenCode + playbook v0.2.0 | OpenCode + playbook v0.3.0 | Claude Code /code-review | Claude Code + playbook v0.2.0 | Claude Code + playbook v0.3.0 |
|---|---|---|---|---|---|---|---|
| original (6 samples) | 2/6 (0.89) | 5/6 (0.83) | 6/6 (0.93) | 3/6 (0.66) | 2/6 (0.66) | 6/6 (0.87) | 6/6 (0.97) |
| CRBugBench (8 samples) | 0/8 (0.67) | 0/8 (0.35) | 7/8 (0.74) | 5/8 (0.63) | 0/8 (0.57) | 8/8 (0.83) | 8/8 (0.81) |

## CRBugBench-style detection (samples with one known defect)

Did the review catch the known defect? Strict counts the judge's `yes`; lenient counts `yes` as 1 and `partial` as 0.5; top-5 is a `yes` whose first matching comment is among the review's first five. Passed is this benchmark's gate-and-rubric verdict on the same runs.

| Reviewer | Runs | Passed | Strict detection | Lenient detection | Found in first 5 comments | Median first match | Comments per review |
|---|---|---|---|---|---|---|---|
| OpenCode /review | 8 | 0% | 75% | 81% | 75% | 1 | 1.8 |
| OpenCode + playbook v0.1.0 | 8 | 0% | 25% | 56% | 25% | 1 | 3.4 |
| OpenCode + playbook v0.2.0 | 8 | 88% | 88% | 94% | 88% | 1 | 5.4 |
| OpenCode + playbook v0.3.0 | 7 | 71% | 71% | 71% | 71% | 1 | 2.3 |
| Claude Code /code-review | 8 | 0% | 88% | 94% | 88% | 1 | 6.1 |
| Claude Code + playbook v0.2.0 | 8 | 100% | 100% | 100% | 100% | 1 | 5.9 |
| Claude Code + playbook v0.3.0 | 8 | 100% | 100% | 100% | 100% | 1 | 5.0 |

No detection verdict (the judge refused or failed): OpenCode + playbook v0.3.0 / crbug-form-method-none.

## Did the second pass run? (v0.3.0 and later)

- OpenCode + playbook v0.3.0: 9 of 14 runs
- Claude Code + playbook v0.3.0: 14 of 14 runs; 15 of 28 subagent starts in the background

## Per sample (verdict, judge score)

| Sample | OpenCode /review | OpenCode + playbook v0.1.0 | OpenCode + playbook v0.2.0 | OpenCode + playbook v0.3.0 | Claude Code /code-review | Claude Code + playbook v0.2.0 | Claude Code + playbook v0.3.0 |
|---|---|---|---|---|---|---|---|
| change-drops-part-of-request | FAIL (0.81) | pass (0.95) | pass (0.87) | pass (0.96) | FAIL (0.68) | pass (0.86) | pass (0.90) |
| clean-multi-file-change | FAIL (0.86) | pass (0.86) | pass (0.84) | FAIL (0.41) | FAIL (0.53) | pass (0.89) | pass (0.96) |
| crbug-audio-input-args | FAIL (0.74) | FAIL (n/a) | pass (0.65) | pass (0.89) | FAIL (0.70) | pass (0.92) | pass (0.86) |
| crbug-basic-auth-not | FAIL (0.84) | FAIL (0.15) | pass (0.88) | pass (0.80) | FAIL (0.09) | pass (0.85) | pass (0.88) |
| crbug-form-method-none | FAIL (0.80) | FAIL (0.42) | pass (0.79) | n/a (n/a) | FAIL (0.69) | pass (0.92) | pass (0.83) |
| crbug-ftp-active-string | FAIL (0.86) | FAIL (0.47) | pass (0.95) | pass (0.98) | FAIL (0.74) | pass (0.97) | pass (0.97) |
| crbug-log-textio | FAIL (0.31) | FAIL (0.26) | FAIL (0.44) | FAIL (0.00) | FAIL (0.36) | pass (0.52) | pass (0.68) |
| crbug-netrc-env-path | FAIL (0.79) | FAIL (0.76) | pass (0.78) | pass (0.83) | FAIL (0.75) | pass (0.88) | pass (0.83) |
| crbug-replace-same-object | FAIL (0.20) | FAIL (0.38) | pass (0.70) | pass (0.82) | FAIL (0.58) | pass (0.74) | pass (0.76) |
| crbug-xtrim-maxlen-minid | FAIL (0.80) | FAIL (0.00) | pass (0.76) | FAIL (0.10) | FAIL (0.63) | pass (0.81) | pass (0.68) |
| diff-old-bug-on-untouched-line | FAIL (0.97) | pass (0.73) | pass (1.00) | FAIL (0.50) | FAIL (0.49) | pass (0.93) | pass (1.00) |
| rereview-earlier-findings | FAIL (0.76) | FAIL (0.51) | pass (0.96) | pass (1.00) | FAIL (0.47) | pass (0.96) | pass (0.97) |
| spot-the-bug | pass (1.00) | pass (0.93) | pass (0.94) | pass (1.00) | pass (0.86) | pass (1.00) | pass (1.00) |
| style-only-no-changes-needed | pass (0.96) | pass (1.00) | pass (1.00) | FAIL (0.09) | pass (0.94) | pass (0.60) | pass (1.00) |

## Why gates failed

Failed gate checks per setup, with the number of runs each failed in:

- OpenCode /review (12 runs): `blocks` 10, `approves` 2
- OpenCode + playbook v0.1.0 (8 runs): `blocks` 8, `not approves` 1, `remove_fixed` 1
- OpenCode + playbook v0.3.0 (4 runs): `approves` 2, `blocks` 2, `not blocks` 1, `not counts_important` 1
- Claude Code /code-review (12 runs): `blocks` 10, `approves` 2, `remove_fixed` 1, `discount_open` 1

## Runs the judge could not score

- OpenCode + playbook v0.1.0 / crbug-audio-input-args: refused (`reasoning_extraction`)
- OpenCode + playbook v0.3.0 / crbug-form-method-none: refused (`reasoning_extraction`)
