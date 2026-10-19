"""Which canonical skill files a native copy may publish (SPEC §10.8, §17.3).

A secret path (by name or by symlink target) and a link leaving the skill's
source directory are never copied; links that stay inside the skill are.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters._skill_sources import (
    copyable_skill_files,
    refused_skill_files,
)
from coding_agent_playbook.artifacts.skill import Skill

if TYPE_CHECKING:
    from pathlib import Path

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake home directory holding ``~/.aws/credentials``."""
    fake_home = tmp_path / "home"
    (fake_home / ".aws").mkdir(parents=True)
    (fake_home / ".aws" / "credentials").write_text("[default]\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


def _scripts(tmp_path: Path, files: dict[str, str]) -> Path:
    scripts = tmp_path / "skills" / "demo" / "scripts"
    for rel, text in files.items():
        (scripts / rel).parent.mkdir(parents=True, exist_ok=True)
        (scripts / rel).write_text(text, encoding="utf-8")
    return scripts


def test_absent_source_dir_copies_nothing(tmp_path: Path) -> None:
    assert copyable_skill_files(None, tmp_path / "dst") == []
    assert copyable_skill_files(tmp_path / "missing", tmp_path / "dst") == []


def test_plain_files_are_copyable_in_sorted_path_order(tmp_path: Path, home: Path) -> None:
    scripts = _scripts(tmp_path, {"b.sh": "b\n", "a/z.py": "z\n", "a.sh": "a\n"})
    copied = copyable_skill_files(scripts, tmp_path / "dst")
    assert [p.relative_to(scripts).as_posix() for p in copied] == ["a/z.py", "a.sh", "b.sh"]


def test_secret_named_file_is_refused_with_a_warning(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scripts = _scripts(tmp_path, {"run.sh": "echo\n", ".env": "DB_PASSWORD=x\n"})
    dst_root = tmp_path / "dst" / "scripts"

    copied = copyable_skill_files(scripts, dst_root)

    assert copied == [scripts / "run.sh"]
    err = capsys.readouterr().err
    assert f"warning: not copying {scripts / '.env'} into {dst_root}" in err
    assert "secret path" in err


@posix_only
def test_innocent_link_to_a_home_secret_is_refused(tmp_path: Path, home: Path) -> None:
    scripts = _scripts(tmp_path, {"run.sh": "echo\n"})
    (scripts / "notes.txt").symlink_to(home / ".aws" / "credentials")
    assert copyable_skill_files(scripts, tmp_path / "dst") == [scripts / "run.sh"]


@posix_only
def test_link_leaving_the_skill_dir_is_refused(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = tmp_path / "elsewhere" / "helper.sh"
    outside.parent.mkdir()
    outside.write_text("echo\n", encoding="utf-8")
    scripts = _scripts(tmp_path, {"run.sh": "echo\n"})
    (scripts / "helper.sh").symlink_to(outside)

    assert copyable_skill_files(scripts, tmp_path / "dst") == [scripts / "run.sh"]
    assert "outside the skill's source directory" in capsys.readouterr().err


@posix_only
def test_link_inside_the_skill_is_copied(tmp_path: Path, home: Path) -> None:
    scripts = _scripts(tmp_path, {"run.sh": "echo\n"})
    (scripts.parent / "references").mkdir()
    (scripts.parent / "references" / "api.md").write_text("# API\n", encoding="utf-8")
    (scripts / "alias.sh").symlink_to("run.sh")
    (scripts / "api.md").symlink_to("../references/api.md")

    copied = copyable_skill_files(scripts, tmp_path / "dst")

    assert [p.name for p in copied] == ["alias.sh", "api.md", "run.sh"]


@posix_only
def test_refused_skill_files_covers_scripts_and_references(tmp_path: Path, home: Path) -> None:
    scripts = _scripts(tmp_path, {"run.sh": "echo\n", "deploy.pem": "KEY\n"})
    references = scripts.parent / "references"
    references.mkdir()
    (references / "aws.md").symlink_to(home / ".aws" / "credentials")
    skill = Skill(
        frontmatter={"id": "demo", "description": "d"},
        body="Body\n",
        scripts_dir=scripts,
        references_dir=references,
        source_package="test",
    )

    refused = refused_skill_files(skill)

    assert [item.path for item in refused] == [scripts / "deploy.pem", references / "aws.md"]
    assert all(item.reason for item in refused)
