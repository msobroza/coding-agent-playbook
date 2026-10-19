"""``playbook sync`` refuses to write while ``playbook validate`` fails (prK §P P8b).

Write mode and ``--check`` run the full validate rule set
(``sync_gate_errors``) after the environment preflight and before any
render: a finding prints its ``FAIL`` lines and the abort line on stderr, exits
1 and writes nothing. ``--check-staged`` — the ``commit = false`` pre-commit
hot path — is not gated.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands._validation import ValidationError
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.orchestrator import SyncContext

    SyntheticRepoFactory = Callable[..., Path]

_ABORT_LINE = "playbook sync aborted; no files were written."

_UNKNOWN_FACT_RULE = (
    "---\nid: bad-fact\nname: Bad\ndescription: d\nscope: scoped\n"
    "skill: python-coding\napplies_if:\n  orm_version: '>=2'\n---\nBody\n"
)

_CONFIG_WITH_MISSING_OVERLAY = """\
schema_version = 1
adapters_enabled = ["claude_code"]
overlays_enabled = ["no_such_overlay_pkg_p8"]

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"
"""


def _write_bad_rule(repo: Path) -> Path:
    """A repo-local rule whose ``applies_if`` names an unknown fact."""
    target = repo / "playbook" / "rules" / "bad-fact.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_UNKNOWN_FACT_RULE, encoding="utf-8")
    return target


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` (repo-relative posix path -> bytes)."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class _SpyValidate:
    """Records each context it validates and returns ``errors``."""

    def __init__(self, errors: list[ValidationError] | None = None) -> None:
        self.errors = errors or []
        self.calls: list[SyncContext] = []

    def __call__(self, ctx: SyncContext) -> list[ValidationError]:
        self.calls.append(ctx)
        return self.errors


def test_sync_aborts_on_validate_error_and_writes_nothing(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("good", "Good body.\n")])
    bad = _write_bad_rule(repo)
    before = _tree_snapshot(repo)

    rc = _sync.run(argparse.Namespace(repo_root=str(repo), check=False))

    assert rc == 1
    assert _tree_snapshot(repo) == before
    assert not (repo / "AGENTS.md").exists()
    assert not (repo / ".coding-agent-playbook.lock").exists()
    assert not (repo / ".gitignore").exists()
    err = capsys.readouterr().err
    assert f"FAIL {bad}: applies_if: unknown predicate key: 'orm_version'" in err


def test_sync_check_aborts_on_validate_error(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("good", "Good body.\n")])
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    bad = _write_bad_rule(repo)
    capsys.readouterr()

    rc = _sync.execute(repo, check=True, git=FakeGitClient())

    assert rc == 1
    captured = capsys.readouterr()
    assert f"FAIL {bad}:" in captured.err
    assert _ABORT_LINE in captured.err
    assert "drift" not in captured.out.lower()  # the gate fires before any render


def test_sync_check_staged_is_not_validate_gated(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """The pre-commit hot path stays as fast as before: no validate run at all."""
    repo = make_synthetic_repo(tmp_path)
    _write_bad_rule(repo)
    spy = _SpyValidate([ValidationError("x.md", "boom")])

    rc = _sync.execute(repo, check_staged=True, git=FakeGitClient(staged=[]), validate=spy)

    assert rc == 0
    assert spy.calls == []


_RULE_CALLING_PROMPT = (
    "---\nid: inliner\nname: Inliner\ndescription: d\nslash: inliner\n"
    'includes_rules:\n  - python-typing\n---\nReview.\n{{ rule("python-typing") }}\n'
)


def test_sync_check_staged_names_a_prompt_that_still_calls_rule(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression (D15, prS §7.5): the ungated pre-commit path refuses a ``rule()`` call
    with the migration message, never a jinja2 ``UndefinedError`` traceback."""
    repo = make_synthetic_repo(tmp_path)
    prompt = repo / "playbook" / "prompts" / "inliner.md.j2"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text(_RULE_CALLING_PROMPT, encoding="utf-8")
    spy = _SpyValidate([ValidationError("x.md", "boom")])

    rc = _sync.execute(repo, check_staged=True, git=FakeGitClient(staged=["app.py"]), validate=spy)

    assert rc == 1
    assert spy.calls == []  # still not the full validate gate
    assert capsys.readouterr().err.splitlines() == [
        f'FAIL {prompt}: body calls {{{{ rule("python-typing") }}}}; prompts no longer inline '
        "rules. Remove the call and keep 'python-typing' in includes_rules: Claude Code and "
        "OpenCode commands then point at its skill, Continue appends its text",
        "validation failed with 1 error(s)",
        _ABORT_LINE,
    ]


def test_sync_check_staged_skips_the_rule_call_check_with_nothing_staged(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """The nothing-staged fast path still exits 0 before reading any prompt."""
    repo = make_synthetic_repo(tmp_path)
    prompt = repo / "playbook" / "prompts" / "inliner.md.j2"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text(_RULE_CALLING_PROMPT, encoding="utf-8")

    assert _sync.execute(repo, check_staged=True, git=FakeGitClient(staged=[])) == 0


def test_sync_validate_errors_go_to_stderr_with_abort_line(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    spy = _SpyValidate([ValidationError("x.md", "boom"), ValidationError("y.md", "bang")])

    rc = _sync.execute(repo, git=FakeGitClient(), validate=spy)

    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "FAIL x.md: boom",
        "FAIL y.md: bang",
        "validation failed with 2 error(s)",
        _ABORT_LINE,
    ]
    assert [ctx.repo_root for ctx in spy.calls] == [repo]


def test_sync_validates_after_the_environment_preflight(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unusable overlay is refused by the preflight first, with its own message."""
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_MISSING_OVERLAY)
    spy = _SpyValidate()

    rc = _sync.execute(repo, git=FakeGitClient(), validate=spy)

    assert rc == 1
    assert spy.calls == []
    assert "no_such_overlay_pkg_p8" in capsys.readouterr().err


@pytest.mark.parametrize("check", [False, True])
def test_sync_runs_validate_once_and_proceeds_when_clean(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, check: bool
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("good", "Good body.\n")])
    if check:
        assert _sync.execute(repo, git=FakeGitClient()) == 0
    spy = _SpyValidate()

    rc = _sync.execute(repo, check=check, git=FakeGitClient(), validate=spy)

    assert rc == 0
    assert len(spy.calls) == 1
    assert (repo / "AGENTS.md").is_file()


_MEMBER_OF_MISSING_SKILL_RULE = (
    "---\nid: python-typing\nname: Typing\ndescription: d\nscope: scoped\n"
    "skill: python-codng\n---\nBody\n"
)


def test_sync_writes_nothing_on_a_membership_error(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """A member rule naming no merged skill (V5) stops the sync before any write."""
    repo = make_synthetic_repo(tmp_path, rules=[("good", "Good body.\n")])
    bad = repo / "playbook" / "rules" / "python-typing.md"
    bad.write_text(_MEMBER_OF_MISSING_SKILL_RULE, encoding="utf-8")
    before = _tree_snapshot(repo)

    rc = _sync.execute(repo, git=FakeGitClient())

    assert rc == 1
    assert _tree_snapshot(repo) == before
    err = capsys.readouterr().err
    assert (
        f"FAIL {bad}: skill 'python-codng' does not exist after merging every layer; expected "
        "one of: ml-data, python-coding, python-testing, python-tooling (or enable the overlay "
        "that ships it)"
    ) in err
    assert _ABORT_LINE in err


_SCOPED_WITHOUT_SKILL_RULE = (
    "---\nid: risk-naming\nname: Risk naming\ndescription: d\nscope: scoped\n---\nBody\n"
)


@pytest.mark.parametrize("check", [False, True])
def test_sync_writes_nothing_for_a_scoped_rule_without_skill(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    check: bool,
) -> None:
    """V1 (prS §6.10 item 10): write mode and ``--check`` stop before any write."""
    repo = make_synthetic_repo(tmp_path, rules=[("good", "Good body.\n")])
    bad = repo / "playbook" / "rules" / "risk-naming.md"
    bad.write_text(_SCOPED_WITHOUT_SKILL_RULE, encoding="utf-8")
    before = _tree_snapshot(repo)

    rc = _sync.execute(repo, check=check, git=FakeGitClient())

    assert rc == 1
    assert _tree_snapshot(repo) == before
    err = capsys.readouterr().err
    assert (
        f"FAIL {bad}: scope 'scoped' needs 'skill: <skill-id>' naming the skill whose "
        "references deliver this rule; known skills: ml-data, python-coding, python-testing, "
        "python-tooling"
    ) in err.splitlines()
    assert _ABORT_LINE in err
