---
id: domino-jobs
name: domino-jobs
description: "Guides Domino 6.2 jobs and the run basics Apps and agents share."
playbook:
  use_when: "writing code a Domino job, schedule, Launcher or Flow runs"
  files: "Job and Launcher scripts, requirements.txt and Domino dotfiles"
  sections:
    - id: project-and-run-environment
      title: "Project and run environment"
      impact: CRITICAL
      summary: "Shared by jobs, Apps and agents: what a run persists, where its paths, identity, secrets and API access come from, and which environment it runs on."
      open_when: "Any Domino job, App or agent reads a DOMINO_* variable, a /mnt or /domino path or a secret, calls the Domino API, or edits requirements.txt or its environment."
    - id: entry-points-and-exit-codes
      title: "Entry points and exit codes"
      impact: CRITICAL
      summary: "Each job or Launcher runs one non-interactive script that validates its inputs, and its exit status tells Domino, schedules and callers the truth."
      open_when: "A script becomes a job or Launcher command, parses its arguments or an uploaded file, catches a top-level exception or sets its exit status."
    - id: datasets
      title: "Datasets"
      impact: HIGH
      summary: "Large, shared and reproducible data lives in Datasets and snapshots, written so concurrent runs never clobber each other."
      open_when: "A job reads or writes big or many files, a dataset snapshot, a location concurrent runs share, or an extract from an outside source."
    - id: scheduling-and-launching
      title: "Scheduling and launching"
      impact: HIGH
      summary: "Scheduled, re-run, interrupted and code-launched jobs repeat safely on pinned inputs."
      open_when: "A job gets a cron schedule, may overlap, be re-run or retried, runs on a spot tier, or is started from code, CI or Airflow."
    - id: flow-tasks
      title: "Flow tasks"
      impact: HIGH
      summary: "A Flow task reads /workflow/inputs, writes every declared output and changes nothing else."
      open_when: "Code runs as a Domino Flow task, reads /workflow/inputs, branches on DOMINO_IS_WORKFLOW_JOB, or a DominoJobTask definition changes."
    - id: results-and-metrics
      title: "Results and metrics"
      impact: MEDIUM
      summary: "Result files, dashboard metrics, emails and logs are deliberate, stable outputs of each run."
      open_when: "A job writes report files, dominostats.json, email.html or log output, or a change edits .dominoresults or .dominoignore."
    - id: reproducibility
      title: "Reproducibility"
      impact: MEDIUM
      summary: "Every reported number traces back to the run, code, data, environment and seed that produced it."
      open_when: "A training or scoring job sets a random seed, logs MLflow params or metrics, or its numbers must be reproduced later."
---

# Domino jobs

On Domino 6.2 a job is a headless run of one script on a hardware tier and a compute environment, started from the UI, a schedule, a Launcher, a Flow, the CLI or the API. Everything the run needs comes from the project, its mounted data and injected environment variables, and everything it keeps must be written where Domino syncs it before the container goes away. These basics are shared with Apps and agents: App hosting belongs to the domino-apps skill and LLM agent services to domino-agents.

## Quick Reference

- Paths, project and run identity come from the injected `DOMINO_*` variables, never from `/mnt` literals; secrets come from project or user environment variables, never from the repo.
- One non-interactive entry script per job validates its arguments and exits non-zero on any failure, so schedules, Flows and callers see the truth.
- Large or shared data lives in Datasets and their snapshots; concurrent runs write run-scoped paths, atomically.
- A job can run again at any time (re-runs, overlapping schedules, retries, spot reclaims), so it takes its unit of work as an argument and repeats safely.
- A Flow task reads only `/workflow/inputs`, writes every declared output under `/workflow/outputs` and has no other effect.
- Result files, `dominostats.json`, `email.html` and log lines are deliberate outputs with stable names; `.dominoignore` holds only files that must never persist.
- Every reported number traces back to the run, commit, data snapshot, environment revision and seed that produced it.

```python
import os
from pathlib import Path


def output_root(env: dict[str, str]) -> Path:
    """Where this run's results go: the artifacts directory, else the working directory."""
    artifacts = env.get("DOMINO_ARTIFACTS_DIR")
    return Path(artifacts) if artifacts else Path(env["DOMINO_WORKING_DIR"])


root = output_root(dict(os.environ))
```

## See Also

- domino-apps
- domino-agents
- python-coding
- python-testing
- python-tooling
- ml-data
