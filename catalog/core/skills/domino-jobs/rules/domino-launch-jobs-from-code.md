---
id: domino-launch-jobs-from-code
name: Launching jobs from code
description: "Start Domino jobs from code with an explicit command, commit, environment and tier, wait with a deadline, and treat every final state but Succeeded as an error."
scope: scoped
globs:
  - "**/*.py"
  - "**/dags/**/*.py"
applies_if:
  domino_project: true
section: scheduling-and-launching
priority: 47
tags: [python, domino, jobs, scheduling]
---

# Launch jobs from code with pinned inputs and a deadline

## Description

Code that starts Domino jobs (a pipeline step, another job, CI, an Airflow task) passes the command, commit ID, environment ID and hardware tier explicitly: each one left out defaults to the latest commit or the project's defaults, so the job silently runs different code on a different image. It waits with a bound, and it treats every final state other than Succeeded (Failed, Error, Stopped, or still running at the deadline) as an error the caller sees.

## Bad Example

```python
domino = Domino("team/churn")
job = domino.job_start(command="train.py")  # latest commit, default environment and tier
while domino.job_status(job["id"])["statuses"]["executionStatus"] != "Succeeded":
    time.sleep(5)  # spins forever when the job fails
```

## Good Example

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class JobRequest:
    command: str
    commit_id: str
    environment_id: str
    hardware_tier_name: str


class JobFailedError(RuntimeError):
    def __init__(self, job_id: str, state: str) -> None:
        super().__init__(f"Domino job {job_id!r} ended in state {state!r}, expected 'Succeeded'")
        self.job_id = job_id
        self.state = state


class JobLauncher(Protocol):
    def start_blocking(self, request: JobRequest, *, max_poll_time: int) -> str: ...
    def state(self, job_id: str) -> str: ...


class DominoJobLauncher:
    """Adapter over the python-domino client."""

    def __init__(self, client: Domino) -> None:
        self._client = client

    def start_blocking(self, request: JobRequest, *, max_poll_time: int) -> str:
        job = self._client.job_start_blocking(
            command=request.command,
            commit_id=request.commit_id,
            environment_id=request.environment_id,
            hardware_tier_name=request.hardware_tier_name,
            max_poll_time=max_poll_time,
        )
        return str(job["id"])

    def state(self, job_id: str) -> str:
        return str(self._client.job_status(job_id)["statuses"]["executionStatus"])


def start_and_wait(launcher: JobLauncher, request: JobRequest, *, timeout_s: int) -> str:
    job_id = launcher.start_blocking(request, max_poll_time=timeout_s)
    state = launcher.state(job_id)
    if state != "Succeeded":
        raise JobFailedError(job_id, state)
    return job_id
```

A fake `JobLauncher` returning "Succeeded" or "Failed" tests both paths without Domino.

## Notes

- The 6.2 docs give `job_start_blocking` a `max_poll_time` (default 6000 seconds) but say only of the older `runs_start_blocking` that exceeding it raises, and neither says what a failed job returns, so the deadline and the state check stay explicit in one function.
- `job_start` takes no environment revision (domino-environment-revisions) and takes the tier by name, so record the tier ID the run reports.
- Authentication is domino-api-proxy-auth: the proxy inside runs, a service-account token outside.
- Orchestrators only trigger jobs; the work code stays in the Domino project. Airflow workers install the `dominodatalab[airflow]` extra.
- The Platform API starts jobs with `POST /api/jobs/v1/jobs` and has no v1 stop endpoint, so stop through `job_stop` and choose `commit_results` deliberately.
- Domino 6.2 needs `dominodatalab` 2.0 or later. For local development `domino run --wait` blocks until the job ends; CLI versions before 6.2.3 cannot log in.
- The port and adapter shapes are python-protocols (python-coding) and design-adapter (design-patterns).
