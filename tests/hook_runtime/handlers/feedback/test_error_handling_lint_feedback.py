"""error-handling-lint-feedback: bucket 2 of the shared D1 call (specs/prK-hook-pack.md §E.3).

The hook is linked to ``python-error-handling``, whose ``lint_codes`` sync
resolves into its config; every case runs the shipped ``HOOK.md`` and the
shipped rule through ``playbook-hook simulate post_tool_use`` (see
``ruff_kit``). No test spawns ruff or git.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.hook_runtime.decision import Decision
from tests.hook_runtime.fakes import FakeRuff, ruff_row
from tests.hook_runtime.handlers.pack_repo import engine_hook, engine_rules, resolve_engine_hooks
from tests.hook_runtime.handlers.ruff_kit import (
    context,
    edit,
    head_git,
    pin_ruff,
    probed_drops,
    value_of,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from tests.hook_runtime.handlers.pack_repo import PackRepo

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "error-handling-lint-feedback"
POST_EDIT: Final = "post-edit-ruff-format"
APP: Final = "src/app.py"
CODES: Final = ("B904", "BLE001", "E722", "S101", "S110", "S112", "TRY400", "TRY401")
HEAD: Final = "def run():\n    return 1\n"
#: The agent's edit: lines 3-6 are new.
EDITED: Final = HEAD + "try:\n    run()\nexcept:\n    pass\n"
BARE: Final = ruff_row("E722", 5, "Do not use bare `except`")
PASS: Final = ruff_row("S110", 5, "`try`-`except`-`pass` detected, consider logging the exception")
PREFIX: Final = "rule python-error-handling (skill python-coding): "


def _install(repo: PackRepo, program: Path, *hook_ids: str, select: str = '["F"]') -> None:
    repo.write("pyproject.toml", f"[tool.ruff.lint]\nselect = {select}\n")
    repo.write(APP, EDITED)
    repo.install_pack(list(hook_ids or (HOOK_ID,)), rules=engine_rules())
    pin_ruff(repo, program)


@pytest.fixture
def repo(pack_repo: PackRepo, ruff_program: Path) -> PackRepo:
    """error-handling-lint-feedback alone, the project selecting only F, ruff pinned."""
    _install(pack_repo, ruff_program)
    return pack_repo


def test_bare_except_pass_on_new_line_context(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    ruff = FakeRuff(diagnostics=[BARE, PASS])

    report = edit(repo, deps(proc=ruff, git=head_git(HEAD, APP)), APP)

    assert ruff.kinds() == ["d1"]  # a lint hook never rewrites the file
    assert value_of(ruff.argvs("d1")[0], "--extend-select") == ",".join(CODES)
    assert report.trace.combined.decision is Decision.CONTEXT
    assert context(report) == [
        f'{PREFIX}"src/app.py:5 E722 Do not use bare `except`"',
        f'{PREFIX}"src/app.py:5 S110 `try`-`except`-`pass` detected, consider logging the '
        'exception"',
    ]


def test_legacy_line_silent(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    legacy = ruff_row("BLE001", 2, "Do not catch blind exception: `Exception`")

    report = edit(repo, deps(proc=FakeRuff(diagnostics=[legacy]), git=head_git(HEAD, APP)), APP)

    assert report.trace.combined.decision is Decision.NONE


def test_same_diagnostic_once(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    state = tmp_path / "state"

    first = edit(
        repo, deps(proc=FakeRuff(diagnostics=[BARE]), git=head_git(HEAD, APP)), APP, state=state
    )
    second = edit(
        repo, deps(proc=FakeRuff(diagnostics=[BARE]), git=head_git(HEAD, APP)), APP, state=state
    )

    assert len(context(first)) == 1
    assert second.trace.combined.decision is Decision.NONE


def test_code_unknown_to_ruff_absent_from_d1_argv(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    """The sync probe (``rule --all``) drops a code this ruff lacks; D1 never names it."""
    _install(pack_repo, ruff_program)
    known: list[dict[str, object]] = [
        {"code": code, "status": {"Stable": {}}} for code in CODES if code != "TRY400"
    ]
    hooks = resolve_engine_hooks([HOOK_ID], pack_repo.root, rules=engine_rules())
    pin_ruff(pack_repo, ruff_program, drops=probed_drops(ruff_program, hooks, known))
    ruff = FakeRuff()

    edit(pack_repo, deps(proc=ruff, git=head_git(HEAD, APP)), APP)

    extended = value_of(ruff.argvs("d1")[0], "--extend-select").split(",")
    assert "TRY400" not in extended
    assert extended == [code for code in CODES if code != "TRY400"]


def test_s101_in_tests_silent(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    """``assert`` is the pytest idiom under tests/; in src/ it is a runtime check."""
    test_rel = "tests/test_x.py"
    repo.write(test_rel, "def test_x():\n    assert run()\n")
    check = ruff_row("S101", 2, "Use of `assert` detected")

    in_tests = edit(
        repo, deps(proc=FakeRuff(diagnostics=[check]), git=head_git(None, test_rel)), test_rel
    )
    in_src = edit(repo, deps(proc=FakeRuff(diagnostics=[check]), git=head_git(None, APP)), APP)

    assert in_tests.trace.combined.decision is Decision.NONE
    assert context(in_src) == [f'{PREFIX}"src/app.py:2 S101 Use of `assert` detected"']


def test_project_selected_code_lands_in_bucket_1_with_rule_suffix(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    """E is in the project's select: CI fails on E722, and the rule says why."""
    _install(pack_repo, ruff_program, POST_EDIT, HOOK_ID, select='["E", "F"]')
    ruff = FakeRuff(format_clean=False, diagnostics=[BARE, PASS])

    report = edit(pack_repo, deps(proc=ruff, git=head_git(HEAD, APP)), APP)

    assert ruff.kinds().count("d1") == 1
    assert context(report) == [
        'ruff (CI fails on this): "src/app.py:5 E722 Do not use bare `except`" '
        "(rule python-error-handling, skill python-coding)",
        f'{PREFIX}"src/app.py:5 S110 `try`-`except`-`pass` detected, consider logging the '
        'exception"',
    ]


def test_hook_md_matches_its_pack_row_and_handler(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """§E.0.6 row: default, post_tool_use, warn -> context, open; linked to the rule."""
    fm = engine_hook(HOOK_ID).frontmatter

    rc = _validate.run(argparse.Namespace(repo_root=str(tmp_path)))

    assert (fm.tier, fm.events, fm.decisions, fm.on_error) == (
        "default",
        ["post_tool_use"],
        ["context", "none"],
        "open",
    )
    assert fm.linked_rule == "python-error-handling"
    assert fm.handler is not None and fm.handler.builtin == "ruff_lint_feedback"
    assert fm.priority > engine_hook(POST_EDIT).frontmatter.priority  # D1 after M1/M2
    assert rc == 0
    assert HOOK_ID not in capsys.readouterr().err
