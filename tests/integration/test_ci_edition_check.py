"""The editions-equal-their-tags CI step (#281 ticket 13): thin, in the job with full history.

``scripts/release.py check-editions`` compares every edition file with its
tag's blob (``release.edition_freeze.edition_tag_problems``), which needs the
tags and their history. These tests pin the wiring a later edit could quietly
break: the step runs in the pull-request job that checks out ``fetch-depth: 0``,
and its YAML is one command.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from release_tag import CI_WORKFLOW

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / CI_WORKFLOW
JOB = "playbook-ci"
COMMAND = "python scripts/release.py check-editions"


def _job() -> dict[str, Any]:
    data = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    job: dict[str, Any] = data["jobs"][JOB]
    return job


def test_the_edition_check_runs_once_as_one_command_in_the_pull_request_job() -> None:
    steps = [s for s in _job()["steps"] if "check-editions" in s.get("run", "")]

    assert [s["run"].strip() for s in steps] == [COMMAND]
    assert _job()["if"] == "github.event_name == 'pull_request'"


def test_the_job_checks_out_the_full_history_and_tags() -> None:
    checkout = next(s for s in _job()["steps"] if str(s.get("uses", "")).startswith("actions/"))

    assert checkout["uses"] == "actions/checkout@v4"
    assert checkout["with"]["fetch-depth"] == 0
