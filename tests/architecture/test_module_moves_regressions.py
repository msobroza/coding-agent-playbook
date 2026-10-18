"""Regression tests of the module-path rewrite script (review of #152).

A package directory a checkout left with only ``__pycache__/`` inside, the comments
of a split import statement, and ``apply`` writing nothing when a later file is
refused. The rules themselves are in ``test_module_moves.py`` (specs/prT-package-layout.md 5.4.4).
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

from tests.architecture._module_moves_tree import holds_files, path_exists
from tests.architecture.module_moves import apply, check
from tests.architecture.module_moves_samples import (
    N1_MAP,
    N2_MAP,
    N2_TREE,
    N12_MAP,
    N12_TREE,
    FakeFormatter,
    load_test_map,
    read,
    repo_with,
    write_files,
)

if TYPE_CHECKING:
    from pathlib import Path

_WRITER = {"src/coding_agent_playbook/toml_writer.py": "def dumps() -> str: ...\n"}
_CONFIG = "coding_agent_playbook.config"
_SPLIT_LABEL = (
    f"from {_CONFIG} import Config, ConfigError"
    f" -> from {_CONFIG}.model import Config; from {_CONFIG}.schema import ConfigError"
)


def test_holds_files_counts_only_files_outside_pycache(tmp_path: Path) -> None:
    write_files(
        tmp_path,
        {
            "husk/__pycache__/models.cpython-313.pyc": "",
            "husk/sub/__pycache__/x.cpython-313.pyc": "",
            "data/__pycache__/y.cpython-313.pyc": "",
            "data/shims/run.json": "{}",
        },
    )
    (tmp_path / "empty").mkdir()

    assert [holds_files(tmp_path / name) for name in ("husk", "empty", "missing")] == [False] * 3
    assert holds_files(tmp_path / "data")  # a data directory needs no __init__.py
    assert path_exists("data/", tmp_path)
    assert not path_exists("husk/", tmp_path)
    assert path_exists("data/shims/run.json", tmp_path)
    assert not path_exists("data/shims/run.json/", tmp_path)  # a trailing / asks for a directory


def test_a_moved_package_dir_left_with_only_bytecode_is_not_current(tmp_path: Path) -> None:
    # Regression: after N12, git leaves harness/ on disk with its untracked __pycache__/.
    # The husk counted as a namespace package, so check passed locally but failed in CI's
    # fresh clone, and apply left the old names as they were.
    source = """
        from coding_agent_playbook import harness
        from coding_agent_playbook.harness import models

        # see src/coding_agent_playbook/harness/ and coding_agent_playbook.harness
    """
    repo = repo_with(tmp_path, {**N12_TREE, "tests/test_a.py": source})
    write_files(
        repo / "src/coding_agent_playbook/harness",
        {"__pycache__/models.cpython-313.pyc": "", "sub/__pycache__/x.cpython-313.pyc": ""},
    )
    moves = load_test_map(tmp_path, n12=N12_MAP)
    old, new = "coding_agent_playbook.harness", "coding_agent_playbook.agent_harness"

    assert check(repo, moves) == [
        "tests/test_a.py:1: from coding_agent_playbook import harness"
        " -> from coding_agent_playbook import agent_harness as harness",
        f"tests/test_a.py:2: {old} -> {new}",
        "tests/test_a.py:4: src/coding_agent_playbook/harness/ -> src/coding_agent_playbook/agent_harness/",
        f"tests/test_a.py:4: {old} -> {new}",
    ]
    apply(repo, moves, formatter=FakeFormatter())
    assert read(repo, "tests/test_a.py") == textwrap.dedent(
        """\
        from coding_agent_playbook import agent_harness as harness
        from coding_agent_playbook.agent_harness import models

        # see src/coding_agent_playbook/agent_harness/ and coding_agent_playbook.agent_harness
        """
    )
    assert check(repo, moves) == []


def test_split_import_repeats_its_trailing_pragma_on_every_statement(tmp_path: Path) -> None:
    # Regression: the pragma stayed on the last statement only, so E402 failed the gate.
    source = f"from {_CONFIG} import Config, ConfigError  # noqa: E402\n"
    repo = repo_with(tmp_path, {**N2_TREE, "tests/test_a.py": source})
    moves = load_test_map(tmp_path, n02=N2_MAP)

    assert check(repo, moves) == [f"tests/test_a.py:1: {_SPLIT_LABEL}"]
    apply(repo, moves, formatter=FakeFormatter())
    assert read(repo, "tests/test_a.py") == (
        f"from {_CONFIG}.model import Config  # noqa: E402\n"
        f"from {_CONFIG}.schema import ConfigError  # noqa: E402\n"
    )


def test_split_parenthesised_import_keeps_every_comment(tmp_path: Path) -> None:
    # Regression: a split dropped every comment inside the parentheses, the F401 pragma
    # after `(` included. A name's comment now goes with it, and the others go everywhere.
    source = f"""
        def load() -> None:
            from {_CONFIG} import (  # noqa: F401
                Config,  # written by coding_agent_playbook._toml
                ConfigError,  # the error
            )  # lazy
    """
    repo = repo_with(tmp_path, {**N2_TREE, **_WRITER, "tests/test_a.py": source})
    moves = load_test_map(tmp_path, n01=N1_MAP, n02=N2_MAP)

    assert check(repo, moves) == [f"tests/test_a.py:2: {_SPLIT_LABEL}"]
    apply(repo, moves, formatter=FakeFormatter())
    assert read(repo, "tests/test_a.py") == textwrap.dedent(
        f"""\
        def load() -> None:
            from {_CONFIG}.model import (  # noqa: F401  # lazy
                Config,  # written by coding_agent_playbook.toml_writer
            )
            from {_CONFIG}.schema import (  # noqa: F401  # lazy
                ConfigError,  # the error
            )
        """
    )
    assert check(repo, moves) == []


def test_split_after_other_code_puts_every_comment_at_the_line_end(tmp_path: Path) -> None:
    # A comment between `;`-joined statements would swallow the ones after it.
    source = f"""
        import os; from {_CONFIG} import (  # noqa: E402
            Config,  # the model
            ConfigError,
        )
    """
    repo = repo_with(tmp_path, {**N2_TREE, "tests/test_a.py": source})

    apply(repo, load_test_map(tmp_path, n02=N2_MAP), formatter=FakeFormatter())

    assert read(repo, "tests/test_a.py") == (
        f"import os; from {_CONFIG}.model import Config; from {_CONFIG}.schema import ConfigError"
        "  # noqa: E402  # the model\n"
    )


def test_plain_import_split_repeats_its_trailing_comment(tmp_path: Path) -> None:
    source = "import os, coding_agent_playbook._toml as toml  # noqa: E402\n"
    repo = repo_with(tmp_path, {**_WRITER, "tests/test_a.py": source})
    moves = load_test_map(tmp_path, n01=N1_MAP)

    assert check(repo, moves) == [
        "tests/test_a.py:1: import os, coding_agent_playbook._toml as toml"
        " -> import os; import coding_agent_playbook.toml_writer as toml"
    ]
    apply(repo, moves, formatter=FakeFormatter())
    assert read(repo, "tests/test_a.py") == (
        "import os  # noqa: E402\nimport coding_agent_playbook.toml_writer as toml  # noqa: E402\n"
    )


def test_apply_writes_nothing_when_a_later_file_is_refused(tmp_path: Path) -> None:
    # Regression: tests/a.py was rewritten before tests/z.py raised, and never formatted.
    stale = f"from {_CONFIG} import Config\n"
    tree = {**N2_TREE, "tests/a.py": stale, "tests/z.py": "from .config import Config\n"}
    repo = repo_with(tmp_path, tree)
    formatter = FakeFormatter()

    with pytest.raises(ValueError, match=r"tests/z\.py: line 1: relative import"):
        apply(repo, load_test_map(tmp_path, n02=N2_MAP), formatter=formatter)

    assert read(repo, "tests/a.py") == stale
    assert formatter.calls == []
