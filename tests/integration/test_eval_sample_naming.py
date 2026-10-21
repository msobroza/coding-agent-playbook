"""D68: "Eval sample" replaces the old eval-test-case name everywhere.

The rename left no compatibility alias, so a spelling of the old name that
survives anywhere but the history is a stale reference. History is: ``specs/``
(design records), ``MIGRATION.md`` (the upgrade log, which must name the old
spellings), ``tests/architecture/move_map/`` (the append-only move log) and the
glossary's ``_Avoid_:`` line in ``CONTEXT.md``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Final

import pytest

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
#: Built from parts so this file does not match its own pattern.
_OLD_NAME: Final = re.compile("eval[_ ]?" + "tasks?|Eval" + "Task", re.IGNORECASE)
_OLD_SAMPLE_FILE: Final = "task" + ".toml"
_HISTORY_PREFIXES: Final = ("specs/", "tests/architecture/move_map/")
_HISTORY_FILES: Final = ("MIGRATION.md",)
_GLOSSARY: Final = "CONTEXT.md"


def _tracked_files() -> list[str]:
    """Every git-tracked path, or skip when the tree is not a git checkout."""
    git = shutil.which("git")
    if git is None or not (_REPO_ROOT / ".git").exists():
        pytest.skip("needs a git checkout to list tracked files")
    out = subprocess.run(
        [git, "ls-files", "-z"], cwd=_REPO_ROOT, capture_output=True, check=True, timeout=60
    ).stdout
    return [path for path in out.decode().split("\0") if path]


def _is_history(path: str) -> bool:
    return path.startswith(_HISTORY_PREFIXES) or path in _HISTORY_FILES


def _stale_lines(path: str) -> list[str]:
    try:
        text = (_REPO_ROOT / path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return []
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if path == _GLOSSARY and line.startswith("_Avoid_:"):
            continue
        if _OLD_NAME.search(line):
            found.append(f"{path}:{number}: {line.strip()}")
    return found


def test_no_old_eval_name_outside_history() -> None:
    files = [path for path in _tracked_files() if not _is_history(path)]

    stale = [hit for path in files for hit in _stale_lines(path)]
    stale += [path for path in files if _OLD_NAME.search(path)]

    assert stale == [], "\n".join(stale)


def test_every_sample_definition_is_named_sample_toml() -> None:
    old_files = [path for path in _tracked_files() if path.rsplit("/", 1)[-1] == _OLD_SAMPLE_FILE]

    assert old_files == []
