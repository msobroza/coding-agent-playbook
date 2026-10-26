# Eval sample template

An eval sample tests the prompt, not the model: write three per prompt, a happy path, an edge case and a regression. Copy the skeleton, replace the placeholders and run `playbook validate`. Fields: `playbook-eval-samples`; the prompt side: `playbook-prompt-frontmatter`.

## Contents

- Directory trees
- Sample file skeleton
- Gate check vocabulary
- Rubric criteria and negatives
- Commands
- Checklist

## Directory trees

`eval_samples/<prompt-id>/<scenario>/`, beside the layer's `prompts/`. The `<prompt-id>` directory is the prompt's task: it holds every sample of that prompt and names the prompt they grade.

An edit sample: `solution/` mirrors the `setup/` paths with what a correct agent writes.

```text
eval_samples/characterize/pricing-boundary/
├── sample.toml
├── setup/
│   ├── pyproject.toml
│   └── src/pricing.py
└── solution/
    ├── tests/test_pricing.py
    └── negatives/
        └── fixes-the-source/
            └── src/pricing.py
```

A review-only sample: the solution is an answer, and each negative is a wrong answer in Markdown.

```text
eval_samples/release-review/happy-path/
├── sample.toml
├── setup/
│   └── billing/invoice.py
└── solution/
    ├── transcript.md
    └── negatives/
        └── ships-anyway.md
```

## Sample file skeleton

```toml
# sample.toml in eval_samples/release-review/happy-path/
id = "release-review/happy-path"   # <prompt-id>/<scenario>: its directory
description = "Happy path: a float sum in invoice.py must hold the release."

[setup]
files = ["billing/invoice.py"]  # must match the files in setup/
project_kind = "python-application"

[invocation]
prompt_args = "review the release branch"
input_variables = { branch = "release/1.4" }

[gate]
expr = "untouched and holds"

[gate.bind]
untouched = { check = "file_unchanged", path = "billing/invoice.py" }
holds = { check = "answer_matches", pattern = '(?im)^\W*verdict\W*hold\W*$' }

[rubric]
expr = "quality"

[rubric.bind]
quality = { fail = 0.5, rubric = [
  { judge = "The answer names invoice.py and the line that sums floats.", weight = 0.6 },
  { judge = "The answer proposes Decimal amounts, not rounding the float.", weight = 0.4 },
] }

[verdict]
trial = "gate and rubric"
```

At least one of `[gate]` and `[rubric]` is required. An optional `[aggregate]` layer binds `pass_at_k` or `pass_pow_k` with `k` and `over` (`gate`, `rubric` or `verdict`).

## Gate check vocabulary

| Check | Proves |
| --- | --- |
| `file_exists`, `file_forbidden` | A path exists, or must not exist |
| `file_contains` | A file matches a regex |
| `file_unchanged` | A file is byte-identical to `setup/` |
| `answer_matches` | The final answer matches a regex |
| `tests_pass` | The repo's tests pass after the edit |
| `threshold`, `non_regression` | A metric reaches a 0-1 cutoff, or does not worsen from `setup/` |
| `{ ref = "<gate>" }` | A registered composed gate |

Write every regex as a single-quoted TOML literal string, where `\d` and `\.` stay literal.

## Rubric criteria and negatives

Rubric weights sum to 1.0, and `fail` is the 0-1 cutoff. Judge only what no check can decide (clarity, the right reason); anything a regex or a file check can prove belongs in the gate.

Write one negative per plausible wrong answer: a fixed source where the prompt said pin, a missed defect, a wrong verdict. Each must prove the gate rejects it; a negative the gate passes shows a gate that is too loose.

## Commands

```bash
playbook validate                           # schema, task directories, setup files
playbook eval --show <prompt-id>/<scenario>  # the compiled layers of one sample
playbook eval --list                        # every task and its samples
```

Never run `playbook eval --run` to check a sample: it runs an agent, costs money and needs the owner's credentials.

## Checklist

- The id is `<prompt-id>/<scenario>`, its directory under the prompt's task; the prompt does not list it.
- `setup.files` matches `setup/`; never reformat or lint-fix `setup/`.
- The gate fails on `setup/` and on every negative, and passes on the solution; a review-only sample has at least one negative.
- Third-party fixture code is credited in the layer's eval_samples/ATTRIBUTIONS.md.
