---
id: domino-jobs
name: domino-jobs
description: "Guides Domino 6.2 jobs and the run basics Apps and agents share."
playbook:
  use_when: "writing code a Domino job, schedule, Launcher or Flow runs"
  files: "Domino Job and Launcher scripts, requirements.txt, environments and dotfiles"
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
  references:
    - path: references/where-outputs-go.md
      open_when: "Deciding where a job's file goes, or a job's output is missing, unexpectedly in Results, too slow to sync or overwritten by another run."
      applies_if:
        domino_project: true
---

# Domino jobs

A Domino job is a headless run of one script in a fresh container, started from the UI, a schedule, a Launcher, the CLI, the API or a Flow. Nothing in that container survives the run except what the project type syncs back and what was written to a Dataset, so a job's code decides deliberately where every file goes, where its settings come from and what its exit status says.

This skill targets Domino 6.2; where the 6.2 documentation leaves a fact out or contradicts itself, the rule states the safe behavior and says so. Its first section holds the run basics that the domino-apps and domino-agents skills name by rule id instead of restating.

## Quick reference

| | DFS project | Git-based project | Flow task |
| --- | --- | --- | --- |
| Working directory | `/mnt` (`/mnt/<owner>/<project>` once another project is imported) | `/mnt/code`, the repository checkout | as its project type |
| What persists after the run | every file under the working directory, minus `.dominoignore` matches | only the artifacts directory (`/mnt/artifacts`); code edits are lost | only the declared outputs under `/workflow/outputs` |
| Datasets | mounted under the datasets directory, snapshots by number | mounted under the datasets directory, snapshots by number | one chosen snapshot per dataset, at the plain dataset path |
| How code tells | `DOMINO_IS_GIT_BASED` is not `"true"` | `DOMINO_IS_GIT_BASED` is `"true"` | `DOMINO_IS_WORKFLOW_JOB` is `"true"` |

Six musts for every job:

- Exit non-zero on failure; Domino, schedules and callers read only the exit status.
- Persist results only through the project type's synced location or a Dataset.
- Read paths, identity and secrets from environment variables, once, at startup.
- Call the Domino API through the run's API proxy, with no credential in the code.
- Keep big data in Datasets, and read snapshots when results must be reproducible.
- Make scheduled, re-run and retried jobs idempotent.

## See also

- python-coding: error handling, retries and timeouts, typed settings, Protocol seams.
- python-testing: setting the DOMINO_* variables in tests.
- python-tooling: dependency pins.
- ml-data: seeded randomness, serialization security.
- domino-apps: Apps published on Domino.
- domino-agents: agent services on Domino.
