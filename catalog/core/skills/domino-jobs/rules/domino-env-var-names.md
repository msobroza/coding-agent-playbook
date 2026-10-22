---
id: domino-env-var-names
name: Variable names
description: "Give every custom environment variable one organization or application prefix, and never use a name or prefix Domino reserves."
version: 1
scope: scoped
globs:
  - "**/settings.py"
  - "**/config.py"
  - "**/*.sh"
  - ".env.example"
  - "**/Dockerfile*"
applies_if:
  domino_project: true
section: project-and-run-environment
priority: 24
tags: [python, domino, jobs, configuration]
---

# Variable names

## Description

Domino reserves the exact names `USER`, `LOGNAME` and `MLFLOW_TRACKING_URI`, and every name that starts with `DOMINO_`, `KUBERNETES_`, `NEW_RELIC_`, `DATA_PLANE_`, `MINICONDA_`, `FLYTE_`, `HEPHAESTUS_`, `SELDON_`, `CONDA_` or `DISTRIBUTED_COMPUTE_`. The docs call the exact names examples, so treat every injected name in the glossary as reserved too. A project or user variable with such a name overrides the platform's own setting without a warning.

A name starts with a letter and uses only letters, digits and underscores. Every custom variable carries one organization or application prefix, kept as a constant in the settings module.

## Bad Example

```text
DOMINO_DB_URL=postgresql://db.example.com/sales   # inside a reserved prefix
CONDA_ENV=analytics                                # inside a reserved prefix
MLFLOW_TRACKING_URI=http://mlflow.example.com      # replaces Domino's own value
db-url=postgresql://db.example.com/sales           # not a valid name
```

## Good Example

```python
import os
import re
from collections.abc import Mapping

PREFIX = "ACME_CHURN_"
NAME_SYNTAX = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
EXPECTED = f"{PREFIX}<NAME>: letters, digits and underscores, starting with a letter"
RESERVED_NAMES = frozenset({"USER", "LOGNAME", "MLFLOW_TRACKING_URI"})
RESERVED_PREFIXES = (
    "DOMINO_",
    "KUBERNETES_",
    "NEW_RELIC_",
    "DATA_PLANE_",
    "MINICONDA_",
    "FLYTE_",
    "HEPHAESTUS_",
    "SELDON_",
    "CONDA_",
    "DISTRIBUTED_COMPUTE_",
)


def check_variable_name(name: str) -> None:
    if not NAME_SYNTAX.fullmatch(name):
        raise ValueError(f"{name!r} is not a valid name; expected {EXPECTED}")
    if name in RESERVED_NAMES:
        raise ValueError(f"{name!r} is reserved by Domino; expected {EXPECTED}")
    for prefix in RESERVED_PREFIXES:
        if name.startswith(prefix):
            raise ValueError(f"{name!r} uses the reserved prefix {prefix}; expected {EXPECTED}")
    if not name.startswith(PREFIX):
        raise ValueError(f"{name!r} lacks the prefix {PREFIX}; expected {EXPECTED}")


def setting(key: str, env: Mapping[str, str] | None = None) -> str | None:
    """ACME_CHURN_<key>, e.g. setting("DB_URL") or setting("BATCH_SIZE")."""
    return (os.environ if env is None else env).get(PREFIX + key)
```

```python
import pytest


@pytest.mark.parametrize(
    "name", ["DOMINO_DB_URL", "CONDA_ENV", "MLFLOW_TRACKING_URI", "db-url", "DB_URL"]
)
def test_names_outside_the_prefix_are_rejected(name: str) -> None:
    with pytest.raises(ValueError, match=name):
        check_variable_name(name)
```

## Notes

- The same name set at several levels resolves compute environment, then project, then user, and the last one wins, so one user's variable can change a shared job. List the variables a job expects in the README.
- Compute-environment variables need an `ARG` and an `ENV` line in the Dockerfile instructions and a rebuild; the image build cannot read user variables (`domino-pinned-environments`).
- python-domino's tuning variables (`DOMINO_LOG_LEVEL`, `DOMINO_MAX_RETRIES`, `DOMINO_VERIFY_CERTIFICATE`) sit inside the reserved prefix: set them only in a local or test process, never as project or user variables, and never turn certificate verification off.
- Injected defaults are absent in Model Manager.
- MLflow configuration is in `domino-mlflow-tracking`.
