"""The layout adapter in ``playbook sync`` (D71, D78(12); prU L0-23).

When a ``[layout]`` key differs from its D60 default, sync rewrites that default
path prefix (and every ``layout_aliases`` prefix the enabled framework declares) in
every synced file, before the lockfile hashes it; with no ``[layout]`` table the
output is byte-identical to the output without the adapter.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.lockfile.model import compute_hash
from coding_agent_playbook.sync import pipeline as _sync
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = [pytest.mark.usefixtures("hermetic_git_env"), pytest.mark.catalog]

_CONFIG = ".coding-agent-playbook.toml"
_LOCKFILE = ".coding-agent-playbook.lock"
_SKILLS = ".claude/skills"
_GUARD_CONFIG = ".coding-agent-playbook/hooks/guard_config.json"
_TEXT = "Write specs to `docs/specs/YYYY-MM-DD-<slug>.md` and plans to `docs/acme/plans/x.md`.\n"


def _init_repo(repo: Path, **flags: object) -> None:
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "probe"\nrequires-python = ">=3.12"\ndependencies = []\n',
        encoding="utf-8",
    )
    args = argparse.Namespace(
        repo_root=str(repo),
        non_interactive=True,
        name="probe",
        kind="python-library",
        adapters="claude_code,agents_md",
        **flags,
    )
    assert _init.run(args) == 0


def _set_config(repo: Path, *, head: str = "", layout: str = "") -> None:
    """Prepend top-level ``head`` lines and append a ``[layout]`` table body."""
    path = repo / _CONFIG
    text = path.read_text(encoding="utf-8")
    kept = [line for line in text.splitlines() if not line.startswith(("framework =",))]
    tail = f"\n[layout]\n{layout}\n" if layout else ""
    path.write_text(f"{head}\n" + "\n".join(kept) + "\n" + tail, encoding="utf-8")


def _sync_ok(repo: Path, *, check: bool = False) -> None:
    assert _sync.execute(repo, check=check, git=FakeGitClient()) == 0


def _overlay(make_package: Callable[..., str], name: str, *, framework: bool = False) -> str:
    """An overlay with a rule, and a skill whose reference both mention layout paths."""
    package = make_package(name, resources=True)
    slug = name.replace("_", "-")
    resources = Path(importlib.import_module(package).__path__[0]) / "resources"
    rules = resources / "rules"
    rules.mkdir()
    (rules / f"{slug}-docs.md").write_text(
        f"---\nid: {slug}-docs\nname: Docs\ndescription: Where documents go.\n"
        f"scope: always\npriority: 50\n---\n{_TEXT}",
        encoding="utf-8",
    )
    skill = resources / "skills" / f"{slug}-notes"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nid: {slug}-notes\nname: {slug}-notes\ndescription: Notes.\n---\n{_TEXT}",
        encoding="utf-8",
    )
    (skill / "references" / "where.md").write_text(_TEXT, encoding="utf-8")
    _member_skill(resources, slug)
    if framework:
        (resources / "framework.toml").write_text(
            'name = "acme"\ndescription = "Acme."\n[layout_aliases]\n"docs/acme/plans/" = "plans"\n',
            encoding="utf-8",
        )
    return package


def _member_skill(resources: Path, slug: str) -> None:
    """A skill with one scoped member rule whose globs name the specs directory."""
    skill = resources / "skills" / f"{slug}-specs"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nid: {slug}-specs\nname: {slug}-specs\ndescription: Spec writing.\n"
        'playbook:\n  use_when: "writing a spec"\n  files: "Specs"\n---\n# Specs\n',
        encoding="utf-8",
    )
    (resources / "rules" / f"{slug}-spec-format.md").write_text(
        f"---\nid: {slug}-spec-format\nname: Spec format\ndescription: How a spec reads.\n"
        f'scope: scoped\nskill: {slug}-specs\nglobs:\n  - "docs/specs/**/*.md"\n'
        "priority: 50\n---\nKeep each spec under docs/specs.\n",
        encoding="utf-8",
    )


def _nudge_globs(repo: Path) -> list[str]:
    config = json.loads((repo / _GUARD_CONFIG).read_text(encoding="utf-8"))
    handlers = config["hooks"]["skill-nudge"]["handlers"]
    rows = next(iter(handlers.values()))["config"]["skills"]
    return [glob for row in rows for glob in row["globs"]]


def _tree(repo: Path) -> dict[str, bytes]:
    """Every file under ``repo`` except the lockfile's timestamp line."""
    files: dict[str, bytes] = {}
    for path in sorted(repo.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            data = path.read_bytes()
            if path.name == _LOCKFILE:
                data = b"\n".join(
                    line for line in data.splitlines() if not line.startswith(b"rendered_at")
                )
            files[path.relative_to(repo).as_posix()] = data
    return files


def _texts_mentioning(repo: Path, prefix: str) -> list[str]:
    """The synced files that still hold ``prefix`` as a path prefix (``src/x/docs/adr/`` is not)."""
    pattern = re.compile(rf"(?<![\w./-]){re.escape(prefix)}")
    files = [
        path
        for path in sorted(repo.rglob("*"))
        if path.is_file() and ".git" not in path.parts and path.name != _CONFIG
    ]
    return [
        path.relative_to(repo).as_posix()
        for path in files
        if pattern.search(path.read_text(encoding="utf-8", errors="replace"))
    ]


def test_no_layout_table_leaves_every_synced_file_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_package: Callable[..., str]
) -> None:
    overlay = _overlay(make_package, "acme_plain")
    _init_repo(tmp_path, framework="mattpocock")
    _set_config(tmp_path, head=f'framework = "mattpocock"\noverlays_enabled = ["{overlay}"]')
    _sync_ok(tmp_path)
    with_adapter = _tree(tmp_path)

    monkeypatch.setattr(_sync, "rewrite_layout_outputs", lambda *_args, **_kwargs: [])
    _sync_ok(tmp_path)

    assert _tree(tmp_path) == with_adapter


def test_a_changed_key_rewrites_core_overlay_and_framework_files(
    tmp_path: Path, make_package: Callable[..., str]
) -> None:
    overlay = _overlay(make_package, "acme_docs")
    _init_repo(tmp_path, framework="mattpocock")
    _set_config(
        tmp_path,
        head=f'framework = "mattpocock"\noverlays_enabled = ["{overlay}"]',
        layout='specs = "specs"\nagents = "notes/agents"\nadr = "decisions"',
    )

    _sync_ok(tmp_path)

    assert _texts_mentioning(tmp_path, "docs/specs") == []
    assert _texts_mentioning(tmp_path, "docs/agents/") == []
    assert _texts_mentioning(tmp_path, "docs/adr/") == []
    assert "specs/**/*.md" in _nudge_globs(tmp_path)
    reference = tmp_path / _SKILLS / "acme-docs-notes" / "references" / "where.md"
    assert "`specs/YYYY-MM-DD-<slug>.md`" in reference.read_text(encoding="utf-8")
    setup = tmp_path / _SKILLS / "setup-matt-pocock-skills" / "SKILL.md"
    assert "notes/agents/" in setup.read_text(encoding="utf-8")
    assert "specs/YYYY-MM-DD-<slug>.md" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    _sync_ok(tmp_path, check=True)


def test_a_framework_alias_maps_its_own_prefix(
    tmp_path: Path, make_package: Callable[..., str]
) -> None:
    framework = _overlay(make_package, "acme_framework", framework=True)
    _init_repo(tmp_path)
    _set_config(tmp_path, head=f'framework = "{framework}"', layout='plans = "plans"')

    _sync_ok(tmp_path)

    skill = tmp_path / _SKILLS / "acme-framework-notes" / "SKILL.md"
    assert "`plans/x.md`" in skill.read_text(encoding="utf-8")
    assert _texts_mentioning(tmp_path, "docs/acme/plans/") == []
    _sync_ok(tmp_path, check=True)


def test_the_lockfile_hashes_the_rewritten_bytes(
    tmp_path: Path, make_package: Callable[..., str]
) -> None:
    overlay = _overlay(make_package, "acme_lock")
    _init_repo(tmp_path)
    _set_config(tmp_path, head=f'overlays_enabled = ["{overlay}"]', layout='specs = "specs"')
    _sync_ok(tmp_path)

    rel = f"{_SKILLS}/acme-lock-notes/SKILL.md"
    lock = tomllib.loads((tmp_path / _LOCKFILE).read_text(encoding="utf-8"))
    entry = next(entry for entry in lock["entries"] if entry["path"] == rel)
    written = (tmp_path / rel).read_bytes()
    assert b"`specs/YYYY" in written
    assert entry["sha256"] == compute_hash(written)
