"""Which files of a skill's ``scripts/``, ``references/`` and ``examples/`` a sync copies (SPEC §10.8, §17.3).

Both native skill writers — the shared ``SkillWriter`` (``.claude/skills/``,
``.opencode/skills/``, ``.agents/skills/``) and the ``agent_harness`` adapter
(``skills/``) — walk a skill's subtrees through :func:`skill_subtree_files`
(via :func:`copyable_skill_files`, which then refuses secret paths and links
leaving the skill), so the skip rule lives in exactly one place. Sync's hook
script copies (``guard_config``) and the harness importer walk the same way, which
is why the rule lives in this leaf package, below adapters and hooks.

The rule: **Python bytecode caches are never copied** — any path with a
``__pycache__`` component and any ``*.pyc``/``*.pyo`` file. They are
interpreter-tagged by-products, not content: ``pip install`` byte-compiles every
``.py`` in the engine wheel (bundled-plugin scripts included), and importing a
script in-process writes ``scripts/__pycache__/``. Copying them made the synced output
(and its lockfile entries) depend on how, and under which Python, the engine was
installed, so files were added and removed from one sync to the next.

**Nor are tool caches and virtual environments** (also ``SKIPPED_DIR_NAMES``): a
``.ruff_cache/``, ``.mypy_cache/``, ``.pytest_cache/``, ``.hypothesis/`` or ``.venv/``
directory anywhere in a subtree. An example that ships its own ``pyproject.toml``
gets one as soon as a tool runs over the checkout (the engine's CI runs ``ruff
check .`` before pytest, which planted ``examples/fastapi-hotel-api/.ruff_cache/``
and its ``.gitignore``), so copying them made the output depend on what ran in the
engine's checkout before the sync (PR #266 CI).

Nothing else is skipped silently: a dot-file or any other file under ``scripts/``
or ``references/`` may be authored content, and the engine cannot tell otherwise.

**Which canonical skill files a native copy may publish.** A skill's ``scripts/``
and ``references/`` are byte-copied into every skills root and the
``agent_harness`` tree, so a copied file is *published*: hashed into the lockfile,
committed under ``[output] commit = true``, and written to the ``playbook sync
--check`` scratch tree. The walk starts from :func:`skill_subtree_files`, which
silently drops bytecode, tool caches and virtual environments (by-products, not
content). Two kinds of source file are then never copied; each is named in a
stderr warning instead:

- a **secret path** (``security.paths.is_secret_path``), judged both by its name
  inside the skill and by where it resolves, so ``scripts/notes.txt ->
  ~/.aws/credentials`` is refused, not laundered under an innocent name;
- a file whose real location lies **outside the skill's own source directory**
  (a symlink leaving it): it would publish any file the user can read. Links
  that stay inside the skill are dereferenced and copied as before.

``playbook validate`` reports the same files (:func:`refused_skill_files`).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coding_agent_playbook.security.files import is_secret_file, user_home

if TYPE_CHECKING:
    from pathlib import Path, PurePath

    from coding_agent_playbook.artifacts.skill import SideDirName, Skill

#: Directory names whose whole subtree a sync never copies: the bytecode cache, tool
#: caches and virtual environments. None of them is authored content.
SKIPPED_DIR_NAMES: frozenset[str] = frozenset(
    {"__pycache__", ".hypothesis", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv"}
)

#: File suffixes a sync never copies (compiled and optimized bytecode).
SKIPPED_SUFFIXES: frozenset[str] = frozenset({".pyc", ".pyo"})


def is_unauthored_path(relative: PurePath) -> bool:
    """Return whether ``relative`` (inside a skill subtree) is a by-product, never copied.

    True for bytecode (a ``*.pyc``/``*.pyo`` file) and for anything under a
    ``SKIPPED_DIR_NAMES`` directory: a bytecode cache, a tool cache or a virtual
    environment. Judge the path *relative to* the subtree, so a source tree that
    itself lives under such a directory is not mistaken for one.

    Example: ``is_unauthored_path(PurePath("app/.ruff_cache/.gitignore"))`` -> ``True``;
    ``is_unauthored_path(PurePath(".env.example"))`` -> ``False``.
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
        if path.is_file() and not is_unauthored_path(path.relative_to(src))
    )


@dataclass(frozen=True)
class RefusedSkillFile:
    """A canonical skill file that is never copied, and why.

    Example::

        RefusedSkillFile(Path("playbook/skills/demo/scripts/.env"), "a secret path")
    """

    path: Path
    reason: str


def copyable_skill_files(src: Path | None, dst_root: Path) -> list[Path]:
    """Every file under ``src`` a skill copy may publish, sorted.

    Warns on stderr, naming ``dst_root`` (the copy's destination), for each
    refused file. ``[]`` when ``src`` is absent.

    Example::

        for source_file in copyable_skill_files(skill.scripts_dir, skill_dir / "scripts"):
            ...  # copy it
    """
    if src is None or not src.is_dir():
        return []
    copyable, refused = _partition(src, home=user_home())
    for item in refused:
        _warn_refused(item, dst_root)
    return copyable


def published_skill_files(
    skill: Skill, name: SideDirName, dst_root: Path
) -> list[tuple[Path, Path]]:
    """``(source file, destination)`` for each file of ``skill``'s side dir ``name`` a sync writes.

    :func:`copyable_skill_files` of the side dir (``scripts``, ``references`` or
    ``examples``), minus the files a ``playbook.references`` entry whose
    ``applies_if`` failed withholds (``Skill.is_withheld``, prU D48, D58).
    ``[]`` when the skill has no such dir; ``ValueError`` (from
    ``Skill.side_dir``) for a name that is no side dir.

    Example::

        for src, dst in published_skill_files(skill, "examples", skill_dir / "examples"):
            ...  # copy src to dst
    """
    src_root = skill.side_dir(name)
    if src_root is None:
        return []
    pairs = [(src, src.relative_to(src_root)) for src in copyable_skill_files(src_root, dst_root)]
    return [
        (src, dst_root / relative)
        for src, relative in pairs
        if not skill.is_withheld(f"{name}/{relative.as_posix()}")
    ]


def refused_skill_files(skill: Skill) -> list[RefusedSkillFile]:
    """The files of ``skill``'s ``scripts/``, ``references/`` and ``examples/`` no copy will publish.

    Example::

        refused_skill_files(skill)  # [] for a skill without secrets or escaping links
    """
    home = user_home()
    refused: list[RefusedSkillFile] = []
    for _, src in skill.side_dirs():
        if src is not None and src.is_dir():
            refused.extend(_partition(src, home=home)[1])
    return refused


def _partition(src: Path, *, home: str) -> tuple[list[Path], list[RefusedSkillFile]]:
    """Split the files under ``src`` (sorted, caches excluded) into copyable and refused."""
    skill_root = src.parent.resolve()
    copyable: list[Path] = []
    refused: list[RefusedSkillFile] = []
    for source_file in skill_subtree_files(src):
        reason = _refusal_reason(source_file, src, skill_root, home)
        if reason is None:
            copyable.append(source_file)
        else:
            refused.append(RefusedSkillFile(source_file, reason))
    return copyable, refused


def _refusal_reason(source_file: Path, src: Path, skill_root: Path, home: str) -> str | None:
    """Why ``source_file`` must not be copied, or ``None`` when it may be."""
    if is_secret_file(source_file, relative_to=src, home=home):
        return "it is a secret path, or links to one (SPEC §17.3)"
    target = source_file.resolve()
    if not target.is_relative_to(skill_root):
        return f"it links to {target}, outside the skill's source directory {skill_root}"
    return None


def _warn_refused(item: RefusedSkillFile, dst_root: Path) -> None:
    # Plain stderr, not ``warnings.warn``: user-facing CLI output, and pytest
    # runs with ``filterwarnings = ["error"]``.
    print(f"warning: not copying {item.path} into {dst_root}: {item.reason}", file=sys.stderr)
