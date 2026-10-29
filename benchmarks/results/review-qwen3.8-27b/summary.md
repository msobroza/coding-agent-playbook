# Results

| Reviewer (14 `review/*` samples x 3 runs) | Engine pass | Judge passes the review | Pass ignoring the verdict line | Judge score | Runs that edited code | Median time |
|---|---|---|---|---|---|---|
| **Claude Code + playbook** | 37/42 | ≥ 37/42 (4 not judged) | ≥ 37/42 (4 not judged) | 0.91 | 0 of 38 judged | 263 s |
| **Claude Code /code-review** | 3/42 | 35/42 | 33/42 | 0.72 | 2 | 156 s |
| **OpenCode + playbook** | 37/42 | ≥ 37/42 (5 not judged) | ≥ 37/42 (5 not judged) | 0.91 | 0 of 37 judged | 336 s |
| **OpenCode /review** | 2/42 | 35/42 | 23/42 | 0.71 | 18 | 132 s |

## Rubric criteria a built-in reviewer never met

| # | Sample | Criterion (abridged) | /code-review met | /review met |
|---|---|---|---|---|
| 1 | change-drops-part-of-request | The review cites file and line (for example the argument parser in src/report.py's main) and prop... | 2/3 | 0/3 |
| 2 | diff-old-bug-on-untouched-line | The review does not invent a bug in restock() or its tests (for example claiming it mutates the w... | 0/3 | 3/3 |
| 3 | diff-old-bug-on-untouched-line | The review's verdict is 'approve' or 'approve with comments': the new restock() function and its... | 0/3 | 3/3 |
| 4 | clean-multi-file-change | The review reads every file the change touches (src/units.py, src/shipping.py and both test files... | 1/3 | 0/3 |
| 5 | clean-multi-file-change | The review's verdict is 'approve' or 'approve with comments': the new to_kilograms() helper, its... | 0/3 | 3/3 |
| 6 | crbug-basic-auth-not | The review reports that the new condition is not valid Python: `!` is not a negation operator (it... | 3/3 | 0/3 |
| 7 | crbug-basic-auth-not | The review treats that bug as blocking (important, not a nit or an open question), cites its file... | 3/3 | 0/3 |
| 8 | crbug-form-method-none | The review does not invent bugs: anything else it raises is a real problem in the code shown, and... | 0/3 | 3/3 |
| 9 | crbug-log-textio | The review treats that bug as blocking (important, not a nit or an open question), cites its file... | 1/3 | 0/3 |
| 10 | crbug-replace-same-object | The review treats that bug as blocking (important, not a nit or an open question), cites its file... | 1/3 | 0/3 |
| 11 | crbug-xtrim-maxlen-minid | The review does not invent bugs: anything else it raises is a real problem in the code shown, and... | 0/3 | 3/3 |
| 12 | crbug-xtrim-maxlen-minid | The review treats that bug as blocking (important, not a nit or an open question), cites its file... | 1/3 | 0/3 |
