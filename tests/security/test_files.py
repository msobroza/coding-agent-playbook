"""Tests for the filesystem-aware secret checks (``security/files.py``, SPEC §17.3).

``is_secret_file`` judges a path both by its spelling below a root and by where
it resolves, so a symlink cannot give a credential file an innocent name.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from coding_agent_playbook.security.files import is_secret_file, user_home

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")


def test_user_home_follows_the_home_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert user_home() == str(tmp_path)


def test_secret_by_spelling_below_the_root(tmp_path: Path) -> None:
    home = str(tmp_path / "home")
    assert is_secret_file(tmp_path / "rules" / ".env", relative_to=tmp_path, home=home)
    assert not is_secret_file(tmp_path / "rules" / "50-x.md", relative_to=tmp_path, home=home)


def test_path_outside_the_root_is_judged_as_spelled(tmp_path: Path) -> None:
    home = str(tmp_path / "home")
    assert is_secret_file(tmp_path / "id_rsa", relative_to=tmp_path / "repo", home=home)


@posix_only
def test_innocent_name_linking_to_a_home_secret_is_secret(tmp_path: Path) -> None:
    """``notes.md -> ~/.aws/config``: the name is clean, the target is a secret store."""
    home = tmp_path / "home"
    (home / ".aws").mkdir(parents=True)
    (home / ".aws" / "config").write_text("[default]\n", encoding="utf-8")
    link = tmp_path / "repo" / "references" / "notes.md"
    link.parent.mkdir(parents=True)
    link.symlink_to(home / ".aws" / "config")
    assert is_secret_file(link, relative_to=tmp_path / "repo", home=str(home))


def test_never_opens_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / ".env"
    target.write_bytes(b"TOKEN=x\n")

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("is_secret_file must not open the file")

    monkeypatch.setattr(Path, "open", refuse)
    assert is_secret_file(target, relative_to=tmp_path, home=str(tmp_path / "home"))


def test_a_target_the_caller_resolved_is_judged_instead_of_resolving_again(tmp_path: Path) -> None:
    """``resolved`` lets a batch of files sharing parents resolve each one once."""
    home = tmp_path / "home"
    innocent = tmp_path / "repo" / "notes.md"  # never created: only ``resolved`` is judged
    credentials = home / ".aws" / "credentials"
    repo = tmp_path / "repo"

    assert is_secret_file(innocent, relative_to=repo, home=str(home), resolved=credentials)
    assert not is_secret_file(innocent, relative_to=repo, home=str(home), resolved=innocent)
    assert is_secret_file(repo / ".env", relative_to=repo, home=str(home), resolved=innocent)
