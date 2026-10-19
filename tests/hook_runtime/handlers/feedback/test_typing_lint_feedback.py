"""typing-lint-feedback: bucket 3 of the shared D1 call (specs/prK-hook-pack.md §E.3).

Linked to ``python-typing`` (``applies_if: python_version >= 3.11``): its
``when`` block adds the PEP 695 codes only for ``>= 3.12``, resolved at sync
from the same fact the rule body branches on. Extra filters: public defs only
for ``ANN001``/``ANN201`` (one ``ast.parse``), no ``tests/``, every ``ANN*``
left to a Stop typecheck stage, ``UP007``/``UP045`` left to M1's safe fixes.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.guard_config import DetectInputs
from coding_agent_playbook.hook_runtime.decision import Decision
from tests.hook_runtime.fakes import FakeRuff, ruff_row
from tests.hook_runtime.handlers.pack_repo import engine_hook, engine_rules
from tests.hook_runtime.handlers.ruff_kit import context, edit, head_git, pin_ruff, value_of

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_runtime.handlers.pack_repo import PackRepo

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "typing-lint-feedback"
APP: Final = "src/app.py"
PREFIX: Final = "rule python-typing (skill python-coding): "
#: A new file: a public def, a private helper, a mutable default.
NEW_FILE: Final = (
    "def first(items):\n"  # 1
    "    return items[0]\n"  # 2
    "def _helper(y):\n"  # 3
    "    return y\n"  # 4
    "def push(items=[]):\n"  # 5
    "    return items\n"  # 6
)
PUBLIC: Final = [
    ruff_row("ANN001", 1, "Missing type annotation for function argument `items`"),
    ruff_row("ANN201", 1, "Missing return type annotation for public function `first`"),
]
PRIVATE: Final = [ruff_row("ANN001", 3, "Missing type annotation for function argument `y`")]
MUTABLE: Final = ruff_row("B006", 5, "Do not use mutable data structures for argument defaults")


def _install(
    repo: PackRepo,
    program: Path,
    *,
    python_version: str = "3.11",
    select: str = '["F"]',
    extra_tables: Mapping[str, Any] | None = None,
) -> None:
    repo.write("pyproject.toml", f"[tool.ruff.lint]\nselect = {select}\n")
    repo.write(APP, NEW_FILE)
    repo.install_pack(
        [HOOK_ID],
        rules=engine_rules(),
        detect=DetectInputs(facts={"python_version": python_version}),
        extra_tables=extra_tables,
    )
    pin_ruff(repo, program)


def _edit_new(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff: FakeRuff, rel: str = APP
) -> SimulateReport:
    """An Edit of ``rel``, a file with no HEAD blob: every line is changed."""
    return edit(repo, deps(proc=ruff, git=head_git(None, rel)), rel)


@pytest.mark.parametrize(("python_version", "pep695"), [("3.11", False), ("3.12", True)])
def test_py311_no_up046_py312_reports(
    pack_repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    ruff_program: Path,
    python_version: str,
    pep695: bool,
) -> None:
    _install(pack_repo, ruff_program, python_version=python_version)
    generic = ruff_row(
        "UP046", 1, "Generic class `Box` uses `Generic` subclass instead of type parameters"
    )
    ruff = FakeRuff(diagnostics=[generic])

    report = _edit_new(pack_repo, deps, ruff)

    extended = value_of(ruff.argvs("d1")[0], "--extend-select").split(",")
    assert ("UP046" in extended) is pep695
    expected = [f'{PREFIX}"src/app.py:1 UP046 {generic["message"]}"'] if pep695 else []
    assert context(report) == expected


def test_public_def_ann001_ann201_private_silent(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    _install(pack_repo, ruff_program)

    report = _edit_new(pack_repo, deps, FakeRuff(diagnostics=[*PUBLIC, *PRIVATE, MUTABLE]))

    assert context(report) == [
        f'{PREFIX}"src/app.py:1 ANN001 Missing type annotation for function argument `items`"',
        f'{PREFIX}"src/app.py:1 ANN201 Missing return type annotation for public function `first`"',
        f'{PREFIX}"src/app.py:5 B006 Do not use mutable data structures for argument defaults"',
    ]


def test_mypy_stop_tier_suppresses_ann(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    """A Stop ``typecheck`` stage covers annotations; non-ANN codes still report."""
    stop_gate = {"stages": [{"name": "typecheck", "owner": "x", "tool": "mypy"}]}
    _install(pack_repo, ruff_program, extra_tables={"stop_gate": stop_gate})

    report = _edit_new(pack_repo, deps, FakeRuff(diagnostics=[*PUBLIC, MUTABLE]))

    assert context(report) == [
        f'{PREFIX}"src/app.py:5 B006 Do not use mutable data structures for argument defaults"'
    ]


def test_pgh003_is_context_not_deny(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    _install(pack_repo, ruff_program)
    blanket = ruff_row("PGH003", 2, "Use specific rule codes when ignoring type issues")

    report = _edit_new(pack_repo, deps, FakeRuff(diagnostics=[blanket]))

    assert report.trace.combined.decision is Decision.CONTEXT
    assert report.trace.combined.reason == ""


def test_ann401_line_carries_the_any_note(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    _install(pack_repo, ruff_program)
    any_arg = ruff_row("ANN401", 1, "Dynamically typed expressions (typing.Any) are disallowed")

    report = _edit_new(pack_repo, deps, FakeRuff(diagnostics=[any_arg]))

    assert context(report) == [
        f'{PREFIX}"src/app.py:1 ANN401 Dynamically typed expressions (typing.Any) are disallowed; '
        'Any is a last resort: narrow it, or justify a `# type: ignore[code]`"'
    ]


@pytest.mark.parametrize(("select", "reported"), [('["F", "UP"]', False), ('["F"]', True)])
def test_up045_suppressed_when_up_in_safe_fix_select(
    pack_repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    ruff_program: Path,
    select: str,
    reported: bool,
) -> None:
    """M1 fixes UP045 when the project's UP is a safe fix; only otherwise is it a nudge."""
    _install(pack_repo, ruff_program, select=select)
    optional = ruff_row("UP045", 1, "Use `X | None` for type annotations")

    report = _edit_new(pack_repo, deps, FakeRuff(diagnostics=[optional]))

    assert context(report) == (
        [f'{PREFIX}"src/app.py:1 UP045 Use `X | None` for type annotations"'] if reported else []
    )


def test_tests_files_are_out_of_scope(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    _install(pack_repo, ruff_program)
    rel = "tests/test_app.py"
    pack_repo.write(rel, NEW_FILE)

    report = _edit_new(pack_repo, deps, FakeRuff(diagnostics=[*PUBLIC, MUTABLE]), rel)

    assert report.trace.combined.decision is Decision.NONE


def test_hook_md_matches_its_pack_row_and_handler(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """§E.0.6 row: default, post_tool_use, warn -> context, open; linked to python-typing."""
    fm = engine_hook(HOOK_ID).frontmatter

    rc = _validate.run(argparse.Namespace(repo_root=str(tmp_path)))

    assert (fm.tier, fm.events, fm.decisions, fm.on_error) == (
        "default",
        ["post_tool_use"],
        ["context", "none"],
        "open",
    )
    assert fm.linked_rule == "python-typing"
    assert fm.handler is not None and fm.handler.builtin == "ruff_lint_feedback"
    assert rc == 0
    assert HOOK_ID not in capsys.readouterr().err
