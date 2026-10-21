"""Docs-consistency guard: the README documents ``playbook forge`` (specs/prF-forge-adapter.md §11.2, §13).

The section names every forge operation, its ``[forge]`` snippet parses with
the parser ``playbook forge`` uses, and the *Running on Domino Data Lab*
check script is valid bash that never prints a token.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Final

import pytest

from coding_agent_playbook.config.tables.forge import parse_forge_table
from coding_agent_playbook.forge.operations import OPERATIONS

_ROOT: Final = Path(__file__).resolve().parents[2]
_SECTION: Final = "## `playbook forge`"
_DOMINO: Final = "### Running on Domino Data Lab"
_FENCE: Final = re.compile(r"^```(\w*)\n(.*?)^```$", re.MULTILINE | re.DOTALL)
#: Ways a shell script could print a forge token.
_TOKEN_LEAKS: Final = re.compile(
    r"(?:-t\b|--show-token|printenv|echo\s+\"?\$\{?(?:GITLAB_TOKEN|GITLAB_ACCESS_TOKEN|"
    r"OAUTH_TOKEN|GH_TOKEN|GITHUB_TOKEN)|config get token|auth token)"
)


def _readme() -> str:
    return (_ROOT / "README.md").read_text(encoding="utf-8")


def _section(heading: str) -> str:
    text = _readme()
    start = text.index(f"\n{heading}\n")
    level = heading.split(" ", 1)[0]
    end = text.find(f"\n{level} ", start + len(heading) + 1)
    return text[start : end if end > 0 else None]


def _blocks(text: str, language: str) -> list[str]:
    return [body for lang, body in _FENCE.findall(text) if lang == language]


def _script() -> str:
    (script,) = [b for b in _blocks(_section(_DOMINO), "bash") if "domino-forge-check" in b]
    return script


@pytest.mark.parametrize("operation", [op.name for op in OPERATIONS])
def test_the_section_names_every_forge_operation(operation: str) -> None:
    assert f"`{operation}" in _section(_SECTION)


def test_the_forge_table_snippet_parses_with_the_engine_parser() -> None:
    (snippet,) = _blocks(_section(_SECTION), "toml")

    hosts = parse_forge_table(tomllib.loads(snippet)["forge"]).hosts

    assert hosts["ssh.acme.com"] == {"forge": "gitlab", "api_host": "gitlab.acme.com"}


def test_the_section_states_the_exit_codes_and_the_token_boundary() -> None:
    section = " ".join(_section(_SECTION).split())
    for code in ("`0`", "`1`", "`2`", "`3`"):
        assert f"| {code} |" in section
    assert "never reads or stores a forge token" in section
    assert "never pushes" in section


def test_the_domino_section_names_the_setup_steps() -> None:
    domino = _section(_DOMINO)
    for step in (
        "`/mnt/code`",
        "`/repos/<name>`",
        "Dockerfile",
        "`GITLAB_TOKEN`",
        "requirements.txt",
    ):
        assert step in domino
    assert "User environment variables" in domino


def test_the_domino_check_script_is_valid_bash() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not on PATH")

    done = subprocess.run(
        [bash, "-n"], input=_script(), capture_output=True, text=True, timeout=30, check=False
    )

    assert done.returncode == 0, done.stderr


def test_the_domino_check_script_never_prints_a_token() -> None:
    script = _script()
    code = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))

    assert _TOKEN_LEAKS.findall(code) == []
    assert "redact" in code


def test_gitlab_duo_is_among_the_agents_md_readers() -> None:
    assert "GitLab Duo" in _readme()
