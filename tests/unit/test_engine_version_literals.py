"""No test file spells the package version: a release must stay a one-line bump (issue #283).

Tests take the installed version from ``tests.engine_version.ENGINE_VERSION``;
a fixture that needs a fixed stamp uses a value no release will ever have.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tests.engine_version import ENGINE_VERSION

TESTS_ROOT: Final = Path(__file__).resolve().parents[1]
#: Text files a test reads or is: sources, fixture configs, lockfiles and JSON.
_SUFFIXES: Final = frozenset({".py", ".toml", ".json", ".lock", ".md", ".j2", ".txt", ".yaml"})
#: This file lists the likely next versions on purpose, so the guards skip it.
_THIS_FILE: Final = Path(__file__).resolve().relative_to(TESTS_ROOT).as_posix()


def quoted_version_hits(root: Path, version: str) -> list[str]:
    """``path:line`` of every quoted ``version`` in the text files under ``root``.

    Example::

        >>> quoted_version_hits(Path("/no/such/dir"), "1.2.3")
        []
    """
    needles = (f'"{version}"', f"'{version}'")
    hits: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.suffix in _SUFFIXES and p.is_file()):
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if any(needle in line for needle in needles):
                hits.append(f"{path.relative_to(root).as_posix()}:{number}")
    return hits


def _foreign_hits(version: str) -> list[str]:
    """Quoted ``version`` hits under ``tests/`` outside this guard file."""
    return [
        hit
        for hit in quoted_version_hits(TESTS_ROOT, version)
        if not hit.startswith(f"{_THIS_FILE}:")
    ]


def test_quoted_version_hits_names_each_line(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\nv = \"9.9.9\"\nw = '9.9.9'\n", encoding="utf-8")
    (tmp_path / "b.bin").write_text('"9.9.9"\n', encoding="utf-8")

    assert quoted_version_hits(tmp_path, "9.9.9") == ["a.py:2", "a.py:3"]


def test_no_test_file_hard_codes_the_package_version() -> None:
    hits = _foreign_hits(ENGINE_VERSION)

    assert hits == [], (
        f"these lines spell the package version {ENGINE_VERSION!r}; "
        f"use tests.engine_version.ENGINE_VERSION instead: {hits}"
    )


#: The releases most likely to come next; a fixture stamp must never equal one (issue #283).
_NEXT_LIKELY_VERSIONS: Final = ("0.1.0", "0.1.1", "0.2.0", "1.0.0")


def test_no_test_file_spells_a_likely_next_version() -> None:
    hits = {v: _foreign_hits(v) for v in _NEXT_LIKELY_VERSIONS}

    assert all(not found for found in hits.values()), (
        "these lines would break the next one-line version bump; "
        f"use a stamp no release will have (such as 9.9.9): {hits}"
    )
