---
id: domino-pinned-environments
name: Pinned environments
description: "Bake a job's dependencies into its compute environment's Dockerfile instructions with exact versions, and keep requirements.txt to a few exactly pinned packages."
version: 1
scope: scoped
globs:
  - "requirements*.txt"
  - "**/Dockerfile*"
  - "**/*.dockerfile"
  - "pyproject.toml"
applies_if:
  domino_project: true
section: project-and-run-environment
priority: 25
tags: [domino, jobs, dependencies]
---

# Pinned environments

## Description

Every job starts a fresh container from its compute environment's image. A `requirements.txt` in the project is installed with pip over the network at the start of every execution: it slows startup, fails when the package index is unreachable, and drifts whenever versions float.

A job's dependencies are baked into the environment's Dockerfile instructions with exact versions. `requirements.txt` holds only the few packages that change faster than the image, also pinned exactly.

## Bad Example

```text
# requirements.txt: reinstalled on every run, different versions over time
pandas
scikit-learn>=1.0
```

```python
import subprocess
import sys

# Installs at import time, over the network, on every run.
subprocess.run([sys.executable, "-m", "pip", "install", "xgboost"], check=True)
import xgboost
```

## Good Example

```dockerfile
# Environment Dockerfile instructions: Domino adds the FROM line.
USER root
RUN pip install --no-cache-dir \
    pandas==2.2.3 \
    scikit-learn==1.5.2 \
    xgboost==2.1.3
USER ubuntu
```

```text
# requirements.txt: only what changes faster than the image, pinned exactly
acme-features==0.14.2
```

## Notes

- `requirements.txt` sits at the project root, or at the code repository root in a Git-based project.
- Domino adds the `FROM` line. Install as root, then switch back to `ubuntu`, the user runs execute as.
- One `pip install` command lets the resolver see every pin at once; images are limited to 127 layers.
- The image build cannot read project files or user variables, so build steps never need a secret or a repository file.
- Pre-setup, post-setup and pre-run scripts run as root at every start and never on Spark, Ray, Dask or MPI workers, which need everything in the cluster image.
- The 6.2 docs define the post-run script two ways, so nothing may depend on when it runs.
- Where the repo uses uv, export the pinned list from its lock file instead of keeping a second list by hand (`python-uv-workflow`, python-tooling skill).
- Private Git dependencies use the Git integration, never a token in a URL (`domino-secrets-in-env-vars`).
- Which environment revision a job runs on is `domino-environment-revisions`.
