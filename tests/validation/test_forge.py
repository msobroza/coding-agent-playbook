"""``playbook validate`` reports the ``[forge]`` table's problems (specs/prF-forge-adapter.md §5.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.cli import main
from tests.engine_version import ENGINE_VERSION

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


_CONFIG = f"""\
schema_version = 1

[engine]
version = "{ENGINE_VERSION}"

[project]
name = "demo"
kind = "python-library"

[forge]
hosts = {{ "git.acme.com" = "svn" }}
color = "blue"
"""


def test_validate_reports_the_checked_forge_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text(_CONFIG, encoding="utf-8")

    assert main(["validate", "--repo-root", str(tmp_path)]) == 1

    out = capsys.readouterr().out
    assert "[forge] unknown key 'color'; allowed: hosts" in out
    assert "[forge] hosts entry 'git.acme.com': 'svn' is not a forge" in out


def test_validate_accepts_a_valid_forge_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _CONFIG.replace('"svn"', '"gitlab"').replace('color = "blue"\n', "")
    (tmp_path / ".coding-agent-playbook.toml").write_text(config, encoding="utf-8")

    main(["validate", "--repo-root", str(tmp_path)])

    assert "[forge]" not in capsys.readouterr().out
