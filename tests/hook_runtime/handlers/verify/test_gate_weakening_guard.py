"""gate-weakening-guard: the ``gate-integrity`` stage and its ``pre_edit`` companion (specs/prK-hook-pack.md §E.2).

The Stop side runs through ``playbook-hook simulate stop`` with the
coordinator and this hook on: ``FakeGit.worktree_diffs["HEAD"]`` is the
working tree's ``-U0`` diff, ``head_blobs`` the config files at ``HEAD``.
The companion runs through ``simulate pre_tool_use`` on real files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.policy import UNATTENDED_ENV_VAR
from coding_agent_playbook.hook_runtime.dispatch.registry import load_builtin
from coding_agent_playbook.hook_runtime.git.parse import AddedLine, DiffLines, RemovedLine
from coding_agent_playbook.hook_runtime.handlers.verify.gate_weakening_guard import (
    FIX_HINT,
    scan_policy,
)
from coding_agent_playbook.hook_runtime.judges.gate_weakening import ScanPolicy
from tests.hook_runtime.handlers.pack_repo import engine_hook
from tests.hook_runtime.handlers.stop_kit import changed_git, reason_lines, stop, stop_payload

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from tests.hook_runtime.fakes import FakeGit
    from tests.hook_runtime.handlers.pack_repo import PackRepo

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "gate-weakening-guard"
GATE_ID: Final = "stop-ci-parity-gate"
ADDOPTS: Final = '[tool.pytest.ini_options]\naddopts = [\n    "--cov-fail-under={}",{}\n]\n'
REASON: Final = "  # integration suite moved to nightly"
TEST_FILE: Final = "tests/test_parse.py"


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.write("src/x.py", "x = f()\n")
    pack_repo.write(TEST_FILE, "def test_parse() -> None:\n    assert True\n")
    pack_repo.install_pack([GATE_ID, HOOK_ID])
    return pack_repo


def _diff(*added: tuple[str, int, str], head: dict[str, bytes] | None = None) -> FakeGit:
    lines = tuple(AddedLine(path, n, text) for path, n, text in added)
    diff = DiffLines(added=lines, paths=tuple(dict.fromkeys(line.path for line in lines)))
    return changed_git(worktree_diffs={"HEAD": diff}, head_blobs=head or {})


def _stop(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], git: FakeGit, state: Path
) -> SimulateReport:
    return stop(repo, deps, stop_payload(repo, message="Done."), git=git, state=state)


def _cov_loosened(repo: PackRepo, *, reason: str = "") -> FakeGit:
    repo.write("pyproject.toml", ADDOPTS.format(70, reason))
    added = ("pyproject.toml", 3, f'    "--cov-fail-under=70",{reason}')
    return _diff(added, head={"pyproject.toml": ADDOPTS.format(80, "").encode()})


def test_bare_type_ignore_block_line(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    git = _diff(("src/x.py", 1, "x = f()  # type: ignore"))

    report = _stop(repo, deps, git, tmp_path)

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1:] == [
        '[gate-integrity] "src/x.py":1 type-ignore: "x = f() # type: ignore"',  # flattened
        f"[gate-integrity] {FIX_HINT}",
    ]


def test_justified_type_ignore_none(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    git = _diff(("src/x.py", 1, "x = f()  # type: ignore[attr-defined]  # stub gap"))

    report = _stop(repo, deps, git, tmp_path)

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.user_notes == (
        "verified locally (lint, gate-integrity); the CI matrix is authoritative",
    )


def test_lowering_cov_fail_under_block_plus_user_note(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    report = _stop(repo, deps, _cov_loosened(repo), tmp_path)

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1].startswith('[gate-integrity] "pyproject.toml" config-loosening')
    [note] = [n for n in report.trace.combined.user_notes if n.startswith("Gate loosened")]
    assert "--cov-fail-under 80 → 70" in note


def test_justified_loosening_user_note_only(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    report = _stop(repo, deps, _cov_loosened(repo, reason=REASON), tmp_path)

    assert report.trace.combined.decision is Decision.NONE
    [note] = [n for n in report.trace.combined.user_notes if n.startswith("Gate loosened")]
    assert note.startswith('Gate loosened (justified): "pyproject.toml" config-loosening:')


def test_untracked_file_and_secret_paths(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.write("src/new.py", "import requests\nrequests.get(u, verify=False)\n")
    repo.write(".env", "TOKEN=x  # noqa\n")
    git = changed_git(untracked=("src/new.py", ".env"))

    report = _stop(repo, deps, git, tmp_path)

    assert reason_lines(report)[1:-1] == [
        '[gate-integrity] "src/new.py":2 verify-false: "requests.get(u, verify=False)"'
    ]


def test_same_fingerprint_second_stop_none(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    git = _diff(("src/x.py", 1, "x = f()  # type: ignore"))

    first = _stop(repo, deps, git, tmp_path)
    chained = stop_payload(repo, message="Done.", case="block_chain")  # stop_hook_active: true
    second = stop(repo, deps, chained, git=git, state=tmp_path)

    assert first.trace.combined.decision is Decision.DENY
    assert second.trace.combined.decision is Decision.NONE
    assert second.trace.combined.user_notes == (
        "Playbook gate RED at gate-integrity — NOT verified.",
    )


def test_without_the_coordinator_the_stage_blocks_alone_once(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    pack_repo.write("src/x.py", "x = f()\n")
    pack_repo.install_pack([HOOK_ID])
    git = _diff(("src/x.py", 1, "x = f()  # type: ignore"))

    first = _stop(pack_repo, deps, git, tmp_path)
    second = _stop(pack_repo, deps, git, tmp_path)

    assert first.trace.combined.decision is Decision.DENY
    assert reason_lines(first)[-1] == f"[gate-integrity] {FIX_HINT}"
    assert second.trace.combined.decision is Decision.NONE
    assert second.trace.combined.user_notes == (
        "Playbook gate RED at gate-integrity — NOT verified.",
    )


# --- the pre_edit companion -------------------------------------------------------------------


def _edit(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], new: str, *, env: dict[str, str] | None = None
) -> SimulateReport:
    tool_input = {
        "file_path": str(repo.root / TEST_FILE),
        "old_string": "def test_parse() -> None:",
        "new_string": new,
    }
    return repo.simulate(repo.tool_payload("Edit", tool_input), deps(), env=env)


SKIPPED: Final = '@pytest.mark.skip(reason="flaky")\ndef test_parse() -> None:'


def test_edit_adding_skip_marker_asks(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    report = _edit(repo, deps, SKIPPED)

    assert report.trace.combined.decision is Decision.ASK
    assert report.trace.combined.reason.startswith(
        f'"{TEST_FILE}": the edit adds pytest-skip-marker'
    )


def test_edit_adding_skip_marker_headless_denies(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    report = _edit(repo, deps, SKIPPED, env={UNATTENDED_ENV_VAR: "1"})

    assert report.trace.combined.decision is Decision.DENY


@pytest.mark.parametrize(
    "new",
    [
        "def test_parse() -> None:  # renamed nothing",
        '@pytest.mark.xfail(strict=True, reason="bug 12")\ndef test_parse() -> None:',
        "@pytest.mark.skip  # quarantined: issue #42 until the upstream fix\ndef test_parse() -> None:",
    ],
)
def test_edit_without_unjustified_skip_passes(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], new: str
) -> None:
    assert _edit(repo, deps, new).trace.combined.decision is Decision.NONE


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (f"rm {TEST_FILE}", Decision.ASK),
        (f"git rm -q {TEST_FILE}", Decision.ASK),
        (f"mv {TEST_FILE} /tmp/x.py", Decision.ASK),
        ("rm -r tests", Decision.ASK),
        ("rm src/x.py", Decision.NONE),
        (f"cat {TEST_FILE}", Decision.NONE),
    ],
)
def test_deleting_test_file_asks(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], command: str, expected: Decision
) -> None:
    report = repo.simulate(repo.tool_payload("Bash", {"command": command}), deps())

    assert report.trace.combined.decision is expected


# --- one policy source ------------------------------------------------------------------------


def test_hook_md_config_equals_gate_scan_defaults(tmp_path: Path) -> None:
    """The shipped hook adds nothing to ``judges.gate_weakening``'s policy: hook and CLI twin agree."""
    fm = engine_hook(HOOK_ID).frontmatter
    stop_handler, edit_handler = fm.handlers["stop"], fm.handlers["pre_tool_use"]
    assert stop_handler.builtin is not None and edit_handler.builtin is not None
    declaration = load_builtin(stop_handler.builtin)

    policy = scan_policy(stop_handler.config, str(tmp_path))

    assert policy == ScanPolicy(source_roots=("",))
    assert set(stop_handler.config) <= set(declaration.config_schema)
    assert {e.value for e in load_builtin(edit_handler.builtin).events} == {"pre_tool_use"}
    assert (fm.tier, tuple(fm.events), fm.on_error) == ("default", ("stop", "pre_tool_use"), "ask")


# --- GitLab CI files (prF §10.3) ----------------------------------------------------------------

GITLAB_CI: Final = (
    "lint:\n  script:\n    - ruff check .\n\nplaybook-ci:\n  script:\n    - playbook ci\n"
)


def test_a_removed_gitlab_ci_job_blocks(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    after = GITLAB_CI.replace("lint:\n  script:\n    - ruff check .\n\n", "")
    repo.write(".gitlab-ci.yml", after)
    removed = tuple(
        RemovedLine(".gitlab-ci.yml", n, text)
        for n, text in enumerate(GITLAB_CI.splitlines()[:4], 1)
    )
    diff = DiffLines(removed=removed, paths=(".gitlab-ci.yml",))
    git = changed_git(
        worktree_diffs={"HEAD": diff}, head_blobs={".gitlab-ci.yml": GITLAB_CI.encode()}
    )

    report = _stop(repo, deps, git, tmp_path)

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1] == (
        '[gate-integrity] ".gitlab-ci.yml" gitlab-ci-job-removed: "job \'lint\' removed"'
    )


def test_scan_policy_reads_ci_config_globs(tmp_path: Path) -> None:
    policy = scan_policy({"ci_config_globs": ["ci/*.gitlab-ci.yml"]}, str(tmp_path))

    assert policy.ci_config_globs[-1] == "ci/*.gitlab-ci.yml"


# --- scanner settings (prF §14) -----------------------------------------------------------------


def test_a_changed_gitlab_sast_ruleset_blocks(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    git = _diff((".gitlab/sast-ruleset.toml", 2, "  [[semgrep.ruleset]]"))

    report = _stop(repo, deps, git, tmp_path)

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1] == (
        '[gate-integrity] ".gitlab/sast-ruleset.toml" scanner-config-changed: '
        '".gitlab/sast-ruleset.toml changed"'
    )


def test_a_workflow_excluding_paths_from_secret_detection_blocks(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    git = _diff((".github/workflows/ci.yml", 4, "  SECRET_DETECTION_EXCLUDED_PATHS: src/"))

    report = _stop(repo, deps, git, tmp_path)

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1] == (
        '[gate-integrity] ".github/workflows/ci.yml" scanner-loosened-in-ci: '
        '"sets SECRET_DETECTION_EXCLUDED_PATHS: src/"'
    )
