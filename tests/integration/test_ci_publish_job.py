"""The ``publish-release`` CI job (ADR 0014): each release's metric bundle on a GitHub Release.

After ``tag-release`` tagged a release on a push to ``main``, this job checks
out the tag, builds the bundle with ``scripts/release_report.py`` and creates
the GitHub Release ``v<version>``, or updates its assets and notes when it
already exists. ``workflow_dispatch`` with a ``version`` input backfills an
older release and runs only this job. These tests pin the wiring a later edit
could quietly weaken: the trigger, the least-privilege token and first-party
actions only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from release_tag import CI_WORKFLOW

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / CI_WORKFLOW
PUBLISH_JOB = "publish-release"
TAG_JOB = "tag-release"
WRITE_JOBS = {TAG_JOB, PUBLISH_JOB}
NOT_ON_DISPATCH = "github.event_name != 'workflow_dispatch'"
VERSION_EXPR = "${{ needs.tag-release.outputs.version || inputs.version }}"
REPORT_CALL = 'python scripts/release_report.py --version "$V" --out release-report'


def _workflow() -> dict[Any, Any]:
    data = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{WORKFLOW_PATH} must be a YAML mapping, got {data!r}"
    return data


def _job(name: str) -> dict[str, Any]:
    jobs = _workflow()["jobs"]
    assert name in jobs, f"missing job {name!r} in {WORKFLOW_PATH}; jobs: {sorted(jobs)}"
    job: dict[str, Any] = jobs[name]
    return job


def _publish_script() -> str:
    return "\n".join(str(s.get("run", "")) for s in _job(PUBLISH_JOB)["steps"])


def test_publish_needs_tag_release_and_runs_on_its_output() -> None:
    job = _job(PUBLISH_JOB)

    assert job["needs"] == TAG_JOB
    assert "needs.tag-release.outputs.version != ''" in job["if"]
    assert _job(TAG_JOB)["outputs"]["version"] == "${{ steps.tag.outputs.version }}"
    tag_step = next(s for s in _job(TAG_JOB)["steps"] if s.get("id") == "tag")
    assert '--github-output "$GITHUB_OUTPUT"' in tag_step["run"]


def test_publish_is_the_only_new_job_with_contents_write() -> None:
    assert _workflow()["permissions"] == {"contents": "read"}
    assert _job(PUBLISH_JOB)["permissions"] == {"contents": "write"}
    widened = {name for name, job in _workflow()["jobs"].items() if "permissions" in job}
    assert widened == WRITE_JOBS


def test_dispatch_takes_a_version() -> None:
    version = _workflow()[True]["workflow_dispatch"]["inputs"][
        "version"
    ]  # PyYAML reads `on:` as True

    assert version["required"] is True
    assert version["type"] == "string"
    assert _job(PUBLISH_JOB)["env"]["V"] == VERSION_EXPR


def test_publish_runs_on_dispatch_even_when_tag_release_is_skipped() -> None:
    condition = _job(PUBLISH_JOB)["if"]

    assert condition.startswith("always() &&"), condition
    assert "github.event_name == 'workflow_dispatch'" in condition


def test_dispatch_skips_the_test_and_tag_jobs() -> None:
    assert NOT_ON_DISPATCH in _job("test")["if"]
    # These two already run on one other event only, so a dispatch skips them.
    assert _job(TAG_JOB)["if"].startswith("github.event_name == 'push' &&")
    assert _job("playbook-ci")["if"] == "github.event_name == 'pull_request'"


def test_publish_checks_out_the_tag_and_builds_the_bundle() -> None:
    checkout = next(s for s in _job(PUBLISH_JOB)["steps"] if "uses" in s)
    script = _publish_script()

    assert checkout["with"]["ref"] == "v${{ env.V }}"
    assert "python -m pip install -e . matplotlib" in script
    assert REPORT_CALL in script
    assert "${{" not in script  # the dispatch input reaches the shell only through env:


def test_publish_updates_an_existing_release() -> None:
    script = _publish_script()
    step = next(s for s in _job(PUBLISH_JOB)["steps"] if "gh release" in s.get("run", ""))

    assert "--clobber" in script
    assert "gh release edit" in script
    assert "gh release create" in script
    assert step["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_only_first_party_actions() -> None:
    uses = [str(s["uses"]) for s in _job(PUBLISH_JOB)["steps"] if "uses" in s]

    assert uses and all(u.startswith(("actions/checkout@", "actions/setup-python@")) for u in uses)
