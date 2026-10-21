"""Choosing the spec-driven framework by name at init and in the committed config (D57; L0-19).

``playbook init --framework superpowers | mattpocock | none`` writes the committed
``framework`` key and syncs the matching bundled plugin; ``validate`` refuses two
frameworks enabled together; switching is a config change plus ``sync``, whose
lockfile removes the old framework's files; ``check`` prints the role map (D77).
"""

from __future__ import annotations

import argparse
import importlib
import tomllib
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import check as _check
from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.sync import pipeline as _sync
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

# init ends with a real sync (SubprocessGitClient); keep git off the developer's config.
pytestmark = [pytest.mark.usefixtures("hermetic_git_env"), pytest.mark.catalog]

_CONFIG = ".coding-agent-playbook.toml"
_MATTPOCOCK = "coding_agent_playbook.plugins.mattpocock_skills"
_SKILLS = ".claude/skills"


def _init_repo(repo: Path, **flags: object) -> int:
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "probe"\nrequires-python = ">=3.12"\ndependencies = []\n',
        encoding="utf-8",
    )
    args = argparse.Namespace(
        repo_root=str(repo),
        non_interactive=True,
        name="probe",
        kind="python-library",
        adapters="claude_code",
        **flags,
    )
    return _init.run(args)


def _config(repo: Path) -> dict[str, object]:
    return tomllib.loads((repo / _CONFIG).read_text(encoding="utf-8"))


def _set_framework(repo: Path, framework: str, *, overlays: str = "[]") -> None:
    text = (repo / _CONFIG).read_text(encoding="utf-8")
    lines = [
        line
        for line in text.splitlines()
        if not line.startswith(("framework =", "overlays_enabled ="))
    ]
    head = [f'framework = "{framework}"', f"overlays_enabled = {overlays}"]
    (repo / _CONFIG).write_text("\n".join([*head, *lines]) + "\n", encoding="utf-8")


def test_init_framework_mattpocock_enables_that_framework_only(tmp_path: Path) -> None:
    assert _init_repo(tmp_path, framework="mattpocock") == 0

    config = _config(tmp_path)
    assert config["framework"] == "mattpocock"
    assert "overlays_enabled" not in config
    assert (tmp_path / _SKILLS / "grill-me" / "SKILL.md").is_file()
    assert not (tmp_path / _SKILLS / "brainstorming").exists()
    assert _validate.run(argparse.Namespace(repo_root=str(tmp_path))) == 0


def test_init_framework_superpowers_writes_the_key(tmp_path: Path) -> None:
    assert _init_repo(tmp_path, framework="superpowers") == 0

    assert _config(tmp_path)["framework"] == "superpowers"
    assert (tmp_path / _SKILLS / "brainstorming" / "SKILL.md").is_file()


def test_init_without_a_framework_writes_none(tmp_path: Path) -> None:
    assert _init_repo(tmp_path) == 0

    assert _config(tmp_path)["framework"] == "none"
    assert not (tmp_path / _SKILLS / "brainstorming").exists()


def test_init_refuses_an_unknown_framework_before_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _init_repo(tmp_path, framework="mattpock") == 2

    err = capsys.readouterr().err
    assert "--framework" in err
    assert "mattpock" in err
    assert not (tmp_path / _CONFIG).exists()


def test_init_rerun_without_the_flag_keeps_the_framework(tmp_path: Path) -> None:
    assert _init_repo(tmp_path, framework="mattpocock") == 0
    assert _init_repo(tmp_path) == 0

    assert _config(tmp_path)["framework"] == "mattpocock"


def test_two_frameworks_fail_validate_naming_both(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _init_repo(tmp_path, framework="superpowers") == 0
    _set_framework(tmp_path, "superpowers", overlays=f'["{_MATTPOCOCK}"]')
    capsys.readouterr()

    assert _validate.run(argparse.Namespace(repo_root=str(tmp_path))) == 1

    fails = [line for line in capsys.readouterr().out.splitlines() if line.startswith("FAIL")]
    assert fails == [
        "FAIL framework: 2 frameworks are enabled together: "
        f"coding_agent_playbook.plugins.superpowers, {_MATTPOCOCK}; enable one with the "
        "framework key and remove the others from overlays_enabled"
    ]


def _overlay(
    make_package: Callable[..., str],
    *,
    framework_toml: str | None = None,
    skills: Mapping[str, str] = MappingProxyType({}),
) -> str:
    """An importable overlay whose ``resources/`` holds ``framework_toml`` and ``skills``.

    ``skills`` maps a skill id to its ``capabilities`` frontmatter value.
    """
    name = make_package("acme_cli_framework", resources=True)
    resources = Path(importlib.import_module(name).__path__[0]) / "resources"
    if framework_toml is not None:
        (resources / "framework.toml").write_text(framework_toml, encoding="utf-8")
    for skill_id, capabilities in skills.items():
        skill_dir = resources / "skills" / skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nid: {skill_id}\nname: {skill_id}\ndescription: The {skill_id} skill.\n"
            f"capabilities: {capabilities}\n---\n# {skill_id}\n",
            encoding="utf-8",
        )
    return name


def _validate_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> list[str]:
    capsys.readouterr()
    assert _validate.run(argparse.Namespace(repo_root=str(repo))) == 1
    return [line for line in capsys.readouterr().out.splitlines() if line.startswith("FAIL")]


def test_init_refuses_a_framework_that_ships_no_framework_toml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], make_package: Callable[..., str]
) -> None:
    overlay = _overlay(make_package)

    assert _init_repo(tmp_path, framework=overlay) == 2

    err = capsys.readouterr().err
    assert (
        f"error: --framework {overlay!r} is not a usable framework ({overlay} ships no "
        "framework.toml, so it is not a framework; list an add-on in overlays_enabled "
        "instead); use mattpocock, superpowers, an overlay module that ships "
        "framework.toml, or none; nothing was written"
    ) in err
    assert not (tmp_path / _CONFIG).exists()


def test_validate_fails_a_framework_key_naming_no_framework(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], make_package: Callable[..., str]
) -> None:
    overlay = _overlay(make_package)
    assert _init_repo(tmp_path) == 0
    _set_framework(tmp_path, overlay)

    assert _validate_fails(tmp_path, capsys) == [
        f"FAIL framework: {overlay} ships no framework.toml, so it is not a framework; "
        "list an add-on in overlays_enabled instead"
    ]


def test_validate_fails_a_framework_key_naming_an_unusable_layer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _init_repo(tmp_path) == 0
    _set_framework(tmp_path, "acme_missing_framework")

    assert _validate_fails(tmp_path, capsys) == [
        "FAIL framework: acme_missing_framework: not importable"
    ]


def test_validate_fails_a_broken_framework_toml_naming_its_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], make_package: Callable[..., str]
) -> None:
    overlay = _overlay(
        make_package,
        framework_toml='name = "acme"\ndescription = "A"\nextra = 1\n'
        '[layout_aliases]\n"docs/acme" = "plans"\n',
    )
    assert _init_repo(tmp_path) == 0
    _set_framework(tmp_path, overlay)

    assert _validate_fails(tmp_path, capsys) == [
        f"FAIL {overlay}/framework.toml: unknown key 'extra'; allowed keys: name, "
        "description, layout_aliases",
        f"FAIL {overlay}/framework.toml: layout_aliases 'docs/acme' is not a path prefix: "
        "write a relative directory path ending with '/', without '..'",
    ]


def test_validate_fails_bad_capability_tags_naming_the_skill(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], make_package: Callable[..., str]
) -> None:
    overlay = _overlay(
        make_package,
        framework_toml='name = "acme"\ndescription = "A"\n',
        skills={"ship": "[deploy]", "ask": "[clarify]", "ask-more": "[clarify]"},
    )
    assert _init_repo(tmp_path) == 0
    _set_framework(tmp_path, overlay)

    fails = _validate_fails(tmp_path, capsys)

    assert f"FAIL {overlay} skills/ship: capabilities has unknown role 'deploy'; " in "\n".join(
        fails
    )
    assert (
        f"FAIL {overlay} skills/ask-more: capabilities role 'clarify' is already declared "
        "by skill 'ask'; one skill per role"
    ) in fails


def test_switching_framework_leaves_only_the_new_framework(tmp_path: Path) -> None:
    assert _init_repo(tmp_path, framework="mattpocock") == 0
    _set_framework(tmp_path, "superpowers")

    assert _sync.execute(tmp_path, git=FakeGitClient()) == 0

    assert not (tmp_path / _SKILLS / "grill-me").exists()
    assert (tmp_path / _SKILLS / "brainstorming" / "SKILL.md").is_file()
    assert _sync.execute(tmp_path, check=True, git=FakeGitClient()) == 0


def test_synced_framework_skills_carry_no_capabilities_key(tmp_path: Path) -> None:
    assert _init_repo(tmp_path, framework="mattpocock") == 0

    text = (tmp_path / _SKILLS / "grill-me" / "SKILL.md").read_text(encoding="utf-8")
    assert "capabilities" not in text


def test_check_prints_the_framework_role_map(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _init_repo(tmp_path, framework="mattpocock") == 0
    capsys.readouterr()

    assert _check.run(argparse.Namespace(repo_root=str(tmp_path), refresh=False)) == 0

    out = capsys.readouterr().out
    assert (
        "  framework mattpocock: clarify -> grill-me, clarify_with_docs -> grill-with-docs, "
        "spec -> to-spec, plan -> to-tickets, tdd -> tdd, debug -> diagnosing-bugs, "
        "review -> two-axis-review"
    ) in out


def test_check_says_when_no_framework_is_enabled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _init_repo(tmp_path) == 0
    capsys.readouterr()

    assert _check.run(argparse.Namespace(repo_root=str(tmp_path), refresh=False)) == 0

    assert "  Framework: none" in capsys.readouterr().out
