"""The answers files of a ``prepare --eval`` run, kept and restored with its metrics (spec D8).

A refused release discards its checkout, so ``scripts/release_eval.py`` copies
each target's ``answers/<target>.jsonl.gz`` into the kept directory beside its
metrics file, and ``--reuse-metrics`` puts it back into the release's
``answers/`` directory. A kept directory made before answers were stored has
none: the release then stores no answers for that target, and says so.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.answers_store import ANSWERS_SUFFIX

if TYPE_CHECKING:
    from pathlib import Path


def keep_answers(answers_dir: Path, kept: Path) -> None:
    """Copy every answers file of ``answers_dir`` into ``kept``; none without the directory.

    Example::

        >>> keep_answers(release / "answers", kept)  # doctest: +SKIP
    """
    for path in sorted(answers_dir.glob(f"*{ANSWERS_SUFFIX}")):
        shutil.copy2(path, kept / path.name)


def restore_answers(kept_dir: Path, name: str, dest: Path) -> None:
    """Copy target ``name``'s kept answers file to ``dest``; a note when none was kept.

    Example::

        >>> restore_answers(kept, "opus", release / "answers" / "opus.jsonl.gz")  # doctest: +SKIP
    """
    kept = kept_dir / f"{name}{ANSWERS_SUFFIX}"
    if not kept.is_file():
        print(f"release: {name}: no answers kept; this release stores none for that target")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(kept, dest)
