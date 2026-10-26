---
id: domino-job-schedules
name: Job schedules
description: "Document every scheduled job in the repo, write Quartz expressions with seconds and a plain-words meaning, and choose Run sequentially deliberately."
scope: scoped
globs:
  - "**/*.py"
  - "**/*.sh"
  - "README.md"
applies_if:
  domino_project: true
section: scheduling-and-launching
priority: 44
tags: [python, domino, jobs, scheduling]
---

# Document schedules and write Quartz expressions

## Description

A scheduled job is configured in the Domino UI, not in the repo: its command, branch or commit, hardware tier, environment revision, datasets, cron expression and the "Run sequentially" choice live in the project settings, where a reviewer of the code never sees them. The repo therefore documents each schedule next to the code it runs.

Schedules take Quartz expressions, which differ from Unix cron: they start with a seconds field (six fields, plus an optional year: second, minute, hour, day of month, month, day of week), and one of the two day fields must be `?`. A five-field Unix expression pasted into the form means something else or is refused.

With "Run sequentially" on, the next run waits for the previous one to finish, so an hourly job that takes 90 minutes delays every later run. With it off, runs overlap, which is safe only when a run never reads the previous run's output and writes only run-scoped paths.

## Bad Example

```text
Schedule "hourly-sync", Run sequentially: off
Cron expression: 0 5 * * *
Command: python sync.py    # appends to /mnt/data/shared/sync.csv
```

The Unix expression is not valid Quartz, nothing in the repo records the schedule, and overlapping runs append to one shared file.

## Good Example

```markdown
## Scheduled jobs

| Name | Command | Quartz expression | Meaning | Sequential | Environment revision |
| --- | --- | --- | --- | --- | --- |
| nightly-features | `python -m jobs.features` | `0 0 5 * * ?` | every day at 05:00 | yes | 64f0c2a1 rev 7 |
| hourly-sync | `python -m jobs.sync` | `0 5 * ? * *` | minute 5 of every hour | yes | 64f0c2a1 rev 7 |
| weekday-report | `python -m jobs.report` | `0 0 6 ? * MON-FRI` | weekdays at 06:00 | no | 64f0c2a1 rev 7 |
```

Each row names the exact command, the expression with its meaning in words, the overlap choice and the pinned environment revision, so anyone can review or recreate the schedule.

## Notes

- State the meaning beside every expression: one 6.2 page describes `0 5 * ? * *` as running once a day, but it fires at minute 5 of every hour.
- The docs do not name the scheduler's time zone; confirm it on the deployment before relying on wall-clock times.
- A schedule defaults to the latest environment revision; pin one (domino-environment-revisions).
- "Update Domino endpoint" republishes after the run completes, so validate a model before writing it and exit non-zero on failure (domino-job-exit-codes).
- Copying a project does not copy its schedules; the README table is how someone recreates them.
- Repeated and overlapping runs follow domino-idempotent-jobs and domino-run-scoped-writes.
- Multi-step pipelines belong in Flows or an external orchestrator (domino-launch-jobs-from-code), not in a chain of schedules timed to follow each other.
