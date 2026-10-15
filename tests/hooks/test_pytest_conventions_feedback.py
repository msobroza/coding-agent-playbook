"""pytest-conventions-feedback: bucket 4 of the shared D1 call (specs/prK-hook-pack.md §E.3).

Linked to the ``pytest`` rule (``applies_if: has_framework: [pytest]``, globs
``tests/**/*.py``): the PT codes only on test files, and the opt-in AST
heuristics (``ast_heuristics``, off by default) for what no ruff code covers.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.guard_config import DetectInputs
from coding_agent_playbook.hook_runtime.decision import Decision
from tests.hook_runtime.fakes import FakeRuff, ruff_row
from tests.hooks.pack_repo import engine_hook, engine_rules
from tests.hooks.ruff_kit import context, edit, head_git, pin_ruff

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    import pytest

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hooks.pack_repo import PackRepo

HOOK_ID: Final = "pytest-conventions-feedback"
TEST: Final = "tests/test_app.py"
PREFIX: Final = "rule pytest: "
PYTEST: Final[Mapping[str, Any]] = {"frameworks": {"pytest": ">=8"}}
LOOPS: Final = (
    "def test_values():\n"  # 1
    "    for v in [1, 2]:\n"  # 2
    "        assert v\n"  # 3
    "def test_more():\n"  # 4
    "    for v in [3]:\n"  # 5
    "        assert v\n"  # 6
)


def _install(
    repo: PackRepo,
    program: Path,
    *,
    facts: Mapping[str, Any] = PYTEST,
    heuristics: bool = False,
    pyproject: str = '[tool.ruff.lint]\nselect = ["F"]\n',
) -> bytes:
    repo.write("pyproject.toml", pyproject)
    per_hook = {HOOK_ID: {"ast_heuristics": True}} if heuristics else None
    data = repo.install_pack(
        [HOOK_ID], rules=engine_rules(), detect=DetectInputs(facts=dict(facts)), per_hook=per_hook
    )
    pin_ruff(repo, program)
    return data


def _edit_new(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    ruff: FakeRuff,
    rel: str = TEST,
    *,
    state: Path | None = None,
) -> SimulateReport:
    return edit(repo, deps(proc=ruff, git=head_git(None, rel)), rel, state=state)


def test_assert_equal_reports_pt009(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    _install(pack_repo, ruff_program)
    pack_repo.write(TEST, "def test_x(case):\n    case.assertEqual(1, 1)\n")
    unittest_assert = ruff_row(
        "PT009", 2, "Use a regular `assert` instead of unittest-style `assertEqual`"
    )

    report = _edit_new(pack_repo, deps, FakeRuff(diagnostics=[unittest_assert]))

    assert context(report) == [f'{PREFIX}"tests/test_app.py:2 PT009 {unittest_assert["message"]}"']


def test_loop_assert_heuristic_off_silent_on_one_line(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path, tmp_path: Path
) -> None:
    """Off by default; on, one line per file per session, whichever loop it lands on."""
    _install(pack_repo, ruff_program)
    pack_repo.write(TEST, LOOPS)
    off = _edit_new(pack_repo, deps, FakeRuff())
    _install(pack_repo, ruff_program, heuristics=True)
    state = tmp_path / "state"

    on = _edit_new(pack_repo, deps, FakeRuff(), state=state)
    again = _edit_new(pack_repo, deps, FakeRuff(), state=state)

    assert off.trace.combined.decision is Decision.NONE
    assert context(on) == [
        f'{PREFIX}"tests/test_app.py:3 pytest-loop-assert `assert` in a loop: use '
        '`@pytest.mark.parametrize` so each case reports"'
    ]
    assert again.trace.combined.decision is Decision.NONE


def test_unittest_class_and_unmarked_async_test_when_on(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    """(a) a TestCase in a file created this session; (c) pytest-asyncio without auto mode."""
    facts = {"frameworks": {"pytest": ">=8", "pytest-asyncio": ">=0.23"}}
    _install(pack_repo, ruff_program, facts=facts, heuristics=True)
    pack_repo.write(
        TEST,
        "import unittest\n"  # 1
        "class TestOld(unittest.TestCase):\n"  # 2
        "    pass\n"  # 3
        "async def test_fetch():\n"  # 4
        "    pass\n",  # 5
    )

    report = _edit_new(pack_repo, deps, FakeRuff())

    assert [line.split()[3] for line in context(report)] == [
        "pytest-unittest-class",
        "pytest-asyncio-mark",
    ]


def test_asyncio_auto_mode_needs_no_mark(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    facts = {"frameworks": {"pytest": ">=8", "pytest-asyncio": ">=0.23"}}
    auto = '[tool.ruff.lint]\nselect = ["F"]\n[tool.pytest.ini_options]\nasyncio_mode = "auto"\n'
    _install(pack_repo, ruff_program, facts=facts, heuristics=True, pyproject=auto)
    pack_repo.write(TEST, "async def test_fetch():\n    pass\n")

    report = _edit_new(pack_repo, deps, FakeRuff())

    assert report.trace.combined.decision is Decision.NONE


def test_non_pytest_repo_not_rendered(pack_repo: PackRepo, ruff_program: Path) -> None:
    """The linked rule does not apply without pytest, so the hook has no record."""
    data = _install(pack_repo, ruff_program, facts={})

    assert HOOK_ID not in json.loads(data)["hooks"]


def test_src_edit_no_pt_bucket(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    """The rule's globs are tests/**: a src/ edit does not even select the hook."""
    _install(pack_repo, ruff_program)
    pack_repo.write("src/app.py", "x = 1\n")
    ruff = FakeRuff(diagnostics=[ruff_row("PT009", 1, "unittest-style assert")])

    report = _edit_new(pack_repo, deps, ruff, "src/app.py")

    assert ruff.calls == []
    assert report.trace.combined.decision is Decision.NONE


def test_hook_md_matches_its_pack_row_and_handler(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """§E.0.6 row: default, post_tool_use, warn -> context, open; heuristics opt-in."""
    fm = engine_hook(HOOK_ID).frontmatter

    rc = _validate.run(argparse.Namespace(repo_root=str(tmp_path)))

    assert (fm.tier, fm.events, fm.decisions, fm.on_error) == (
        "default",
        ["post_tool_use"],
        ["context", "none"],
        "open",
    )
    assert fm.linked_rule == "pytest"
    assert fm.handler is not None and fm.handler.builtin == "ruff_lint_feedback"
    assert fm.handler.config == {"ast_heuristics": False}
    assert rc == 0
    assert HOOK_ID not in capsys.readouterr().err
