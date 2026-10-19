"""commit-message-convention: ``cz check`` on what a commit or push records (specs/prK-hook-pack.md §F.4.2).

Every case runs the shipped ``HOOK.md`` through ``playbook-hook simulate
pre_tool_use`` with Claude- and OpenCode-shaped Bash payloads. ``FakeCz``
stands in for the pinned commitizen behind ``RuntimeDeps.proc`` (any other
program fails the test) and ``FakeGit`` answers the push scan's refs and log.
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime.config.pin import write_machine_pins
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.event import Harness
from coding_agent_playbook.hook_runtime.git.safe_git import LoggedCommit
from coding_agent_playbook.hook_runtime.handlers.safety._cz import REWRITE_HINT
from tests.hook_runtime.fakes import FakeGit
from tests.hook_runtime.tool_fakes import FakeCz

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "commit-message-convention"
HEREDOC_COMMIT: Final = (
    "git commit -m \"$(cat <<'EOF'\nfeat: add parser\n\nWhy it matters.\nEOF\n)\""
)
TRACKING: Final = "refs/remotes/origin/feat/x"
NEW: Final = "2026-10-16T09:00:00+02:00"
OLD: Final = "2026-09-01T09:00:00+02:00"


@pytest.fixture
def cz_program(tmp_path: Path) -> Path:
    """The stub file ``machine.json`` pins as cz (``FakeCz`` answers its calls)."""
    program = tmp_path / "tools" / "cz"
    program.parent.mkdir()
    program.write_bytes(b"#!/bin/sh\n")
    return program


@pytest.fixture
def repo(pack_repo: PackRepo, cz_program: Path) -> PackRepo:
    pack_repo.install_pack(
        [HOOK_ID], wrapper_prefixes=("proxy",), handler_config={HOOK_ID: {"cutover_date": ""}}
    )
    _pin(pack_repo, cz_program)
    return pack_repo


def _pin(repo: PackRepo, program: Path) -> None:
    git_dir = str(repo.root / ".git")
    write_machine_pins(tools={"cz": [str(program)]}, engine_version="0.1.0a0", git_dir=git_dir)


def _git(**fields: Any) -> FakeGit:
    defaults: dict[str, Any] = {"symbolic_refs": {"HEAD": "feat/x"}}
    return FakeGit(**{**defaults, **fields})


def _bash(
    repo: PackRepo,
    deps: Deps,
    command: str,
    *,
    cz: FakeCz | None = None,
    git: FakeGit | None = None,
    harness: Harness = Harness.CLAUDE_CODE,
    state: Path | None = None,
) -> SimulateReport:
    payload = repo.tool_payload("Bash", {"command": command})
    fields = {"proc": cz if cz is not None else FakeCz(), "git": git or _git()}
    return repo.simulate(payload, deps(**fields), harness=harness, state=state)


@pytest.mark.parametrize("harness", [Harness.CLAUDE_CODE, Harness.OPENCODE])
def test_rejected_message_denies_with_sanitized_cz_text_no_commitizen_hint(
    repo: PackRepo, deps: Deps, harness: Harness
) -> None:
    cz = FakeCz()

    report = _bash(repo, deps, 'git commit -m "Add thing."', cz=cz, harness=harness)

    combined = report.trace.combined
    assert combined.decision is Decision.DENY
    assert cz.messages == ["Add thing."]
    assert combined.reason.splitlines() == [
        'cz check rejected the commit message "Add thing."',
        "cz: commit validation: failed!",
        "cz: please enter a commit message in the commitizen format.",
        REWRITE_HINT,
    ]
    assert "tool.commitizen" not in combined.reason and "cutover" not in combined.reason


def test_cz_echo_is_requoted_and_config_pointers_dropped() -> None:
    """cz's unquoted echo cannot pose as an instruction line; config hints never reach the model."""
    from coding_agent_playbook.hook_runtime.handlers.safety._cz import deny_reason

    output = (
        b'commit "c0ffee": "Bad\x1b[2J subject"\n'
        b"configure [tool.commitizen] to change the convention\n"
        b"commit validation: failed!\n"
    )

    assert deny_reason(output, None).splitlines() == [
        'cz check rejected commit c0ffee "Bad [2J subject"',
        "cz: commit validation: failed!",
        REWRITE_HINT,
    ]


def test_accepted_message_is_none_and_cz_runs_in_the_repo_root(
    repo: PackRepo, deps: Deps, cz_program: Path
) -> None:
    cz = FakeCz()

    report = _bash(repo, deps, "git commit -m 'feat: add parser'", cz=cz)

    assert report.trace.combined.decision is Decision.NONE
    assert cz.calls == [(str(cz_program), "check", "--message", "feat: add parser")]
    assert cz.cwds == [str(repo.root)]


def test_heredoc_form_passes_exact_message(repo: PackRepo, deps: Deps) -> None:
    cz = FakeCz()

    assert _bash(repo, deps, HEREDOC_COMMIT, cz=cz).trace.combined.decision is Decision.NONE
    assert cz.messages == ["feat: add parser\n\nWhy it matters."]


def test_dash_F_file_read_within_64k(repo: PackRepo, deps: Deps) -> None:
    repo.write("msg.txt", "fix: read the message file\n")
    repo.write("big.txt", "x" * (64 * 1024 + 1))
    cz = FakeCz()

    _bash(repo, deps, "git commit -F msg.txt", cz=cz)
    big = _bash(repo, deps, "git commit -F big.txt", cz=cz)

    assert cz.messages == ["fix: read the message file\n"]
    assert big.trace.combined.decision is Decision.NONE


def test_proxy_wrapper_unwrapped_accepts(repo: PackRepo, deps: Deps) -> None:
    cz = FakeCz()

    report = _bash(repo, deps, 'proxy git commit -m "feat: y"', cz=cz)

    assert (report.trace.combined.decision, cz.messages) == (Decision.NONE, ["feat: y"])


@pytest.mark.parametrize(
    "command",
    [
        "git commit --amend --no-edit",
        'git commit -m "$X"',
        "git commit -m `cat msg`",
        'git commit -m "$(git log -1 --format=%s)"',
        'echo git commit -m "bad."',
        "git commit",
        "git commit -C HEAD",
        'git commit --allow-empty-message -m ""',
    ],
)
def test_amend_no_edit_dynamic_and_echo_are_none_zero_cz_calls(
    repo: PackRepo, deps: Deps, command: str
) -> None:
    cz = FakeCz()

    report = _bash(repo, deps, command, cz=cz)

    assert (report.trace.combined.decision, cz.calls) == (Decision.NONE, [])


def test_no_cz_pin_none_plus_one_hint_per_session(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    pack_repo.install_pack([HOOK_ID])
    state = tmp_path / "state"

    first = _bash(pack_repo, deps, 'git commit -m "Add thing."', state=state)
    second = _bash(pack_repo, deps, 'git commit -m "Add other."', state=state)

    assert first.trace.combined.decision is Decision.NONE
    assert first.trace.combined.user_notes == (
        "commit-message-convention: cz is not pinned for this worktree, so commit messages "
        "are not checked; ask the user to install commitizen and run playbook sync.",
    )
    assert second.trace.combined.user_notes == ()


def test_changed_cz_binary_is_not_run(repo: PackRepo, deps: Deps, cz_program: Path) -> None:
    cz_program.write_bytes(b"#!/bin/sh\necho swapped\n")
    os.utime(cz_program, ns=(1, 1))
    cz = FakeCz()

    report = _bash(repo, deps, 'git commit -m "Add thing."', cz=cz)

    assert (report.trace.combined.decision, cz.calls) == (Decision.NONE, [])
    assert "changed since sync" in report.trace.combined.user_notes[0]


def _commit(sha: str, when: str, message: str, *parents: str) -> LoggedCommit:
    return LoggedCommit(sha, when, message, parents)


def _pushed(*commits: LoggedCommit, linear: bool = True) -> FakeGit:
    """The tracking ref at ``base0`` and ``commits`` (newest first) on top of it.

    ``linear`` chains each commit to the next one and the oldest to ``base0``, as
    a history without merges logs; otherwise each commit keeps its own parents.
    """
    if linear:
        below = [*(commit.sha for commit in commits[1:]), "base0"]
        commits = tuple(
            replace(commit, parents=(parent,))
            for commit, parent in zip(commits, below, strict=True)
        )
    return _git(
        upstream_ref=TRACKING,
        commits={TRACKING: "base0"},
        logs={f"{TRACKING}..HEAD": commits},
    )


def _checking_push(repo: PackRepo, cutover: str = "") -> None:
    """The push scan is opt-in: the consumer's ``[hooks.commit-message-convention] check_push``."""
    repo.install_pack(
        [HOOK_ID],
        per_hook={HOOK_ID: {"check_push": True}},
        handler_config={HOOK_ID: {"cutover_date": cutover}},
    )


def test_push_not_scanned_by_default(repo: PackRepo, deps: Deps) -> None:
    """The shipped ``check_push = false``: the per-commit check and the commit-msg twin cover it."""
    cz = FakeCz(rejected_ranges=frozenset({f"{TRACKING}..HEAD"}))
    git = _pushed(_commit("c0", NEW, "Bad subject\n"))

    report = _bash(repo, deps, "git push", cz=cz, git=git)

    assert (report.trace.combined.decision, cz.calls) == (Decision.NONE, [])
    assert not [call for call in git.calls if call[0] == "commit_log"]


def test_push_skips_pre_cutover_commits(repo: PackRepo, deps: Deps) -> None:
    _checking_push(repo, "2026-10-15")
    cz = FakeCz()
    git = _pushed(_commit("c0", NEW, "feat: new\n"), _commit("c1", OLD, "Legacy subject\n"))

    report = _bash(repo, deps, "git push", cz=cz, git=git)

    assert report.trace.combined.decision is Decision.NONE
    assert (cz.ranges, cz.messages) == (["c0^..HEAD"], [])


def test_push_tail_through_a_merge_checks_each_commit(repo: PackRepo, deps: Deps) -> None:
    """Regression (PR #32): ``c1^..HEAD`` would also reach main's commits behind the merge."""
    _checking_push(repo, "2026-10-15")
    cz = FakeCz(accepts=lambda message: True)
    git = _pushed(
        _commit("c0", NEW, "feat: after the merge\n", "c1"),
        _commit("c1", NEW, "Merge branch 'main' into feat\n", "c2", "m0"),
        _commit("c2", OLD, "Legacy subject\n", "base0"),
        linear=False,
    )

    report = _bash(repo, deps, "git push", cz=cz, git=git)

    assert report.trace.combined.decision is Decision.NONE
    assert (cz.ranges, cz.messages) == (
        [],
        ["Merge branch 'main' into feat\n", "feat: after the merge\n"],
    )


def test_push_rebased_commit_with_new_committer_date_is_checked(repo: PackRepo, deps: Deps) -> None:
    _checking_push(repo, "2026-10-15")
    cz = FakeCz(rejected_ranges=frozenset({f"{TRACKING}..HEAD"}))
    git = _pushed(_commit("c0", NEW, "Old style subject\n"))

    report = _bash(repo, deps, "git push origin", cz=cz, git=git)

    assert report.trace.combined.decision is Decision.DENY
    assert cz.ranges == [f"{TRACKING}..HEAD"]
    assert report.trace.combined.reason.splitlines()[0] == (
        'cz check rejected the commit message "Add thing."'  # FakeCz's canned echo, re-quoted
    )


def test_push_noncontiguous_kept_set_per_commit_messages(repo: PackRepo, deps: Deps) -> None:
    _checking_push(repo, "2026-10-15")
    cz = FakeCz()
    git = _pushed(
        _commit("c0", OLD, "Legacy\n"),
        _commit("c1", NEW, "feat: one\n"),
        _commit("c2", OLD, "Legacy two\n"),
        _commit("c3", NEW, "Bad subject\n"),
    )

    report = _bash(repo, deps, "git push", cz=cz, git=git)

    assert cz.messages == ["Bad subject\n"]  # oldest first; the first rejection stops the scan
    assert report.trace.combined.decision is Decision.DENY
    assert report.trace.combined.reason.splitlines()[0] == (
        'cz check rejected commit c3 "Bad subject"'
    )


def test_push_explicit_refspec_names_the_tracking_ref(repo: PackRepo, deps: Deps) -> None:
    _checking_push(repo)
    cz = FakeCz()
    tracking = "refs/remotes/upstream/main"
    git = _git(commits={tracking: "base0"}, logs={f"{tracking}..HEAD": ()})

    _bash(repo, deps, "git push upstream HEAD:main", cz=cz, git=git)

    assert ("commit_log", (f"{tracking}..HEAD",)) in git.calls


def test_missing_tracking_ref_fails_open(repo: PackRepo, deps: Deps) -> None:
    _checking_push(repo)
    cz = FakeCz()

    report = _bash(repo, deps, "git push", cz=cz, git=_git(upstream_ref=TRACKING))

    assert (report.trace.combined.decision, cz.calls) == (Decision.NONE, [])


def test_cutover_date_rendered_from_the_commit_convention_table(pack_repo: PackRepo) -> None:
    """One source for the push scan and the CI step: ``[hooks.commit_convention]`` (D-Q3)."""
    from coding_agent_playbook.config.tables.hooks import (
        CommitConventionConfig,
        GuardrailsConfig,
        HooksConfig,
    )
    from coding_agent_playbook.guard_config import GuardConfigInputs, render_guard_config
    from tests.hook_runtime.handlers.pack_repo import resolve_engine_hooks

    hooks = resolve_engine_hooks([HOOK_ID], pack_repo.root)
    convention = CommitConventionConfig(cutover_date="2026-10-15")
    config = HooksConfig(enabled=True, commit_convention=convention)
    inputs = GuardConfigInputs(hooks, config, GuardrailsConfig(), "0.1.0a0")

    rendered = render_guard_config(inputs)["hooks"][HOOK_ID]["handlers"]["pre_tool_use"]

    assert rendered["config"] == {"check_push": False, "cutover_date": "2026-10-15"}


def test_check_push_false_never_scans(pack_repo: PackRepo, deps: Deps, cz_program: Path) -> None:
    pack_repo.install_pack([HOOK_ID], per_hook={HOOK_ID: {"check_push": False}})
    _pin(pack_repo, cz_program)
    git = _pushed(_commit("c0", NEW, "Bad\n"))

    report = _bash(pack_repo, deps, "git push", git=git)

    assert report.trace.combined.decision is Decision.NONE
    assert not [call for call in git.calls if call[0] == "commit_log"]


def test_cz_timeout_fails_open_with_a_note(repo: PackRepo, deps: Deps) -> None:
    report = _bash(repo, deps, 'git commit -m "Add thing."', cz=FakeCz(timeout=True))

    assert report.trace.combined.decision is Decision.NONE
    assert "cz did not answer" in report.trace.combined.user_notes[0]


@pytest.mark.skipif(
    os.environ.get("PLAYBOOK_LATENCY_TESTS") != "1", reason="set PLAYBOOK_LATENCY_TESTS=1"
)
def test_cz_startup_latency() -> None:
    """The commitizen start-up cost on a ``git commit`` segment (Track K10 Done-when, §F.4.2)."""
    import shutil
    import subprocess
    import time

    cz = shutil.which("cz")
    if cz is None:
        pytest.skip("cz not on PATH")
    runs: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        subprocess.run(
            [cz, "check", "--message", "feat: x"], capture_output=True, timeout=30, check=False
        )
        runs.append(time.perf_counter() - started)
    print(f"cz check start-up: median {sorted(runs)[2]:.3f}s over {len(runs)} runs")
    assert sorted(runs)[2] < 3.0  # inside the hook's 3 s cz timeout
