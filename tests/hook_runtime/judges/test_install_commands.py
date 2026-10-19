"""Install-shaped segments and the CLI word splitter under them (specs/prK-hook-pack.md §E.4).

``install_requests`` is the seam dependency-allowlist-guard and taint-escalation
share: tokens only (``echo pip install x`` installs nothing), runner launchers
read from ``raw_argv`` (``uvx ruff`` runs ``ruff``), PEP 503 names, and nothing
requested by a self-install or a sync.
"""

from __future__ import annotations

from typing import Final

import pytest

from coding_agent_playbook.hook_runtime.judges.cli_words import split_words, value_options
from coding_agent_playbook.hook_runtime.judges.install_commands import (
    InstallRequest,
    install_requests,
)
from coding_agent_playbook.hook_runtime.shell.parse import parse_shell

TORCH_INDEX: Final = "https://download.pytorch.org/whl/cu121"


def _requests(command: str) -> list[InstallRequest]:
    parsed = parse_shell(command, "posix", "/r")
    return [request for segment in parsed.segments for request in install_requests(segment)]


@pytest.mark.parametrize(
    ("command", "tool", "adder", "names"),
    [
        ("pip install Foo_Bar==1", "pip install", "pip", ("foo-bar",)),
        ("python3 -m pip install requests", "pip install", "pip", ("requests",)),
        ("sudo pip3.12 install rich", "pip install", "pip", ("rich",)),
        ("pip download sdist-pkg", "pip download", None, ("sdist-pkg",)),
        ("pip install 'pkg @ https://x.example/p.whl'", "pip install", "pip", ("pkg",)),
        ("pip install git+https://h.example/o/r.git#egg=Thing", "pip install", "pip", ("thing",)),
        ("uv add --dev pytest", "uv add", "uv", ("pytest",)),
        ("uv pip install x", "uv pip install", "uv pip", ("x",)),
        ("uv tool install black", "uv tool install", None, ("black",)),
        ("uv run --with rich python x.py", "uv run", None, ("rich",)),
        ("uvx ruff check", "uvx", None, ("ruff",)),
        ("uvx --from git+https://h.example/o/tool.git@v1 tool", "uvx", None, ("tool",)),
        ("pipx run cowsay hi", "pipx run", None, ("cowsay",)),
        ("poetry add -G dev Pytest_Cov", "poetry add", "poetry", ("pytest-cov",)),
        ("pdm add -d mypy", "pdm add", "pdm", ("mypy",)),
        (
            "conda install -c conda-forge numpy=1.2 conda-forge::scipy",
            "conda install",
            None,
            ("numpy", "scipy"),
        ),
        ("npm i -D @types/node@20 left-pad", "npm install", None, ("@types/node", "left-pad")),
        ("npx create-react-app app", "npx", None, ("create-react-app",)),
    ],
)
def test_install_requests_name_what_is_fetched(
    command: str, tool: str, adder: str | None, names: tuple[str, ...]
) -> None:
    (request,) = _requests(command)

    assert (request.tool, request.adder, request.names) == (tool, adder, names)


@pytest.mark.parametrize(
    "command",
    [
        "pip install -e .",
        'pip install -e ".[dev]"',
        "pip install ./dist/pkg-1.0-py3-none-any.whl",
        "pip install -U pip",
        "uv sync",
        "uv lock",
        "uv run pytest -q",
        "npm install",
        "npm ci",
        "echo pip install requests",
    ],
)
def test_syncs_self_installs_and_prose_request_nothing(command: str) -> None:
    assert [r.names for r in _requests(command) if r.names or r.files] == []


def test_files_indexes_and_dev_flags_are_kept() -> None:
    (pip,) = _requests(f"pip install -rreq.txt --extra-index-url {TORCH_INDEX} -i https://p/simple")
    (uv,) = _requests("uv add --group dev --index pt=https://x.example/s?a=b torch")

    assert (pip.files, pip.indexes) == (
        ("req.txt",),
        (("primary", "https://p/simple"), ("extra", TORCH_INDEX)),
    )
    assert (uv.dev, uv.indexes) == (True, (("extra", "https://x.example/s?a=b"),))


def test_split_words_reads_values_flags_and_operands() -> None:
    values = value_options("-r -d --data")
    words = split_words(["-rreq.txt", "-d@f", "--data=x", "-v", "-", "a", "--", "-b"], values)
    runner = split_words(
        ["--from", "x", "tool", "--flag"], value_options("--from"), stop_at_operand=True
    )

    assert words.values == [("-r", "req.txt"), ("-d", "@f"), ("--data", "x")]
    assert (words.flags, words.operands) == ({"-v"}, ["-", "a", "-b"])
    assert (runner.of(value_options("--from")), runner.operands) == (["x"], ["tool", "--flag"])
