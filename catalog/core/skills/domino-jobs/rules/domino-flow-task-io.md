---
id: domino-flow-task-io
name: Flow task inputs and outputs
description: "A Flow task reads its inputs from /workflow/inputs, writes every declared output under /workflow/outputs, and detects Flow mode by parsing DOMINO_IS_WORKFLOW_JOB."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "**/flows/**/*.py"
  - "**/workflow*.py"
applies_if:
  domino_project: true
section: flow-tasks
priority: 48
tags: [python, domino, jobs, flows]
---

# Read Flow inputs and write every declared output

## Description

Each Flow task is a Domino job whose inputs arrive as files under `/workflow/inputs/<name>`: a file input is the file itself, and a primitive input (a number, a string, a flag) is its value written as text. Its declared outputs must exist under `/workflow/outputs/<name>` when the job ends; a missing output fails the task. Nothing else persists: a Flow task makes no project commit, keeps no artifacts and takes no dataset snapshot. Code that also runs as a standalone job picks its locations from the `DOMINO_IS_WORKFLOW_JOB` flag.

## Bad Example

```python
import os
from pathlib import Path

artifacts = Path("/mnt/artifacts")
frame = load_csv(artifacts / "train.csv")  # not where a Flow puts its inputs
epochs = int(Path("/workflow/inputs/epochs").read_text())  # breaks on a trailing newline
if os.environ.get("DOMINO_IS_WORKFLOW_JOB"):  # true for the string "false"
    save_model(fit(frame, epochs), artifacts / "model.pkl")  # lost: not a declared output
```

## Good Example

```python
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

TRAINING_DATA = "training_data"  # names shared with the flow definition
EPOCHS = "epochs"
MODEL = "model"


def is_flow_task(env: Mapping[str, str]) -> bool:
    return env.get("DOMINO_IS_WORKFLOW_JOB", "").strip().lower() == "true"


@dataclass(frozen=True)
class FlowIO:
    inputs_dir: Path = Path("/workflow/inputs")
    outputs_dir: Path = Path("/workflow/outputs")

    def input_path(self, name: str) -> Path:
        return self.inputs_dir / name

    def read_text_input(self, name: str) -> str:
        return self.input_path(name).read_text(encoding="utf-8").strip()

    def output_path(self, name: str) -> Path:
        return self.outputs_dir / name


def run_task(io: FlowIO) -> None:
    frame = load_csv(io.input_path(TRAINING_DATA))
    model = fit(frame, epochs=int(io.read_text_input(EPOCHS)))
    save_model(model, io.output_path(MODEL))
```

```python
def test_run_task_writes_the_model(tmp_path: Path) -> None:
    io = FlowIO(inputs_dir=tmp_path / "in", outputs_dir=tmp_path / "out")
    io.inputs_dir.mkdir()
    io.outputs_dir.mkdir()
    write_sample_csv(io.input_path(TRAINING_DATA))
    io.input_path(EPOCHS).write_text("2\n", encoding="utf-8")

    run_task(io)

    assert io.output_path(MODEL).exists()
```

## Notes

- Write every declared output, including a legitimately empty result in its declared format, and write outputs last and atomically (domino-run-scoped-writes).
- Output names must match the task's declared outputs exactly; keep them as constants shared with the flow definition.
- For a local run, create the input files (or use the plugin's setup helper) rather than editing paths in the task.
- Standalone-mode paths come from domino-paths-from-env; side effects and retries are domino-flow-task-purity.
- The where-outputs-go reference in this skill shows the Flow column next to the standalone ones.
