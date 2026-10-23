"""``detector.bounded_read``: the one bounded UTF-8 read every detector input goes through."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.detector.bounded_read import read_bounded_utf8

if TYPE_CHECKING:
    from pathlib import Path


def test_a_small_utf8_file_is_read(tmp_path: Path) -> None:
    path = tmp_path / "requirements.txt"
    path.write_text("flask\n", encoding="utf-8")

    assert read_bounded_utf8(path) == "flask\n"


def test_a_file_of_exactly_the_cap_is_read(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_bytes(b"x" * 8)

    assert read_bounded_utf8(path, max_bytes=8) == "x" * 8


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("oversized.txt", b"x" * 9),
        ("latin1.txt", b"caf\xe9\n"),
        ("missing.txt", None),
        ("a-directory.txt", "dir"),
    ],
    ids=["oversized", "not-utf8", "missing", "directory"],
)
def test_an_unusable_file_reads_as_none(
    tmp_path: Path, name: str, payload: bytes | str | None
) -> None:
    path = tmp_path / name
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    elif payload == "dir":
        path.mkdir()

    assert read_bounded_utf8(path, max_bytes=8) is None
