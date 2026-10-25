"""``playbook sync`` records artifact digests and names what changed (#281 ticket 03).

End to end through ``commands.sync.run`` on a synthetic consumer repo: the
lockfile carries one ``[[artifacts]]`` digest per dispatched artifact (always
rules that reach only ``AGENTS.md`` included), whole-file entries carry their
artifact's digest, and the last line of the output names the changed artifacts.
"""

from __future__ import annotations

import argparse
import tomllib
from typing import TYPE_CHECKING

from coding_agent_playbook.commands import sync as sync_cmd
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.sync._guidance_changes import NO_GUIDANCE_CHANGED

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

    from coding_agent_playbook.lockfile.model import Lockfile

    SyntheticRepoFactory = Callable[..., Path]

_LOCK = ".coding-agent-playbook.lock"


def _sync(repo: Path, capsys: pytest.CaptureFixture[str]) -> list[str]:
    """Run write-mode sync on ``repo``; return its stdout lines."""
    capsys.readouterr()
    assert sync_cmd.run(argparse.Namespace(repo_root=str(repo), check=False)) == 0
    return capsys.readouterr().out.splitlines()


def _lockfile(repo: Path) -> Lockfile:
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return lockfile


def _edit_rule(repo: Path, rule_id: str, old: str, new: str) -> None:
    path = repo / "playbook" / "rules" / f"{rule_id}.md"
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def test_first_sync_reports_every_artifact_as_new(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("style-guide", "Use spaces.\n")])

    last = _sync(repo, capsys)[-1]

    keys = [record.key for record in _lockfile(repo).artifacts]
    assert "rule:style-guide" in keys
    assert last == f"Guidance changed: new {', '.join(sorted(keys))}"


def test_a_second_sync_without_edits_reports_no_guidance_changed(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("style-guide", "Use spaces.\n")])
    _sync(repo, capsys)

    assert _sync(repo, capsys)[-1] == NO_GUIDANCE_CHANGED


def test_editing_a_rule_body_names_only_that_rule(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(
        tmp_path, rules=[("style-guide", "Use spaces.\n"), ("naming", "Name well.\n")]
    )
    _sync(repo, capsys)
    _edit_rule(repo, "style-guide", "Use spaces.", "Use tabs.")

    assert _sync(repo, capsys)[-1] == "Guidance changed: changed rule:style-guide"


def test_deleting_a_rule_names_it_as_removed(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(
        tmp_path, rules=[("style-guide", "Use spaces.\n"), ("naming", "Name well.\n")]
    )
    _sync(repo, capsys)
    (repo / "playbook" / "rules" / "naming.md").unlink()

    assert _sync(repo, capsys)[-1] == "Guidance changed: removed rule:naming"


def test_whole_file_entries_record_their_artifacts_digest(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("style-guide", "Use spaces.\n")])
    _sync(repo, capsys)

    lockfile = _lockfile(repo)
    digests = {record.key: record.digest for record in lockfile.artifacts}
    entry = lockfile.find(".continue/rules/50-style-guide.md")
    agents_md = lockfile.find("AGENTS.md")
    assert entry is not None
    assert agents_md is not None
    assert entry.digest == digests["rule:style-guide"]
    assert agents_md.kind == "composite"
    assert agents_md.digest == ""


def test_a_lockfile_from_before_digests_still_loads_and_counts_as_a_first_sync(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("style-guide", "Use spaces.\n")])
    _sync(repo, capsys)
    lock = repo / _LOCK
    old_text = lock.read_text(encoding="utf-8").split("\n[[artifacts]]", 1)[0]
    lock.write_text(old_text.replace('digest = "', 'unused = "'), encoding="utf-8")

    last = _sync(repo, capsys)[-1]

    assert last.startswith("Guidance changed: new ")
    assert "changed rule" not in last


def test_the_written_lockfile_keeps_the_core_keys_older_readers_need(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("style-guide", "Use spaces.\n")])
    _sync(repo, capsys)

    doc = tomllib.loads((repo / _LOCK).read_text(encoding="utf-8"))

    assert {"schema_version", "engine_version", "rendered_at", "entries"} <= doc.keys()
    assert all({"path", "sha256", "bytes"} <= entry.keys() for entry in doc["entries"])
    assert all(record.keys() == {"kind", "artifact_id", "digest"} for record in doc["artifacts"])
