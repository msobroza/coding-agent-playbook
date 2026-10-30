# Release metrics: 9.9.4

Targets: claude-opus (vs 9.9.3), opencode-qwen (vs 9.9.3).

## claude-opus

Pass rate 0.917 (+0.083 vs 9.9.3), mean score 0.833 (+0.040).
Rerun 2 / carried 1 / rejudged 1.
Setup: claude_code 2.1.300, model claude-opus-5-5, judge judge-new, setup digest setup-9.9.4-claude-opus.

No regressions.

### Tasks: claude-opus

| task | previous pass rate | pass rate | Δ pass rate | previous mean | mean | Δ mean | regressions | improvements | carried | rejudged | new |
|---|---|---|---|---|---|---|---|---|---|---|---|
| review | 0.778 | 0.889 | +0.111 | 0.790 | 0.843 | +0.053 | 0 | 1 | 0 | 1 | 0 |
| tidy | 1.000 | 1.000 | +0.000 | 0.800 | 0.800 | +0.000 | 0 | 0 | 1 | 0 | 0 |

### Changed samples: claude-opus

| sample | task | status | previous mean | mean | Δ mean | reasons |
|---|---|---|---|---|---|---|
| review/a | review | rejudged | 0.920 | 0.880 | -0.040 | rejudged from 9.9.3 |
| review/b | review | improvement | 0.500 | 0.700 | +0.200 | mean score rises 0.200; passes 2 of 3 runs; judge changed since 9.9.3: pass agreement 100% |

Carried samples (counted, not listed): 1.

### Controls: claude-opus

| control | edition | passes | runs | previous mean | mean | Δ mean |
|---|---|---|---|---|---|---|
| review/a | 9.9.1 | 3 | 3 | 0.860 | 0.860 | +0.000 |

### Judge change: claude-opus

Judge changed from judge-old, judge-older to judge-new: 3 runs, pass agreement 100%, mean |Δ score| 0.040.

| task | runs | pass agreement | mean abs score diff |
|---|---|---|---|
| review | 3 | 100% | 0.040 |

### Trend: claude-opus

| release | task | pass rate | mean | judge changed |
|---|---|---|---|---|
| 9.9.2 | review | 0.833 | 0.800 |  |
| 9.9.2 | tidy | 1.000 | 0.800 |  |
| 9.9.3 | review | 0.778 | 0.790 |  |
| 9.9.3 | tidy | 1.000 | 0.800 |  |
| 9.9.4 | review | 0.889 | 0.843 | yes |
| 9.9.4 | tidy | 1.000 | 0.800 | yes |

## opencode-qwen

Pass rate 0.667 (+0.000 vs 9.9.3), mean score 0.600 (-0.025).
Rerun 2 / carried 0 / rejudged 0.
Setup: claude_code 2.1.300, model claude-opus-5-5, judge judge-old, setup digest setup-9.9.4-opencode-qwen.

Regressions:

- `review/a`: mean score drops 0.150 (accepted: the rubric is stricter)

### Tasks: opencode-qwen

| task | previous pass rate | pass rate | Δ pass rate | previous mean | mean | Δ mean | regressions | improvements | carried | rejudged | new |
|---|---|---|---|---|---|---|---|---|---|---|---|
| review | 1.000 | 0.667 | -0.333 | 0.750 | 0.600 | -0.150 | 1 | 0 | 0 | 0 | 0 |
| tidy | 0.333 | 0.667 | +0.333 | 0.500 | 0.600 | +0.100 | 0 | 1 | 0 | 0 | 0 |

### Changed samples: opencode-qwen

| sample | task | status | previous mean | mean | Δ mean | reasons |
|---|---|---|---|---|---|---|
| review/a | review | regression | 0.750 | 0.600 | -0.150 | mean score drops 0.150 |
| tidy/a | tidy | improvement | 0.500 | 0.600 | +0.100 | mean score rises 0.100; passes 2 of 3 runs |

### Controls: opencode-qwen

No edition controls.

### Trend: opencode-qwen

| release | task | pass rate | mean | judge changed |
|---|---|---|---|---|
| 9.9.2 | review | 0.667 | 0.600 |  |
| 9.9.2 | tidy | 0.333 | 0.500 |  |
| 9.9.3 | review | 1.000 | 0.750 |  |
| 9.9.3 | tidy | 0.333 | 0.500 |  |
| 9.9.4 | review | 0.667 | 0.600 |  |
| 9.9.4 | tidy | 0.667 | 0.600 |  |
