"""Which docs tools a repository configures (D69, D78(10)): the config readers.

Each row writes config files into an empty repository and states what
:func:`doctest_globs` or :func:`doc8_configured` reads from them, including
pytest's own config precedence and files that do not parse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.commands.twins._docs_config import doc8_configured, doctest_globs

if TYPE_CHECKING:
    from pathlib import Path

_PYPROJECT_MD: Final = '[tool.pytest.ini_options]\naddopts = "--doctest-glob=*.md"\n'
_INI_TXT: Final = "[pytest]\naddopts = --doctest-glob=*.txt\n"
_SETUP_CFG_MD: Final = "[tool:pytest]\naddopts = --doctest-glob=*.md\n"


def _write_all(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        pytest.param({}, (), id="no-config"),
        pytest.param({"pyproject.toml": _PYPROJECT_MD}, ("*.md",), id="pyproject"),
        pytest.param(
            {
                "pyproject.toml": '[tool.pytest.ini_options]\naddopts = ["--doctest-glob", "*.rst"]\n'
            },
            ("*.rst",),
            id="pyproject-list-space-form",
        ),
        pytest.param(
            {"pytest.ini": _INI_TXT, "pyproject.toml": _PYPROJECT_MD},
            ("*.txt",),
            id="pytest-ini-over-pyproject",
        ),
        pytest.param(
            {"pyproject.toml": _PYPROJECT_MD, "tox.ini": _INI_TXT},
            ("*.md",),
            id="pyproject-over-tox",
        ),
        pytest.param(
            {"tox.ini": "[pytest]\naddopts = --doctest-glob *.txt\n", "setup.cfg": _SETUP_CFG_MD},
            ("*.txt",),
            id="tox-over-setup-cfg",
        ),
        pytest.param(
            {"setup.cfg": "[tool:pytest]\naddopts = -q --doctest-glob=*.md --doctest-glob *.rst\n"},
            ("*.md", "*.rst"),
            id="setup-cfg-both-forms",
        ),
        pytest.param(
            {"tox.ini": "[testenv]\ncommands = pytest\n", "setup.cfg": _SETUP_CFG_MD},
            ("*.md",),
            id="tox-without-pytest-section-falls-through",
        ),
        pytest.param(
            {"pytest.ini": "[pytest]\naddopts = --doctest-glob='*.md\n"},
            (),
            id="unbalanced-quotes",
        ),
        pytest.param({"pyproject.toml": "[tool.pytest.ini_options\n"}, (), id="malformed-toml"),
        pytest.param({"pytest.ini": "addopts = --doctest-glob=*.md\n"}, (), id="malformed-ini"),
        pytest.param(
            {"pytest.ini": "[pytest]\naddopts = --doctest-glob\n"}, (), id="dangling-flag"
        ),
    ],
)
def test_doctest_globs(tmp_path: Path, files: dict[str, str], expected: tuple[str, ...]) -> None:
    _write_all(tmp_path, files)

    assert doctest_globs(tmp_path) == expected


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        pytest.param({}, False, id="no-config"),
        pytest.param({".doc8.ini": ""}, True, id="dot-doc8-ini"),
        pytest.param({"doc8.ini": ""}, True, id="doc8-ini"),
        pytest.param({"setup.cfg": "[doc8]\nmax-line-length = 99\n"}, True, id="setup-cfg"),
        pytest.param({"tox.ini": "[doc8]\nmax-line-length = 99\n"}, True, id="tox-ini"),
        pytest.param(
            {"pyproject.toml": "[tool.doc8]\nmax-line-length = 99\n"}, True, id="pyproject"
        ),
        pytest.param({"pyproject.toml": "[tool.doc8]\n"}, False, id="empty-pyproject-table"),
        pytest.param({"setup.cfg": "[flake8]\nmax-line-length = 99\n"}, False, id="other-section"),
        pytest.param({"setup.cfg": "doc8 = yes\n"}, False, id="malformed-ini"),
        pytest.param({"pyproject.toml": "[tool.doc8\n"}, False, id="malformed-toml"),
    ],
)
def test_doc8_configured(tmp_path: Path, files: dict[str, str], expected: bool) -> None:
    _write_all(tmp_path, files)

    assert doc8_configured(tmp_path) is expected
