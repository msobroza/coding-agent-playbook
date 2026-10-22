---
id: domino-jobs
name: domino-jobs
description: "Guides Domino 6.2 jobs and the run basics Apps and agents share."
playbook:
  use_when: "writing code a Domino job, schedule, Launcher or Flow runs"
  files: "Domino job and Launcher scripts, requirements.txt and .domino* dotfiles"
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

A Domino job is a headless run of one script in a fresh container, started from the UI, a schedule, a Launcher, the CLI, the API or a Flow. Nothing in the container survives the run except what the project type syncs back and what was written to a Dataset, and the script's exit status is the only verdict Domino, schedules and callers see. This skill targets Domino 6.2; where the documentation contradicts itself, the rule states the safe behavior.

Its first section holds the run basics every Domino run shares: what persists, where paths, identity and secrets come from, how to reach the Domino API and which environment runs the code. The domino-apps and domino-agents skills point to those rules instead of restating them.

## Quick Reference

| | DFS project | Git-based project | Flow task |
| --- | --- | --- | --- |
| Working directory | `/mnt` | `/mnt/code` (the repo checkout) | as the project type, inputs under `/workflow/inputs` |
| Persists after the run | every changed file not ignored by `.dominoignore` | only `/mnt/artifacts`; code edits are neither committed nor pushed | only the declared files under `/workflow/outputs` |
| Datasets and snapshots | `/domino/datasets/local/<name>`, snapshots under `.../snapshots/<name>/<number>` | `/mnt/data/<name>`, snapshots under `/mnt/data/snapshots/<name>/<number>` | the chosen snapshot at the plain dataset path, read-only |
| Tells the type apart | `DOMINO_IS_GIT_BASED` is not `"true"` | `DOMINO_IS_GIT_BASED` is `"true"` | `DOMINO_IS_WORKFLOW_JOB` is `"true"` |

Every job:

- Exits non-zero on failure, and zero only after its outputs are complete.
- Persists only through its project type's synced location or a Dataset.
- Reads paths, run identity and secrets from environment variables, resolved once at startup.
- Calls the Domino API through the run's API proxy, never with a key in the code.
- Keeps big or many files in Datasets and reads snapshots when results must be reproducible.
- Stays idempotent when a schedule, a retry or a re-run starts it again.

## See Also

- python-coding: error handling, retries and timeouts, typed settings and Protocol seams.
- python-testing: monkeypatch for the DOMINO_* variables.
- python-tooling: dependency pins.
- ml-data: seeded randomness and serialization security.
- domino-apps: published Domino Apps.
- domino-agents: agents built and evaluated on Domino.
