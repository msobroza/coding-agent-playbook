"""Which files of a skill's ``scripts/`` and ``references/`` a sync copies (SPEC §10.8).

Both native skill writers — the shared ``SkillWriter`` (``.claude/skills/``,
``.opencode/skills/``, ``.agents/skills/``) and the ``agent_harness`` adapter
(``skills/``) — walk a skill's subtrees through :func:`skill_subtree_files`
(via :func:`~coding_agent_playbook.adapters._skill_sources.copyable_skill_files`,
which then refuses secret paths and links leaving the skill), so the skip rule
lives in exactly one place.

The rule: **Python bytecode caches are never copied** — any path with a
``__pycache__`` component and any ``*.pyc``/``*.pyo`` file. They are
interpreter-tagged by-products, not content: ``pip install`` byte-compiles every
``.py`` in the engine wheel (bundled-plugin scripts included), and importing a
script in-process writes ``scripts/__pycache__/``. Copying them made the synced output
(and its lockfile entries) depend on how, and under which Python, the engine was
installed, so files were added and removed from one sync to the next.

Nothing else is skipped: a dot-file or any other file under ``scripts/`` or
``references/`` may be authored content, and the engine cannot tell otherwise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path, PurePath

#: Directory names whose whole subtree a sync never copies.
SKIPPED_DIR_NAMES: frozenset[str] = frozenset({"__pycache__"})

#: File suffixes a sync never copies (compiled and optimized bytecode).
SKIPPED_SUFFIXES: frozenset[str] = frozenset({".pyc", ".pyo"})


def is_bytecode_cache(relative: PurePath) -> bool:
    """Return whether ``relative`` (a path inside a skill subtree) is a bytecode cache.

    Judge the path *relative to* the subtree, so a source tree that itself
    lives under a ``__pycache__`` directory is not mistaken for one.

    Example: ``is_bytecode_cache(PurePath("__pycache__/run.cpython-312.pyc"))``
    -> ``True``; ``is_bytecode_cache(PurePath("run.py"))`` -> ``False``.
    """
    if SKIPPED_DIR_NAMES.intersection(relative.parts):
        return True
    return relative.suffix in SKIPPED_SUFFIXES


def skill_subtree_files(src: Path) -> list[Path]:
    """Return the files under ``src`` that a sync copies, sorted; caches excluded.

    Symlinked files are included (the callers dereference them when copying);
    directories are never returned.

    Example: ``skill_subtree_files(skill.scripts_dir)`` -> ``[<src>/run.py]``
    for a ``scripts/`` holding ``run.py`` and ``__pycache__/run.cpython-312.pyc``.
    """
    return sorted(
        path
        for path in src.rglob("*")
        if path.is_file() and not is_bytecode_cache(path.relative_to(src))
    )
