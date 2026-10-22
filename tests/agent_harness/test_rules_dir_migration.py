"""agent_harness member rules move from root ``references/<id>.md`` to ``skills/<s>/rules/`` (prU D22).

An engine before prU wrote every scoped rule of the harness tree as the root
``references/<id>.md`` (plus ``references/REFERENCES.md``), all recorded in the
lockfile. The first sync after the upgrade writes each member of an emitted
skill at ``skills/<skill>/rules/<id>.md`` and settles the old pristine copies:
they are gone, and so are their lockfile rows.

``_rewind_to_references_layout`` turns a repo synced by this engine into the
state the previous engine left: the same rule bytes and lockfile rows, spelled
under the root ``references/``, with that directory's ``REFERENCES.md`` routing
file and its lockfile row.
"""

from __future__ import annotations

import dataclasses
import shutil
from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness import emitter
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.lockfile.model import LockEntry, compute_hash
from coding_agent_playbook.sync import pipeline as _sync
from tests.fakes import FakeGitClient
from tests.plugins.superpowers_expectations import consumer_config

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    MakeRepo = Callable[..., Path]


def _config() -> str:
    return consumer_config(overlays=[], adapters=("agent_harness",))


def _harness_rows(repo: Path) -> set[str]:
    """Every lockfile path under the harness ``skills/`` and ``references/``."""
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return {e.path for e in lockfile.entries if e.path.startswith(("skills/", "references/"))}


def _old_spelling(path: str) -> str:
    """``skills/s/rules/x.md`` -> ``references/x.md``."""
    return f"references/{path.rsplit('/', 1)[1]}"


_OLD_ROUTING = "references/REFERENCES.md"


def _old_routing_row(repo: Path, entries: list[LockEntry]) -> LockEntry:
    """Write the old ``references/REFERENCES.md`` and return its row, shaped like ``SKILLS.md``'s."""
    text = emitter.routing_file(
        "On-demand references and scoped rules.", "Routing index for `references/`.\n"
    ).encode("utf-8")
    (repo / _OLD_ROUTING).write_bytes(text)
    [skills_routing] = [e for e in entries if e.path == "skills/SKILLS.md"]
    return dataclasses.replace(
        skills_routing, path=_OLD_ROUTING, sha256=compute_hash(text), bytes=len(text)
    )


def _rewind_to_references_layout(repo: Path, members: set[str]) -> None:
    """Leave ``repo`` as an engine before prU synced it: members under the root ``references/``."""
    (repo / "references").mkdir()
    for path in sorted(members):
        shutil.move(repo / path, repo / _old_spelling(path))
    for rules_dir in sorted((repo / "skills").glob("*/rules")):
        rules_dir.rmdir()
    state = FileSystemStateSource(repo_root=repo)
    lockfile = state.load_lockfile()
    assert lockfile is not None
    lockfile.entries = [
        *(
            dataclasses.replace(e, path=_old_spelling(e.path)) if e.path in members else e
            for e in lockfile.entries
        ),
        _old_routing_row(repo, lockfile.entries),
    ]
    state.save_lockfile(lockfile)


def test_resync_moves_pristine_root_references_into_skill_rules(
    tmp_path: Path, make_synthetic_repo: MakeRepo
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_config())
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    members = {p for p in _harness_rows(repo) if "/rules/" in p}
    assert members, "the synthetic repo must activate at least one member rule"
    assert not (repo / "references").exists()
    _rewind_to_references_layout(repo, members)
    assert _OLD_ROUTING in _harness_rows(repo)

    assert _sync.execute(repo, git=FakeGitClient()) == 0

    for path in members:
        assert (repo / path).is_file(), path
        assert not (repo / _old_spelling(path)).exists(), path
    assert not (repo / _OLD_ROUTING).exists()
    assert not (repo / "references").exists()
    assert {p for p in _harness_rows(repo) if p.startswith("references/")} == set()
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0
