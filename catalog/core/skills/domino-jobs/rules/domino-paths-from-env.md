---
id: domino-paths-from-env
name: Paths from the environment
description: "Read Domino's injected paths and run identity once into a frozen record with local fallbacks, and pass that record down instead of hard-coding /mnt or /domino paths."
version: 1
scope: scoped
globs:
  - "**/settings.py"
  - "**/config.py"
  - "**/paths.py"
  - "**/*.py"
applies_if:
  domino_project: true
section: project-and-run-environment
priority: 22
tags: [python, domino, jobs, configuration]
---

# Paths from the environment

## Description

Domino injects a run's paths and identity as environment variables. Their values differ between DFS and Git-based projects, imported projects and Flow tasks, and they are absent on a laptop, in CI and in Model Manager. One module reads them once into a frozen record with explicit local fallbacks; the rest of the code receives that record as a parameter (`python-dependency-injection`, python-coding skill).

## Bad Example

```python
import os
from pathlib import Path

ARTIFACTS = Path("/mnt/artifacts")  # wrong in DFS projects
SALES = Path("/domino/datasets/local/sales")  # wrong in Git-based projects


def tag_output(name: str) -> str:
    return f"{name}-{os.environ['DOMINO_RUN_ID']}"  # KeyError in a local test
```

## Good Example

```python
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def _flag(env: Mapping[str, str], name: str) -> bool:
    return env.get(name, "false").lower() == "true"  # values arrive as text


@dataclass(frozen=True)
class JobContext:
    working_dir: Path
    artifacts_dir: Path
    datasets_dir: Path
    is_git_based: bool
    is_flow_task: bool
    run_id: str
    run_number: str
    project_owner: str
    project_name: str

    @classmethod
    def from_env(cls, env: Mapping[str, str], *, local_root: Path) -> "JobContext":
        def path(name: str, fallback: Path) -> Path:
            return Path(env[name]) if env.get(name) else fallback

        return cls(
            working_dir=path("DOMINO_WORKING_DIR", local_root),
            artifacts_dir=path("DOMINO_ARTIFACTS_DIR", local_root / "artifacts"),
            datasets_dir=path("DOMINO_DATASETS_DIR", local_root / "data"),
            is_git_based=_flag(env, "DOMINO_IS_GIT_BASED"),
            is_flow_task=_flag(env, "DOMINO_IS_WORKFLOW_JOB"),
            run_id=env.get("DOMINO_RUN_ID", "local"),
            run_number=env.get("DOMINO_RUN_NUMBER", "0"),
            project_owner=env.get("DOMINO_PROJECT_OWNER", "local"),
            project_name=env.get("DOMINO_PROJECT_NAME", "local"),
        )


def test_reads_git_based_flag(tmp_path: Path) -> None:
    ctx = JobContext.from_env({"DOMINO_IS_GIT_BASED": "true"}, local_root=tmp_path)
    assert ctx.is_git_based and ctx.artifacts_dir == tmp_path / "artifacts"
```

## Notes

- The variables to know: `DOMINO_WORKING_DIR`, `DOMINO_ARTIFACTS_DIR`, `DOMINO_DATASETS_DIR`, `DOMINO_IMPORTED_CODE_DIR`, `DOMINO_IMPORTED_DATA_DIR`, `DOMINO_IMPORTED_ARTIFACTS_DIR`, `DOMINO_IS_GIT_BASED`, `DOMINO_IS_WORKFLOW_JOB`, `DOMINO_RUN_ID`, `DOMINO_RUN_NUMBER`, `DOMINO_PROJECT_ID`, `DOMINO_PROJECT_OWNER`, `DOMINO_PROJECT_NAME`, `DOMINO_STARTING_USERNAME`, `DOMINO_USER_NAME`, `DOMINO_HARDWARE_TIER_ID` and `DOMINO_API_HOST` (API access in `domino-api-proxy-auth`).
- Booleans arrive as text, and the string `"false"` is truthy in Python.
- The 6.2 docs give two Git-based dataset paths (`/mnt/local` and `/mnt/data`), so code reads `DOMINO_DATASETS_DIR` and never either literal.
- Importing another project moves a DFS project's working directory to `/mnt/<owner>/<project>`.
- Never set these names yourself (`domino-env-var-names`).
- Where the repo uses pydantic-settings, the settings class of `pydantic-typed-settings` (python-coding skill) can own these fields.
- Tests pass a mapping to `from_env`; where a test must set real environment variables, the python-testing skill shows how.
- The 6.2 glossary names these variables but gives no values per project type, so log the resolved roots once at startup and check them on the first run on a deployment.
- The where-outputs-go reference of this skill lists which variable gives each location.
