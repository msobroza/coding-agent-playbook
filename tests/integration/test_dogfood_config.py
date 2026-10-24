"""The engine repo dogfoods its own commit convention (specs/prK-lifecycle-hooks.md §K OQ-6).

OQ-6 commits three things and nothing else: the ``[hooks.commit_convention]``
cut-over in a repo-root ``.coding-agent-playbook.toml``, ``[tool.commitizen]``
in ``pyproject.toml``, and a pull-request ``playbook-ci`` job that runs the
``commit-convention`` step. Lifecycle hooks stay off in this repo, and the
user's ``wrapper_prefixes``, convention and trailer rows stay in their
untracked setup. These tests read the committed repo-root files the way
``test_precommit_hooks_yaml.py`` does, so a later edit that switches hooks on,
adds a policy row, moves the version source or interpolates the PR title into
a shell line fails here. The ``test`` job's lane wiring (ADR 0009) is pinned
here too: a skill-only pull request runs only the ``catalog`` checks, and every
other case runs the whole suite.
"""

from __future__ import annotations

import dataclasses
import shlex
import shutil
import subprocess
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands.twins._ci_commit_convention import COMMIT_STEP, PR_TITLE_ENV
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.config.tables.hooks import (
    CommitConventionConfig,
    GuardrailsConfig,
    HooksConfig,
    policy_tables,
)
from coding_agent_playbook.hook_runtime.judges.commit_cutover import parse_cutover

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / ".coding-agent-playbook.toml"
PYPROJECT_PATH = ROOT / "pyproject.toml"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"

#: The identity every loadable config carries: ``Config.from_dict`` requires these keys.
IDENTITY_KEYS = frozenset({"schema_version", "engine", "project"})
JOB = "playbook-ci"
PR_TITLE_EXPR = "${{ github.event.pull_request.title }}"
PLAYBOOK_CI_ARGV = ["playbook", "ci", "--steps", COMMIT_STEP, "--base", "origin/main"]
TEST_JOB = "test"
#: ``labeled`` lets the ``ci:full`` label start a run (ADR 0009); the rest are the defaults.
PR_EVENT_TYPES = frozenset({"opened", "synchronize", "reopened", "labeled"})
LANE_STEP_ID = "lane"
LANE_SELECTOR = "python -m tests.skill_lane"
#: The selector's inputs reach the shell only through env:, never interpolated into run:.
LANE_STEP_ENV = {
    "EVENT_NAME": "${{ github.event_name }}",
    "FORCE_FULL": "${{ contains(github.event.pull_request.labels.*.name, 'ci:full') }}",
}
LANE_OUTPUT_ENV = {"LANE": "${{ steps.lane.outputs.lane }}"}
FULL_LANE_ARGV = ["pytest", "-q", "-n", "auto", "--dist", "worksteal"]
SKILL_LANE_ARGV = [*FULL_LANE_ARGV, "-m", "catalog", "--no-cov"]


@pytest.fixture(autouse=True)
def _no_external_clis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Autouse: these tests read files and run validate in-process; no CLI may run."""

    def _refuse_run(args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"unexpected subprocess.run({args!r}) in a dogfood-config test")

    def _no_binary(name: str, *args: object, **kwargs: object) -> str | None:
        return None

    monkeypatch.setattr(subprocess, "run", _refuse_run)
    monkeypatch.setattr(shutil, "which", _no_binary)


def _toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _cutover() -> object:
    return _toml(CONFIG_PATH)["hooks"]["commit_convention"]["cutover_date"]


def _workflow() -> dict[Any, Any]:
    with WORKFLOW_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict), f"{WORKFLOW_PATH} must be a YAML mapping, got {data!r}"
    return data


def _job(name: str = JOB) -> dict[str, Any]:
    jobs = _workflow()["jobs"]
    assert name in jobs, f"missing job {name!r} in {WORKFLOW_PATH}; jobs: {sorted(jobs)}"
    job: dict[str, Any] = jobs[name]
    return job


def _step_running(job: dict[str, Any], command: str) -> dict[str, Any]:
    step = next((s for s in job["steps"] if command in s.get("run", "")), None)
    assert step is not None, f"no step runs {command!r}; steps: {job['steps']!r}"
    return dict(step)


def _step_with_id(job: dict[str, Any], step_id: str) -> dict[str, Any]:
    step = next((s for s in job["steps"] if s.get("id") == step_id), None)
    assert step is not None, f"no step has id {step_id!r}; steps: {job['steps']!r}"
    return dict(step)


def _checkout(job: dict[str, Any]) -> dict[str, Any]:
    uses = [s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert uses, f"no actions/checkout step; steps: {job['steps']!r}"
    return dict(uses[0])


def _pytest_step() -> dict[str, Any]:
    return _step_running(_job(TEST_JOB), "pytest -q")


def test_dogfood_config_sets_only_the_commit_cutover() -> None:
    data = _toml(CONFIG_PATH)

    assert set(data) == IDENTITY_KEYS | {"hooks"}, sorted(data)
    assert set(data["hooks"]) == {"commit_convention"}, data["hooks"]
    assert set(data["hooks"]["commit_convention"]) == {"cutover_date"}


def test_dogfood_cutover_is_an_iso_date_string() -> None:
    cutover = _cutover()

    # An unquoted TOML date loads as datetime.date, which the engine rejects (D-Q3).
    # The value itself is not pinned: it moves to the hooks PR's merge date.
    assert isinstance(cutover, str), f"cutover_date must be a quoted string, got {cutover!r}"
    assert parse_cutover(cutover) == date.fromisoformat(cutover)


def test_dogfood_config_keeps_hooks_off() -> None:
    tables = policy_tables(_toml(CONFIG_PATH), {})
    hooks = tables.hooks_config()

    # Everything but the cut-over is the absent-table default: no byte change (§I).
    assert hooks.enabled is False
    assert dataclasses.replace(hooks, commit_convention=CommitConventionConfig()) == HooksConfig()
    assert tables.guardrails_config() == GuardrailsConfig()


def test_dogfood_config_passes_engine_config_parsing() -> None:
    config = FileSystemStateSource(repo_root=ROOT).load_primary_config()
    tables = policy_tables(config.extra_tables, {})

    assert tables.hooks_config().commit_convention.cutover_date == _cutover()
    assert config.project.name == "coding-agent-playbook"
    assert config.overlays_enabled == []
    assert config.adapters_enabled == []
    assert config.commit_output is False


def test_engine_root_validates_with_dogfood_config(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["validate", "--repo-root", str(ROOT)])
    out = capsys.readouterr().out

    assert exit_code == 0, out
    assert "validating the engine package" not in out  # the H15/H16/H21 policy rows ran


def test_pyproject_commitizen_uses_conventional_commits() -> None:
    commitizen = _toml(PYPROJECT_PATH)["tool"]["commitizen"]

    # No version or bump keys: hatch's [project] version stays the one version source.
    assert commitizen == {"name": "cz_conventional_commits"}


def test_ci_playbook_ci_job_runs_commit_convention_on_pull_requests_only() -> None:
    job = _job()

    assert "pull_request" in _workflow()[True]  # PyYAML (YAML 1.1) reads `on:` as True
    assert job["if"] == "github.event_name == 'pull_request'"
    assert shlex.split(_step_running(job, "playbook ci")["run"]) == PLAYBOOK_CI_ARGV


def test_ci_playbook_ci_job_fetches_full_history() -> None:
    checkout = _checkout(_job())

    assert checkout["with"]["fetch-depth"] == 0  # playbook ci diffs <merge base>..HEAD


def test_ci_pr_title_reaches_playbook_ci_only_through_env() -> None:
    for name, job in _workflow()["jobs"].items():
        for step in job["steps"]:
            run = step.get("run", "")
            assert "github.event.pull_request.title" not in run, f"{name}: {run!r}"

    assert _step_running(_job(), "playbook ci")["env"] == {PR_TITLE_ENV: PR_TITLE_EXPR}


def test_ci_playbook_ci_job_installs_commitizen() -> None:
    argv = shlex.split(_step_running(_job(), "pip install")["run"])

    assert argv[:6] == ["python", "-m", "pip", "install", "-e", "."]
    assert [arg for arg in argv[6:] if arg.startswith("commitizen>=")], argv


def test_ci_test_matrix_and_dev_extra_stay_without_commitizen() -> None:
    install = _step_running(_job("test"), "pip install")["run"]
    dev_extra = _toml(PYPROJECT_PATH)["project"]["optional-dependencies"]["dev"]

    # commitizen lives only in the playbook-ci job: the CI-parity gate is unchanged.
    assert install == 'python -m pip install -e ".[dev]"'
    assert not [dep for dep in dev_extra if dep.startswith("commitizen")]


def test_ci_pull_requests_into_main_also_run_when_labelled() -> None:
    pull_request = _workflow()[True]["pull_request"]

    assert pull_request["branches"] == ["main"]
    assert set(pull_request.get("types", [])) == PR_EVENT_TYPES, pull_request


def test_ci_test_job_fetches_the_merge_commit_and_its_first_parent() -> None:
    checkout = _checkout(_job(TEST_JOB))

    # The selector diffs HEAD^1 against HEAD, the pull request's merge commit (ADR 0009).
    assert checkout.get("with", {}).get("fetch-depth") == 2, checkout


def test_ci_lane_step_runs_the_selector_on_env_inputs_only() -> None:
    step = _step_with_id(_job(TEST_JOB), LANE_STEP_ID)
    run = step["run"]

    assert LANE_SELECTOR in run, run
    assert '--event "$EVENT_NAME"' in run and '--force-full "$FORCE_FULL"' in run, run
    # The key the pytest step reads (steps.lane.outputs.<key>): a typo here would
    # send every pull request to the full lane without a failure.
    output_key = LANE_OUTPUT_ENV["LANE"].removeprefix("${{ steps.lane.outputs.").removesuffix(" }}")
    assert run.startswith(f'echo "{output_key}=$({LANE_SELECTOR} '), run
    assert '>> "$GITHUB_OUTPUT"' in run, run
    assert "${{" not in run, run
    assert step["env"] == LANE_STEP_ENV


def test_ci_pytest_step_runs_only_the_catalog_checks_in_the_skill_lane() -> None:
    step = _pytest_step()
    lines = [line.strip() for line in step["run"].splitlines() if line.strip()]

    assert step.get("env") == LANE_OUTPUT_ENV
    assert len(lines) == 5, step["run"]
    condition, skill_lane, otherwise, full_lane, end = lines
    # Any lane but "skill", the empty one of a crashed selector included, runs everything.
    assert condition == 'if [ "$LANE" = skill ]; then'
    assert shlex.split(skill_lane) == SKILL_LANE_ARGV
    assert (otherwise, end) == ("else", "fi")
    assert shlex.split(full_lane) == FULL_LANE_ARGV


def test_ci_lane_step_comes_before_the_pytest_step() -> None:
    job = _job(TEST_JOB)
    steps = job["steps"]
    lane = steps.index(_step_with_id(job, LANE_STEP_ID))

    assert lane < steps.index(_pytest_step()), [s.get("name") for s in steps]
