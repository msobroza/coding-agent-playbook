"""Which canonical skill files a native copy may publish (SPEC §10.8, §17.3).

A secret path (by name or by symlink target) and a link leaving the skill's
source directory are never copied; links that stay inside the skill are.
"""

from __future__ import annotations

import random
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.generated_output.source_files import (
    RefusedSkillFile,
    _partition,
    copyable_skill_files,
    refused_skill_files,
    skill_subtree_files,
)
from coding_agent_playbook.security.paths import is_secret_path
from tests.generated_output.link_zoo import build_link_zoo, random_link_tree, relink_directory

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


def _partition_before_batch(src: Path, *, home: str) -> tuple[list[Path], list[RefusedSkillFile]]:
    """``_partition`` as of 8eb43dff (two ``Path.resolve()`` per file), kept as the oracle."""
    skill_root = src.parent.resolve()
    copyable: list[Path] = []
    refused: list[RefusedSkillFile] = []
    for source_file in skill_subtree_files(src):
        reason = _refusal_reason_before_batch(source_file, src, skill_root, home)
        if reason is None:
            copyable.append(source_file)
        else:
            refused.append(RefusedSkillFile(source_file, reason))
    return copyable, refused


def _refusal_reason_before_batch(
    source_file: Path, src: Path, skill_root: Path, home: str
) -> str | None:
    """``_refusal_reason`` with the old ``is_secret_file`` inlined, as of 8eb43dff."""
    try:
        spelled = source_file.relative_to(src)
    except ValueError:
        spelled = source_file
    if is_secret_path(spelled, home=home) or is_secret_path(source_file.resolve(), home=home):
        return "it is a secret path, or links to one (SPEC §17.3)"
    target = source_file.resolve()
    if not target.is_relative_to(skill_root):
        return f"it links to {target}, outside the skill's source directory {skill_root}"
    return None


def _bait(src: Path, home: Path, elsewhere: Path) -> None:
    """A secret name, an innocent link to a home secret, links leaving and staying in the skill."""
    (src / ".env").write_text("TOKEN=x\n", encoding="utf-8")
    (src / "notes.txt").symlink_to(home / ".aws" / "credentials")
    elsewhere.mkdir(exist_ok=True)
    (elsewhere / "shared.md").write_text("x\n", encoding="utf-8")
    (src / "out.md").symlink_to(elsewhere / "shared.md")
    (src.parent / "references").mkdir(exist_ok=True)
    (src.parent / "references" / "x.md").write_text("x\n", encoding="utf-8")
    (src / "in.md").symlink_to("../references/x.md")


@posix_only
def test_partition_matches_the_per_path_implementation_over_every_link_shape(
    tmp_path: Path, home: Path
) -> None:
    scripts = tmp_path / "skills" / "demo" / "scripts"
    scripts.mkdir(parents=True)
    build_link_zoo(scripts)
    _bait(scripts, home, tmp_path / "elsewhere")
    (tmp_path / "linked").symlink_to(tmp_path / "skills")

    for src in (scripts, tmp_path / "linked" / "demo" / "scripts", scripts / "d1"):
        assert _partition(src, home=str(home)) == _partition_before_batch(src, home=str(home))
    copyable, refused = _partition(scripts, home=str(home))
    assert len(copyable) >= 3
    assert [item.path.name for item in refused] == [".env", "notes.txt", "out.md"]


@posix_only
@pytest.mark.parametrize("seed", range(10))
def test_partition_matches_the_per_path_implementation_on_random_trees(
    tmp_path: Path, home: Path, seed: int
) -> None:
    rng = random.Random(seed)
    area = tmp_path / "area"
    area.mkdir()
    _bait(area, home, tmp_path / "elsewhere")
    nodes = random_link_tree(area, rng)
    real_dirs = [node for node in nodes[1:] if node.is_dir() and not node.is_symlink()]
    for src in [area, *rng.sample(real_dirs, min(3, len(real_dirs)))]:
        assert _partition(src, home=str(home)) == _partition_before_batch(src, home=str(home))


@posix_only
def test_partition_resolves_afresh_on_every_call(tmp_path: Path, home: Path) -> None:
    """Pins the batch's scope, one per walk and never module-level: once the skills dir
    is relinked to a copy, the walked files resolve into the copy, inside the skill,
    as with per-file ``Path.resolve()``; a memo kept from the first walk would refuse
    them as links leaving it."""
    files = {"run.sh": "x\n", "lib/util.py": "x\n"}
    scripts = _scripts(tmp_path, files)
    _scripts(tmp_path / "copy", files)
    first = _partition(scripts, home=str(home))
    relink_directory(tmp_path / "skills", tmp_path / "copy" / "skills")

    second = _partition(scripts, home=str(home))

    assert second == _partition_before_batch(scripts, home=str(home))
    assert second == first == ([scripts / "lib" / "util.py", scripts / "run.sh"], [])
