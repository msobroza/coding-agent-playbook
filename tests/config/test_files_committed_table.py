"""The policy readers' decode-only reads of the committed config (specs/prT-package-layout.md B.5).

``CommittedDocument`` decodes the committed file from the worktree or from a git
blob at a revision (the guard twins read policy as committed at the base, so a
change cannot loosen its own check); ``ConfigFiles.committed_table`` walks one
table of it. Neither runs the whole-file checks, so a broken ``[output]`` never
stops a ``[metrics]`` read. Last, the two filenames have one spelling.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config.files import (
    CONFIG_FILENAME,
    CONFIG_LOCAL_FILENAME,
    CommittedDocument,
    ConfigFiles,
)
from coding_agent_playbook.config.schema import ConfigError
from tests.config._engine_trees import engine_module_file, engine_module_trees

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_COMMITTED = ".coding-agent-playbook.toml"
_LOCAL = ".coding-agent-playbook.local.toml"

#: The one module that spells the two names (as ``CONFIG_FILENAME``/``CONFIG_LOCAL_FILENAME``).
#: Both pins name their modules dotted, so ``module_moves apply`` follows a move.
_HOME = engine_module_file("coding_agent_playbook.config.files")
#: Engine modules that still spell a name, until the PR named beside each takes it
#: away; the pin compares exact sets, so a fixed module must leave the list.
_ALLOWED = frozenset(
    {
        # GC-3 (spec B.13): the writer side, from the runtime's schema module
        engine_module_file("coding_agent_playbook.guard_config"),
    }
)
#: The hook runtime keeps its own spellings: it must not import the sync-side config/
#: package (spec B.5.4); GC-1 gives them a home in its stdlib-only schema module.
_RUNTIME = "hook_runtime"


def test_committed_table_is_empty_without_the_file(tmp_path: Path) -> None:
    """No committed file: the team policy defaults, even with a local file present."""
    (tmp_path / _LOCAL).write_text("[metrics]\nmode = 'absolute'\n", encoding="utf-8")

    assert ConfigFiles(tmp_path).committed_table("metrics") == {}


def test_committed_table_walks_nested_tables(tmp_path: Path) -> None:
    (tmp_path / _COMMITTED).write_text(
        '[hooks.commit_convention]\ncutover_date = "2026-10-15"\n', encoding="utf-8"
    )
    (tmp_path / _LOCAL).write_text('[hooks.commit_convention]\ncutover_date = "x"\n', "utf-8")
    files = ConfigFiles(tmp_path)

    assert files.committed_table("hooks", "commit_convention") == {"cutover_date": "2026-10-15"}
    assert files.committed_table("hooks", "absent") == {}
    assert files.committed_table("metrics", "ruff_violations") == {}


@pytest.mark.parametrize(
    ("document", "path", "message"),
    [
        ('hooks = "on"\n', ("hooks", "x"), "[hooks] must be a table, got 'on'"),
        ("[hooks]\nx = 1\n", ("hooks", "x"), "[hooks.x] must be a table, got 1"),
        ('metrics = ["a"]\n', ("metrics",), "[metrics] must be a table, got ['a']"),
    ],
)
def test_committed_table_refuses_a_non_table_naming_the_file_and_the_path(
    tmp_path: Path, document: str, path: tuple[str, ...], message: str
) -> None:
    (tmp_path / _COMMITTED).write_text(document, encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        ConfigFiles(tmp_path).committed_table(*path)

    assert str(excinfo.value) == f"{_COMMITTED}: {message}"


def test_committed_table_does_not_run_the_whole_file_checks(tmp_path: Path) -> None:
    """A malformed ``[output]`` and a missing ``[project]`` stop no ``[metrics]`` read."""
    (tmp_path / _COMMITTED).write_text(
        '[output]\ncommit = "yes"\n\n[metrics]\nmode = "absolute"\n', encoding="utf-8"
    )
    files = ConfigFiles(tmp_path)

    assert files.committed_table("metrics") == {"mode": "absolute"}
    with pytest.raises(ConfigError, match=r"\[output\] commit must be a boolean"):
        files.committed()


def test_committed_document_decodes_a_git_blob_naming_the_revision() -> None:
    document = CommittedDocument.decode(b"[hooks.x]\nk = 1\n", where="c.toml at abc123")

    assert document.table("hooks", "x") == {"k": 1}
    with pytest.raises(ConfigError, match=r"^c\.toml at abc123: invalid TOML: "):
        CommittedDocument.decode(b"hooks = [\n", where="c.toml at abc123")
    with pytest.raises(ConfigError, match=r"^c\.toml at abc123: not UTF-8 text \("):
        CommittedDocument.decode(b"\xff", where="c.toml at abc123")


def test_committed_document_of_a_missing_blob_is_empty() -> None:
    """``git show`` returns ``None`` when the base revision has no committed config."""
    document = CommittedDocument.decode(None, where="c.toml at abc123")

    assert document.data == {}
    assert document.table("hooks", "gate-weakening-guard") == {}


def _docstrings(tree: ast.Module) -> set[int]:
    """``id()`` of every module, class and function docstring node of ``tree``."""
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, owners)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }


def _code_strings(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """``(line, text)`` of every string constant of ``tree`` but its docstrings.

    Docstrings are prose, so they may name the files; f-string parts count.
    """
    docstrings = _docstrings(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or id(node) in docstrings:
            continue
        if isinstance(node.value, str):
            yield node.lineno, node.value


def _spells_a_name(text: str) -> bool:
    return CONFIG_FILENAME in text or CONFIG_LOCAL_FILENAME in text


def _modules_spelling_a_name() -> set[str]:
    """The engine modules outside the hook runtime with a code string naming a config file."""
    return {
        module
        for module, tree in engine_module_trees()
        if not module.startswith(f"{_RUNTIME}/")
        and any(_spells_a_name(text) for _, text in _code_strings(tree))
    }


def test_the_config_filenames_have_one_definition_outside_the_hook_runtime() -> None:
    """Spec B.5.6: every module takes ``CONFIG_FILENAME``/``CONFIG_LOCAL_FILENAME`` from
    ``config/files.py`` instead of spelling the names (16 modules did, B.3 item 14).

    The sets are compared whole, so the allowlist only shrinks: a module that stops
    spelling a name must leave it."""
    assert _modules_spelling_a_name() == {_HOME, *_ALLOWED}


def test_the_filename_walk_sees_f_string_parts_and_skips_docstrings() -> None:
    """Guard the guard, on a sample module: line 1 is a docstring, line 2 an f-string."""
    sample = f'"""Reads {CONFIG_FILENAME}."""\nwhere = f"{{root}}/{CONFIG_LOCAL_FILENAME}"\n'

    found = [line for line, text in _code_strings(ast.parse(sample)) if _spells_a_name(text)]

    assert found == [2]
