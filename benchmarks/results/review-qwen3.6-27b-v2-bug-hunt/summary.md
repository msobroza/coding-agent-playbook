# Review benchmark: `review-qwen3.6-27b-v2-bug-hunt`

Agent: `qwen/qwen3.6-27b` through OpenRouter, in OpenCode and Claude Code. Judge: `claude-opus-5-5` (medium effort). One trial per sample; a sample passes when its gate and its rubric both pass.

| Reviewer | Passed | Gate passed | Rubric passed | Mean judge score | Median agent time | Runs that edited files |
|---|---|---|---|---|---|---|
| OpenCode + playbook v2 | 14/14 | 14/14 | 14/14 | 0.90 | 181 s | 0/14 |
| Claude Code + playbook v2 | 12/14 | 13/14 | 12/14 | 0.79 | 242 s | 0/14 |

## By sample set (passed, mean judge score)

| Sample set | OpenCode + playbook v2 | Claude Code + playbook v2 |
|---|---|---|
| original (6 samples) | 6/6 (0.94) | 6/6 (0.92) |
| CRBugBench (8 samples) | 8/8 (0.87) | 6/8 (0.69) |

## CRBugBench-style detection (samples with one known defect)

Did the review catch the known defect? Strict counts the judge's `yes`; lenient counts `yes` as 1 and `partial` as 0.5; top-5 is a `yes` whose first matching comment is among the review's first five. Passed is this benchmark's gate-and-rubric verdict on the same runs.

| Reviewer | Runs | Passed | Strict detection | Lenient detection | Found in first 5 comments | Median first match | Comments per review |
|---|---|---|---|---|---|---|---|
| OpenCode + playbook v2 | 8 | 100% | 100% | 100% | 100% | 1 | 3.0 |
| Claude Code + playbook v2 | 8 | 75% | 88% | 88% | 88% | 1 | 5.1 |

## Did the second pass run? (v2 setups)

- OpenCode + playbook v2: 11 of 14 runs
- Claude Code + playbook v2: 13 of 14 runs; 13 of 26 subagent starts in the background

## Per sample (verdict, judge score)

| Sample | OpenCode + playbook v2 | Claude Code + playbook v2 |
|---|---|---|
| change-drops-part-of-request | pass (0.83) | pass (0.79) |
| clean-multi-file-change | pass (0.91) | pass (0.84) |
| crbug-audio-input-args | pass (0.97) | n/a (0.80) |
| crbug-basic-auth-not | pass (0.87) | pass (0.83) |
| crbug-form-method-none | pass (0.70) | pass (0.82) |
| crbug-ftp-active-string | pass (0.98) | FAIL (0.10) |
| crbug-log-textio | pass (0.92) | pass (0.51) |
| crbug-netrc-env-path | pass (0.86) | pass (0.85) |
| crbug-replace-same-object | pass (0.80) | pass (0.86) |
| crbug-xtrim-maxlen-minid | pass (0.83) | pass (0.74) |
| diff-old-bug-on-untouched-line | pass (0.97) | pass (1.00) |
| rereview-earlier-findings | pass (0.95) | pass (0.94) |
| spot-the-bug | pass (0.98) | pass (0.96) |
| style-only-no-changes-needed | pass (1.00) | pass (1.00) |

## Why gates failed

- Claude Code + playbook v2 / crbug-ftp-active-string: `blocks`

## Runs the judge could not score

- Claude Code + playbook v2 / crbug-audio-input-args:  1: Warning: no stdin data received in 3s, proceeding without it. If piping from a slow command, redirect stdin explicitly: < /dev/null to skip, or wait longer.
