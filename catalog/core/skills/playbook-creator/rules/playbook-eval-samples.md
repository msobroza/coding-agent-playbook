---
id: playbook-eval-samples
name: Eval samples
description: "Give each prompt eval samples whose deterministic gate fails on the setup and every negative and passes on the solution."
scope: scoped
globs:
  - "catalog/**/eval_samples/**"
  - "playbook/eval_samples/**"
  - "src/*/resources/eval_samples/**"
applies_if:
  playbook_layer: true
section: prompts
priority: 46
tags: [playbook, evals]
---

# Prove a prompt with reproducible eval samples

## Description

An eval sample is a reproducible test of a prompt: `eval_samples/<prompt-id>/<scenario>/` beside its layer's `prompts/`, with the id `<prompt-id>/<scenario>`. The `<prompt-id>` directory is the prompt's task: it names the one prompt its samples grade, and the prompt does not list them. Its `sample.toml` holds:

- `id` and `description`. Any other top-level key is an error, `prompt_id` included.
- `[setup]`: the files and the mock facts (`project_kind`, `python_version`, `frameworks`).
- `[invocation]`: `prompt_args` and `input_variables`.
- At least one of `[gate]` and `[rubric]`. The gate binds deterministic handles by name (`file_exists`, `file_contains`, `file_unchanged`, `file_forbidden`, `answer_matches`, a metric `threshold` or `non_regression`) and combines them in `expr`. The rubric binds judge criteria whose weights sum to 1.0, with a 0-1 `fail` cutoff.
- `[verdict]` `trial` (default `"gate and rubric"`) and an optional `[aggregate]` (`pass_at_k`).

`setup/` is the frozen starting repo, with `setup/pyproject.toml` when facts matter. `solution/` mirrors `setup/` paths with what a correct agent writes, or holds `transcript.md` for a review-only sample. `solution/negatives/<case>/` holds known-wrong attempts; a review-only sample needs at least one. CI proves the gate fails on `setup/` and on every negative, and passes on the solution.

## Bad Example

```toml
id = "release-review/happy-path"

[gate]
expr = "untouched"

[gate.bind]
untouched = { check = "file_unchanged", path = "billing/invoice.py" }
cites = { check = "answer_matches", pattern = "invoice\.py:\d+" }
```

The expression uses only `untouched`, so any answer that edits nothing passes, and the `cites` pattern sits in a TOML basic string, where `\.` and `\d` are invalid escapes.

## Good Example

```toml
[gate]
expr = "untouched and holds and names_float"

[gate.bind]
untouched = { check = "file_unchanged", path = "billing/invoice.py" }
holds = { check = "answer_matches", pattern = '(?im)^\W*verdict\W*hold\W*$' }
names_float = { check = "answer_matches", pattern = '(?i)invoice\.py:\d+.*float' }
```

```text
eval_samples/release-review/happy-path/
├── sample.toml
├── setup/
│   ├── pyproject.toml
│   └── billing/invoice.py         # sums amounts as floats
└── solution/
    ├── transcript.md              # names invoice.py:12, verdict hold
    └── negatives/
        └── ships-anyway.md        # misses the float; verdict ship
```

## Notes

- Write three samples per prompt: a happy path, an edge case and a regression.
- Check deterministically first and judge only what cannot be checked.
- Test the prompt, not the model: target what the prompt controls.
- Check a sample with validate and `playbook eval --show <prompt-id>/<scenario>`. Never run `playbook eval --run` to check it: that runs an agent, costs money and needs the owner's credentials.
- Never reformat or lint-fix `setup/`; the eval-sample-authoring-lint and guard-eval-fixtures hooks remind and protect.
- Credit third-party fixture code in the layer's eval_samples/ATTRIBUTIONS.md.
- eval-sample-template.md has the full skeleton.
