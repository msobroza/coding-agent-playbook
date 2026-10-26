# Review benchmark: `review-qwen3.6-27b-foreground-rule`

Agent: `qwen/qwen3.6-27b` through OpenRouter, in Claude Code. Judge: `claude-opus-5-5` (medium effort). One trial per sample; a sample passes when its gate and its rubric both pass.

| Reviewer | Passed | Gate passed | Rubric passed | Mean judge score | Median agent time | Runs that edited files |
|---|---|---|---|---|---|---|
| Claude Code + playbook v2 | 14/14 | 14/14 | 14/14 | 0.88 | 252 s | 0/14 |

## By sample set (passed, mean judge score)

| Sample set | Claude Code + playbook v2 |
|---|---|
| original (6 samples) | 6/6 (0.97) |
| CRBugBench (8 samples) | 8/8 (0.81) |

## CRBugBench-style detection (samples with one known defect)

Did the review catch the known defect? Strict counts the judge's `yes`; lenient counts `yes` as 1 and `partial` as 0.5; top-5 is a `yes` whose first matching comment is among the review's first five. Passed is this benchmark's gate-and-rubric verdict on the same runs.

| Reviewer | Runs | Passed | Strict detection | Lenient detection | Found in first 5 comments | Median first match | Comments per review |
|---|---|---|---|---|---|---|---|
| Claude Code + playbook v2 | 8 | 100% | 100% | 100% | 100% | 1 | 5.0 |

## Did the second pass run? (v2 setups)

- Claude Code + playbook v2: 14 of 14 runs; 15 of 28 subagent starts in the background

## Per sample (verdict, judge score)

| Sample | Claude Code + playbook v2 |
|---|---|
| change-drops-part-of-request | pass (0.90) |
| clean-multi-file-change | pass (0.96) |
| crbug-audio-input-args | pass (0.86) |
| crbug-basic-auth-not | pass (0.88) |
| crbug-form-method-none | pass (0.83) |
| crbug-ftp-active-string | pass (0.97) |
| crbug-log-textio | pass (0.68) |
| crbug-netrc-env-path | pass (0.83) |
| crbug-replace-same-object | pass (0.76) |
| crbug-xtrim-maxlen-minid | pass (0.68) |
| diff-old-bug-on-untouched-line | pass (1.00) |
| rereview-earlier-findings | pass (0.97) |
| spot-the-bug | pass (1.00) |
| style-only-no-changes-needed | pass (1.00) |

## Why gates failed

Every gate passed.
