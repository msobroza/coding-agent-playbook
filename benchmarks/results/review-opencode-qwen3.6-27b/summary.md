# Review benchmark: `review-opencode-qwen3.6-27b`

Agent: `qwen/qwen3.6-27b` through OpenRouter, in OpenCode and Claude Code. Judge: `claude-opus-5-5` (medium effort). One trial per sample; a sample passes when its gate and its rubric both pass.

| Reviewer | Passed | Gate passed | Rubric passed | Mean judge score | Median agent time | Runs that edited files |
|---|---|---|---|---|---|---|
| OpenCode /review | 2/14 | 2/14 | 12/14 | 0.76 | 81 s | 0/14 |
| OpenCode + playbook v1 | 5/14 | 6/14 | 7/14 | 0.57 | 52 s | 0/14 |
| OpenCode + playbook v2 | 12/14 | 13/14 | 12/14 | 0.82 | 162 s | 0/14 |
| Claude Code /code-review | 2/14 | 2/14 | 10/14 | 0.61 | 217 s | 0/14 |
| Claude Code + playbook v2 | 8/14 | 12/14 | 9/14 | 0.69 | 181 s | 0/14 |
| Claude Code + v2 over /code-review | 12/14 | 13/14 | 12/14 | 0.84 | 232 s | 1/14 |
| OpenCode + v2 with /review alongside | 11/14 | 11/14 | 11/14 | 0.73 | 115 s | 0/14 |
| Claude Code + v2 with /code-review alongside | 13/14 | 13/14 | 13/14 | 0.87 | 319 s | 0/14 |

## By sample set (passed, mean judge score)

| Sample set | OpenCode /review | OpenCode + playbook v1 | OpenCode + playbook v2 | Claude Code /code-review | Claude Code + playbook v2 | Claude Code + v2 over /code-review | OpenCode + v2 with /review alongside | Claude Code + v2 with /code-review alongside |
|---|---|---|---|---|---|---|---|---|
| original (6 samples) | 2/6 (0.89) | 5/6 (0.83) | 6/6 (0.94) | 2/6 (0.66) | 4/6 (0.77) | 5/6 (0.85) | 5/6 (0.85) | 5/6 (0.87) |
| CRBugBench (8 samples) | 0/8 (0.67) | 0/8 (0.35) | 6/8 (0.74) | 0/8 (0.57) | 4/8 (0.64) | 7/8 (0.83) | 6/8 (0.63) | 8/8 (0.87) |

## CRBugBench-style detection (samples with one known defect)

Did the review catch the known defect? Strict counts the judge's `yes`; lenient counts `yes` as 1 and `partial` as 0.5; top-5 is a `yes` whose first matching comment is among the review's first five. Passed is this benchmark's gate-and-rubric verdict on the same runs.

| Reviewer | Runs | Passed | Strict detection | Lenient detection | Found in first 5 comments | Median first match | Comments per review |
|---|---|---|---|---|---|---|---|
| OpenCode /review | 8 | 0% | 75% | 81% | 75% | 1 | 1.8 |
| OpenCode + playbook v1 | 8 | 0% | 25% | 56% | 25% | 1 | 3.4 |
| OpenCode + playbook v2 | 8 | 75% | 75% | 81% | 75% | 1 | 3.9 |
| Claude Code /code-review | 8 | 0% | 88% | 94% | 88% | 1 | 6.1 |
| Claude Code + playbook v2 | 8 | 50% | 62% | 75% | 62% | 1 | 3.8 |
| Claude Code + v2 over /code-review | 8 | 88% | 100% | 100% | 100% | 1 | 4.9 |
| OpenCode + v2 with /review alongside | 8 | 75% | 75% | 75% | 75% | 1 | 2.8 |
| Claude Code + v2 with /code-review alongside | 8 | 100% | 88% | 94% | 88% | 1 | 4.8 |

## Did the native reviewer run? (prototypes)

- Claude Code + v2 over /code-review: 0 of 0 runs (14 runs not recorded)
- OpenCode + v2 with /review alongside: 1 of 14 runs
- Claude Code + v2 with /code-review alongside: 12 of 14 runs

## Per sample (verdict, judge score)

| Sample | OpenCode /review | OpenCode + playbook v1 | OpenCode + playbook v2 | Claude Code /code-review | Claude Code + playbook v2 | Claude Code + v2 over /code-review | OpenCode + v2 with /review alongside | Claude Code + v2 with /code-review alongside |
|---|---|---|---|---|---|---|---|---|
| change-drops-part-of-request | FAIL (0.81) | pass (0.95) | pass (0.81) | FAIL (0.68) | FAIL (0.71) | pass (0.91) | pass (0.93) | pass (0.88) |
| clean-multi-file-change | FAIL (0.86) | pass (0.86) | pass (0.99) | FAIL (0.53) | pass (0.82) | pass (0.97) | FAIL (0.30) | FAIL (0.43) |
| crbug-audio-input-args | FAIL (0.74) | FAIL (n/a) | FAIL (0.16) | FAIL (0.70) | n/a (0.90) | pass (0.83) | FAIL (0.00) | pass (0.97) |
| crbug-basic-auth-not | FAIL (0.84) | FAIL (0.15) | pass (0.85) | FAIL (0.09) | FAIL (0.25) | pass (0.84) | pass (0.80) | pass (0.83) |
| crbug-form-method-none | FAIL (0.80) | FAIL (0.42) | pass (0.92) | FAIL (0.69) | pass (0.85) | pass (0.82) | pass (0.75) | pass (0.90) |
| crbug-ftp-active-string | FAIL (0.86) | FAIL (0.47) | pass (0.98) | FAIL (0.74) | pass (0.93) | pass (0.91) | pass (0.96) | pass (0.97) |
| crbug-log-textio | FAIL (0.31) | FAIL (0.26) | FAIL (0.48) | FAIL (0.36) | FAIL (0.47) | n/a (0.80) | FAIL (0.20) | pass (0.55) |
| crbug-netrc-env-path | FAIL (0.79) | FAIL (0.76) | pass (0.83) | FAIL (0.75) | FAIL (0.12) | pass (0.95) | pass (0.87) | pass (0.91) |
| crbug-replace-same-object | FAIL (0.20) | FAIL (0.38) | pass (0.86) | FAIL (0.58) | pass (0.72) | pass (0.71) | pass (0.64) | pass (0.96) |
| crbug-xtrim-maxlen-minid | FAIL (0.80) | FAIL (0.00) | pass (0.82) | FAIL (0.63) | pass (0.85) | pass (0.79) | pass (0.84) | pass (0.85) |
| diff-old-bug-on-untouched-line | FAIL (0.97) | pass (0.73) | pass (0.97) | FAIL (0.49) | pass (0.99) | FAIL (0.36) | pass (0.99) | pass (0.99) |
| rereview-earlier-findings | FAIL (0.76) | FAIL (0.51) | pass (0.95) | FAIL (0.47) | pass (0.95) | pass (0.88) | pass (0.96) | pass (0.95) |
| spot-the-bug | pass (1.00) | pass (0.93) | pass (0.92) | pass (0.86) | FAIL (0.15) | pass (0.96) | pass (0.96) | pass (0.96) |
| style-only-no-changes-needed | pass (0.96) | pass (1.00) | pass (1.00) | pass (0.94) | pass (1.00) | pass (1.00) | pass (0.97) | pass (1.00) |

## Why gates failed

- OpenCode /review / change-drops-part-of-request: `blocks`
- OpenCode /review / clean-multi-file-change: `approves`
- OpenCode /review / crbug-audio-input-args: `blocks`
- OpenCode /review / crbug-basic-auth-not: `blocks`
- OpenCode /review / crbug-form-method-none: `blocks`
- OpenCode /review / crbug-ftp-active-string: `blocks`
- OpenCode /review / crbug-log-textio: `blocks`
- OpenCode /review / crbug-netrc-env-path: `blocks`
- OpenCode /review / crbug-replace-same-object: `blocks`
- OpenCode /review / crbug-xtrim-maxlen-minid: `blocks`
- OpenCode /review / diff-old-bug-on-untouched-line: `approves`
- OpenCode /review / rereview-earlier-findings: `blocks`
- OpenCode + playbook v1 / crbug-audio-input-args: `blocks`
- OpenCode + playbook v1 / crbug-basic-auth-not: `blocks`
- OpenCode + playbook v1 / crbug-form-method-none: `blocks`
- OpenCode + playbook v1 / crbug-log-textio: `blocks; not approves`
- OpenCode + playbook v1 / crbug-netrc-env-path: `blocks`
- OpenCode + playbook v1 / crbug-replace-same-object: `blocks`
- OpenCode + playbook v1 / crbug-xtrim-maxlen-minid: `blocks`
- OpenCode + playbook v1 / rereview-earlier-findings: `remove_fixed; blocks`
- OpenCode + playbook v2 / crbug-audio-input-args: `blocks`
- Claude Code /code-review / change-drops-part-of-request: `blocks`
- Claude Code /code-review / clean-multi-file-change: `approves`
- Claude Code /code-review / crbug-audio-input-args: `blocks`
- Claude Code /code-review / crbug-basic-auth-not: `blocks`
- Claude Code /code-review / crbug-form-method-none: `blocks`
- Claude Code /code-review / crbug-ftp-active-string: `blocks`
- Claude Code /code-review / crbug-log-textio: `blocks`
- Claude Code /code-review / crbug-netrc-env-path: `blocks`
- Claude Code /code-review / crbug-replace-same-object: `blocks`
- Claude Code /code-review / crbug-xtrim-maxlen-minid: `blocks`
- Claude Code /code-review / diff-old-bug-on-untouched-line: `approves`
- Claude Code /code-review / rereview-earlier-findings: `remove_fixed; discount_open; blocks`
- Claude Code + playbook v2 / change-drops-part-of-request: `blocks`
- Claude Code + playbook v2 / crbug-netrc-env-path: `blocks`
- Claude Code + v2 over /code-review / diff-old-bug-on-untouched-line: `approves` (edited: review_findings.json)
- OpenCode + v2 with /review alongside / clean-multi-file-change: `approves`
- OpenCode + v2 with /review alongside / crbug-audio-input-args: `blocks`
- OpenCode + v2 with /review alongside / crbug-log-textio: `blocks`
- Claude Code + v2 with /code-review alongside / clean-multi-file-change: `approves; not blocks; not counts_important`

## Runs the judge could not score

- OpenCode + playbook v1 / crbug-audio-input-args: tps://support.claude.com/en/articles/8106465 Details: `[reasoning_extraction]` Request ID: req_011CgQ4tJG2RA91uzonFZq6V Message ID: msg_011CgQ4tJadH1vEXsdBbViN2
- Claude Code + playbook v2 / crbug-audio-input-args: tps://support.claude.com/en/articles/8106465 Details: `[reasoning_extraction]` Request ID: req_011CgQnYnWE46Hy7BaQxLyTH Message ID: msg_011CgQnYnvHeQXrCAVvyHfJz
- Claude Code + v2 over /code-review / crbug-log-textio: tps://support.claude.com/en/articles/8106465 Details: `[reasoning_extraction]` Request ID: req_011CgQni8oNSELJgQhwutRHu Message ID: msg_011CgQni9BhACQiwETS1jdn3
