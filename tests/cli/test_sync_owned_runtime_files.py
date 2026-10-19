"""``playbook sync`` never clobbers a user file at an engine-owned path (review findings #1, #2).

The OpenCode shim ``.opencode/plugins/playbook-hooks.js`` and the Claude Code
launcher ``.claude/hooks/playbook/launch.sh`` are written whole at fixed
paths. Before any adapter writes, sync checks each one it is about to write on
the real repo (like the ``settings.json`` preflight): a same-named file without
the sentinel line, a hard link (even sentinel-tagged), or a symlink at the path
or at a directory between it and the repo root, stops every mode with exit 1
naming the file, and nothing is written. An engine-owned prior file (sentinel on line 1) is rewritten as usual.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

import pytest

from coding_agent_playbook.generated_output.sentinel import sentinel_line
from coding_agent_playbook.hooks.registrations.claude import render_claude_launcher
from coding_agent_playbook.hooks.registrations.launcher import LAUNCHER_PATH
from coding_agent_playbook.hooks.registrations.opencode import OPENCODE_SHIM_PATH
from coding_agent_playbook.sync import pipeline as _sync
from tests.cli.hook_repo import CONFIG, hook_deps, make_hook_repo, tree
from tests.fakes import FakeGitClient
from tests.hook_samples import write_hook

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]

# The sample hooks bind builtins that validate (H6) resolves through the
# handler registry: install them as real entry points.
pytestmark = pytest.mark.usefixtures("sample_hook_handlers")

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")


class OwnedFile(NamedTuple):
    """One engine-owned runtime file: its path, a user's same-named file, a parent to link."""

    rel: str
    user_text: str
    linked_dir: str
    style: Literal["slash", "hash"]


_SHIM = OwnedFile(
    OPENCODE_SHIM_PATH, "export default { id: 'mine' }\n", ".opencode/plugins", "slash"
)
_LAUNCHER = OwnedFile(LAUNCHER_PATH, "echo 'my own launcher'\n", ".claude/hooks", "hash")
_BOTH = pytest.mark.parametrize("owned", [_SHIM, _LAUNCHER], ids=["shim", "launcher"])


def _sync_repo(repo: Path, tmp_path: Path, **kwargs: Any) -> int:
    kwargs.setdefault("git", FakeGitClient())
    kwargs.setdefault("hook_deps", hook_deps(tmp_path / "state"))
    return _sync.execute(repo, **kwargs)


def _repo(tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory) -> Path:
    """The K3 hook repo plus ``guard-oc``: a sync writes both the launcher and the shim."""
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    write_hook(
        repo / "playbook" / "hooks",
        "guard-oc",
        supports=["claude_code", "opencode"],
        handler={"builtin": "guard_y"},
    )
    return repo


def _place(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@_BOTH
def test_write_mode_refuses_a_same_named_user_file_before_any_write(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    owned: OwnedFile,
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)
    user_file = _place(repo / owned.rel, owned.user_text)
    before = tree(repo, skip=())

    assert _sync_repo(repo, tmp_path) == 1

    err = capsys.readouterr().err
    assert f"error: {owned.rel}: " in err
    assert "sentinel" in err
    assert f"playbook sync stopped; {owned.rel} was not changed" in err
    assert "Traceback" not in err
    assert user_file.read_text(encoding="utf-8") == owned.user_text
    assert tree(repo, skip=()) == before  # no adapter wrote, no lockfile either


@posix_only
@_BOTH
def test_write_mode_refuses_a_symlinked_parent_directory(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    owned: OwnedFile,
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = repo / owned.linked_dir
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)
    before = tree(repo, skip=())

    assert _sync_repo(repo, tmp_path) == 1

    assert f"{owned.linked_dir} is a symbolic link" in capsys.readouterr().err
    assert list(outside.rglob("*")) == []
    assert tree(repo, skip=()) == before


@_BOTH
def test_every_mode_refuses_a_hard_linked_owned_file(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    owned: OwnedFile,
) -> None:
    """A sentinel-tagged file hard-linked at the path: writing it whole would
    truncate the other name too, so every mode stops before any write."""
    repo = _repo(tmp_path, make_synthetic_repo)
    tagged = f"{sentinel_line(owned.style)}\nmine\n"
    other = _place(repo / "keep" / "other", tagged)
    (repo / owned.rel).parent.mkdir(parents=True, exist_ok=True)
    os.link(other, repo / owned.rel)
    before = tree(repo, skip=())

    assert _sync_repo(repo, tmp_path) == 1
    assert f"error: {owned.rel}: it is a hard link" in capsys.readouterr().err
    staged = FakeGitClient(staged=["src/app.py"])
    assert _sync_repo(repo, tmp_path, check=True) == 1
    assert _sync_repo(repo, tmp_path, git=staged, check_staged=True) == 1
    assert capsys.readouterr().out.count(f"Cannot verify {owned.rel}: it is a hard link") == 2
    assert other.read_text(encoding="utf-8") == tagged
    assert tree(repo, skip=()) == before


@posix_only
@_BOTH
def test_write_mode_refuses_a_symlink_at_the_path(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    owned: OwnedFile,
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)
    tagged = f"{sentinel_line(owned.style)}\nmine\n"
    target = _place(tmp_path / "outside" / "target", tagged)
    (repo / owned.rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / owned.rel).symlink_to(target)

    assert _sync_repo(repo, tmp_path) == 1

    assert f"error: {owned.rel}: " in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == tagged
    assert os.path.islink(repo / owned.rel)


@_BOTH
def test_engine_owned_prior_file_is_rewritten(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, owned: OwnedFile
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)
    assert _sync_repo(repo, tmp_path) == 0
    rendered = (repo / owned.rel).read_bytes()
    stale = f"{sentinel_line(owned.style)}\nan older engine's bytes\n"
    _place(repo / owned.rel, stale)

    assert _sync_repo(repo, tmp_path) == 0

    assert (repo / owned.rel).read_bytes() == rendered
    assert _sync_repo(repo, tmp_path, check=True) == 0


def test_launcher_rewrite_matches_the_packaged_render(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)
    _place(repo / LAUNCHER_PATH, f"{sentinel_line('hash')}\nold\n")

    assert _sync_repo(repo, tmp_path) == 0

    assert (repo / LAUNCHER_PATH).read_bytes() == render_claude_launcher().encode("utf-8")


@_BOTH
def test_check_modes_report_a_same_named_user_file(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    owned: OwnedFile,
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)
    assert _sync_repo(repo, tmp_path) == 0
    _place(repo / owned.rel, owned.user_text)
    before = tree(repo)
    staged = FakeGitClient(staged=["src/app.py"])
    capsys.readouterr()

    assert _sync_repo(repo, tmp_path, check=True) == 1
    assert _sync_repo(repo, tmp_path, git=staged, check_staged=True) == 1

    out = capsys.readouterr().out
    assert out.count(f"Cannot verify {owned.rel}: ") == 2
    assert "Move or rename what is in the way" in out
    assert tree(repo) == before


def test_user_file_at_the_shim_path_is_left_alone_when_no_shim_is_written(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)
    (repo / ".coding-agent-playbook.toml").write_text(
        f"{CONFIG}\n[hooks]\nenabled = false\n", encoding="utf-8"
    )
    user_file = _place(repo / OPENCODE_SHIM_PATH, _SHIM.user_text)

    assert _sync_repo(repo, tmp_path) == 0
    assert _sync_repo(repo, tmp_path, check=True) == 0

    assert user_file.read_text(encoding="utf-8") == _SHIM.user_text
