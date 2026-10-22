---
id: domino-jobs
name: domino-jobs
description: "Guides Domino 6.2 jobs and the run basics Apps and agents share."
playbook:
  use_when: "writing code a Domino job, schedule, Launcher or Flow runs"
  files: "Job and Launcher scripts, requirements.txt, Dockerfiles and Domino dotfiles"
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

# Domino Jobs

A Domino job is a headless run of one script in a fresh container, started from the UI, a schedule, a Launcher, the CLI, the API or a Flow. When it ends, Domino keeps only what the project type syncs back, so where a file is written decides whether it survives. This skill targets Domino 6.2; where a newer release behaves differently, the rule says so. Its first section holds the run basics that the domino-apps and domino-agents skills rely on instead of restating them.

## Quick reference

| | DFS project | Git-based project | Flow task |
| --- | --- | --- | --- |
| Working directory | `/mnt` (moves to `/mnt/<owner>/<project>` with imports) | `/mnt/code`, the repository | as its project type |
| Outputs that persist | new and changed project files | only `/mnt/artifacts`; code changes are not saved | only the declared outputs under `/workflow/outputs` |
| Datasets | `/domino/datasets/local/<name>` | `DOMINO_DATASETS_DIR` (`/mnt/data/<name>`) | one snapshot per dataset at the plain dataset path |
| Snapshots | `/domino/datasets/local/snapshots/<name>/<number>` | `/mnt/data/snapshots/<name>/<number>` | chosen in the flow definition |
| Tells the type apart | `DOMINO_IS_GIT_BASED` is `false` | `DOMINO_IS_GIT_BASED` is `true` | `DOMINO_IS_WORKFLOW_JOB` is `true` |

Every job also:

- exits non-zero when it fails, so schedules, emails and callers see the failure;
- persists only through its project type's synced location;
- reads its paths, identity and secrets from environment variables, parsing `"true"` and `"false"` as text;
- calls the Domino API through the run's proxy, with no credential in code;
- keeps big data in Datasets and reads snapshots when its results must be reproducible;
- stays idempotent, so a scheduled, retried or re-run job repeats safely.

## See also

- python-coding: error handling, retries and timeouts, typed settings, Protocol seams.
- python-testing: monkeypatch for the DOMINO_* variables.
- python-tooling: dependency pins.
- ml-data: seeded randomness and serialization security.
- domino-apps: published Apps.
- domino-agents: agents.
