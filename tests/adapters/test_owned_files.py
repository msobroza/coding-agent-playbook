"""Engine-owned single files: written whole only when the engine owns the path (review #1, #2).

``check_engine_owned`` / ``write_engine_owned`` guard the files ``playbook
sync`` writes whole at a fixed path (the Claude Code launcher, the OpenCode
shim): an absent path or a file carrying the sentinel line is the engine's; a
same-named file without it, anything not a regular file, or a symlink at the
path or at a directory between it and the repo root is the user's, and is never
opened for writing.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, ClassVar

import pytest

from coding_agent_playbook._sentinel import sentinel_line
from coding_agent_playbook.adapters._owned_files import (
    UserOwnedFileError,
    check_engine_owned,
    write_engine_owned,
)
from coding_agent_playbook.adapters.base import Adapter
from tests.fakes import record_opens
from tests.hook_samples import resolved_hook

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook._typing import Prompt, Rule

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks and FIFOs")

_REL = ".opencode/plugins/playbook-hooks.js"
_NEW = f"{sentinel_line('slash')}\nexport default {{ id: 'new' }}\n".encode()
_ENGINE_OLD = f"{sentinel_line('slash')}\nexport default {{ id: 'old' }}\n"
_USER = "export default { id: 'mine' }\n"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _refusal(path: Path, repo: Path) -> UserOwnedFileError:
    with pytest.raises(UserOwnedFileError) as caught:
        write_engine_owned(path, repo, _NEW)
    return caught.value


def test_absent_path_is_written_with_its_parents(tmp_path: Path) -> None:
    target = tmp_path / _REL

    assert write_engine_owned(target, tmp_path, _NEW) == target

    assert target.read_bytes() == _NEW


def test_engine_owned_prior_file_is_rewritten(tmp_path: Path) -> None:
    target = _write(tmp_path / _REL, _ENGINE_OLD)

    write_engine_owned(target, tmp_path, _NEW)

    assert target.read_bytes() == _NEW


def test_same_named_user_file_is_refused_and_untouched(tmp_path: Path) -> None:
    target = _write(tmp_path / _REL, _USER)

    error = _refusal(target, tmp_path)

    assert target.read_text(encoding="utf-8") == _USER
    assert error.path == _REL
    assert "sentinel" in error.reason
    assert str(error).startswith(f"{_REL}: ")


def test_sentinel_quoted_below_line_1_is_still_the_users(tmp_path: Path) -> None:
    target = _write(tmp_path / _REL, f"{_USER}{sentinel_line('slash')}\n")

    _refusal(target, tmp_path)

    assert target.read_text(encoding="utf-8").startswith(_USER)


def test_directory_at_the_path_is_refused(tmp_path: Path) -> None:
    target = tmp_path / _REL
    target.mkdir(parents=True)

    assert "not a regular file" in _refusal(target, tmp_path).reason
    assert target.is_dir()


def test_file_where_a_parent_directory_belongs_is_refused(tmp_path: Path) -> None:
    blocker = _write(tmp_path / ".opencode" / "plugins", _USER)

    error = _refusal(tmp_path / _REL, tmp_path)

    assert ".opencode/plugins" in error.reason
    assert "not a directory" in error.reason
    assert blocker.read_text(encoding="utf-8") == _USER


@posix_only
def test_symlink_at_the_path_is_refused_even_to_a_sentinel_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = _write(tmp_path / "outside" / "playbook-hooks.js", _ENGINE_OLD)
    repo = tmp_path / "repo"
    target = repo / _REL
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    opened = record_opens(monkeypatch)

    error = _refusal(target, repo)
    touched = [path for path in opened if path.resolve() == outside.resolve()]

    assert touched == []
    assert "symbolic link" in error.reason
    assert outside.read_text(encoding="utf-8") == _ENGINE_OLD
    assert target.is_symlink()


@posix_only
@pytest.mark.parametrize("linked", [".opencode", ".opencode/plugins"])
def test_symlinked_parent_directory_is_refused(tmp_path: Path, linked: str) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    repo = tmp_path / "repo"
    link = repo / linked
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)

    error = _refusal(repo / _REL, repo)

    assert f"{linked} is a symbolic link" in error.reason
    assert list(outside.rglob("*")) == []


@posix_only
def test_symlink_above_the_repo_root_is_not_the_users(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)

    write_engine_owned(alias / _REL, alias, _NEW)

    assert (real / _REL).read_bytes() == _NEW


@posix_only
def test_fifo_at_the_path_is_refused_without_opening_it(tmp_path: Path) -> None:
    target = tmp_path / _REL
    target.parent.mkdir(parents=True)
    os.mkfifo(target)

    assert "not a regular file" in _refusal(target, tmp_path).reason


def test_check_alone_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / _REL

    check_engine_owned(target, tmp_path)

    assert not (tmp_path / ".opencode").exists()


def test_path_outside_the_repo_root_is_a_caller_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not under the repo root"):
        check_engine_owned(tmp_path / "elsewhere" / "x.js", tmp_path / "repo")


class FakeRuntimeAdapter(Adapter):
    """An out-of-tree adapter that declares one runtime output and plans nothing itself."""

    name = "fake_runtime"
    runtime_outputs: ClassVar[tuple[str, ...]] = (".fake/hooks/shim.js",)

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        return []


def test_abc_default_plans_every_declared_runtime_output_once_a_hook_targets_it() -> None:
    """A new engine-owned file is guarded by declaring it: the default plan is conservative."""
    adapter = FakeRuntimeAdapter()

    assert adapter.planned_runtime_outputs([resolved_hook(supports=("fake_runtime",))]) == (
        ".fake/hooks/shim.js",
    )
    assert adapter.planned_runtime_outputs([resolved_hook(supports=("claude_code",))]) == ()
    assert adapter.planned_runtime_outputs([]) == ()
