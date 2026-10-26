from pathlib import Path

import pytest

from src.netrc_auth import get_netrc_auth


def _write_netrc(path: Path) -> None:
    path.write_text("machine example.com login alice password s3cret\n", encoding="utf-8")


def test_reads_the_netrc_in_the_home_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NETRC", raising=False)
    _write_netrc(tmp_path / ".netrc")
    assert get_netrc_auth("example.com") == ("alice", "s3cret")


def test_no_netrc_file_means_no_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NETRC", raising=False)
    assert get_netrc_auth("example.com") is None


def test_the_netrc_variable_selects_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_netrc(tmp_path / ".netrc-ci")
    monkeypatch.setenv("NETRC", ".netrc-ci")
    assert get_netrc_auth("example.com") == ("alice", "s3cret")
