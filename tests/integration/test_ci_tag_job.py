"""The ``tag-release`` CI job (#281 ticket 11): thin, push-only, after ``test``, least privilege.

Merging the release pull request is the release: on a push to ``main`` this job
runs ``scripts/release.py tag --tested-commit <sha>``, which decides in
``coding_agent_playbook.release.tagging`` whether that commit is a release and
tags it. These tests pin the workflow wiring a later edit could quietly weaken:
the permissions (write only for the tag push), the ``needs: test`` gate whose
job name the manual fallback reads, first-party actions and the full history.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

import yaml

from coding_agent_playbook.release.tagging import TEST_JOB
from release_tag import CI_WORKFLOW

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / CI_WORKFLOW
TAG_JOB = "tag-release"
TAG_ARGV = ["python", "scripts/release.py", "tag", "--tested-commit", "$TESTED_COMMIT"]


def _workflow() -> dict[Any, Any]:
    data = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{WORKFLOW_PATH} must be a YAML mapping, got {data!r}"
    return data


def _tag_job() -> dict[str, Any]:
    jobs = _workflow()["jobs"]
    assert TAG_JOB in jobs, f"missing job {TAG_JOB!r} in {WORKFLOW_PATH}; jobs: {sorted(jobs)}"
    job: dict[str, Any] = jobs[TAG_JOB]
    return job


def _tag_step() -> dict[str, Any]:
    steps = [s for s in _tag_job()["steps"] if "scripts/release.py tag" in s.get("run", "")]
    assert len(steps) == 1, _tag_job()["steps"]
    return dict(steps[0])


def test_the_workflow_token_is_read_only_unless_a_job_asks_for_more() -> None:
    assert _workflow()["permissions"] == {"contents": "read"}
    for name, job in _workflow()["jobs"].items():
        if name != TAG_JOB:
            assert "permissions" not in job, f"{name} widens the token: {job['permissions']!r}"


def test_the_tag_job_may_only_write_contents_to_push_the_tag() -> None:
    assert _tag_job()["permissions"] == {"contents": "write"}


def test_the_tag_job_runs_on_pushes_to_main_after_the_test_job() -> None:
    job = _tag_job()

    assert job["needs"] == TEST_JOB  # the job name release.py tag reads by hand, too
    assert job["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    assert _workflow()[True]["push"]["branches"] == ["main"]  # PyYAML reads `on:` as True


def test_the_tag_job_uses_first_party_actions_and_the_full_history() -> None:
    steps = _tag_job()["steps"]
    uses = [str(s["uses"]) for s in steps if "uses" in s]

    assert uses and all(u.startswith(("actions/checkout@", "actions/setup-python@")) for u in uses)
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0  # the first-parent walk and the tags


def test_the_tag_step_is_one_release_py_call_on_env_inputs_only() -> None:
    step = _tag_step()

    assert shlex.split(step["run"]) == TAG_ARGV
    assert step["env"]["TESTED_COMMIT"] == "${{ github.sha }}"
    assert "${{" not in step["run"]
    # An annotated tag needs a tagger: the Actions bot, never a person.
    assert step["env"]["GIT_COMMITTER_NAME"] == "github-actions[bot]"
