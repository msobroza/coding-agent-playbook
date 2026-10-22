"""The directory gates of one core skill: what it may hold and where its links may lead (prU L0-13).

A core skill ships ``SKILL.md`` and may ship ``rules/`` (its member rules,
D5), ``references/`` (long-form documents and the license copies, D19, D25,
D26), ``scripts/`` (the stdlib scripts from python_design, D2) and
``examples/`` (a runnable example app, D48). Each gate takes the skill's
directory and returns one problem string per violation, naming the
skill-relative path, so ``tests/integration/test_core_skills.py`` runs them over
the real catalog and ``tests/integration/test_core_skill_layout.py`` proves them
on scratch skills.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.validation.link_check import classify_link, extract_markdown_links

if TYPE_CHECKING:
    from collections.abc import Callable

#: Whether a file name may sit in one side directory.
type _FileTest = Callable[[str], bool]

#: The entries a core skill directory may hold, file first.
SKILL_ENTRIES: Final = ("SKILL.md", "examples", "references", "rules", "scripts")
#: The byte-identical upstream license copies a core skill's references/ may hold (D19).
LICENSE_COPY_NAMES: Final = frozenset(
    {"LICENSE.python-best-practices", "LICENSE.python-clean-architecture"}
)
#: A path segment after ``references/`` that is itself a directory: real nesting (D78(16)).
_NESTED_REFERENCE: Final = re.compile(r"references/[^\s/()\[\]`'\"<>]+/")


def skill_layout_problems(skill_dir: Path) -> list[str]:
    """Every directory gate's problems for ``skill_dir``: inventory, links, nesting.

    Example: ``skill_layout_problems(CORE_ROOT / "skills" / "python-coding")`` -> ``[]``.
    """
    return [*inventory_problems(skill_dir), *link_problems(skill_dir), *nesting_problems(skill_dir)]


def inventory_problems(skill_dir: Path) -> list[str]:
    """What ``skill_dir`` holds beyond :data:`SKILL_ENTRIES` and their allowed files.

    ``rules/`` holds only ``<id>.md`` and ``<id>.md.j2`` files, ``references/``
    only ``.md`` files and the two license copies, one level deep, and
    ``scripts/`` only ``.py`` files; ``examples/`` holds an app laid out as it
    needs.

    Example: a skill holding ``references/data.json`` ->
    ``["references/data.json: references/ holds only .md files and the license copies"]``.
    """
    problems = [
        f"{entry.name}: a core skill holds only {', '.join(SKILL_ENTRIES)}"
        for entry in sorted(skill_dir.iterdir())
        if entry.name not in SKILL_ENTRIES or entry.is_dir() != (entry.name != "SKILL.md")
    ]
    problems += _flat_dir_problems(skill_dir, "rules", _is_rule_file, "<id>.md or <id>.md.j2 files")
    problems += _flat_dir_problems(
        skill_dir, "references", _is_reference_file, ".md files and the license copies"
    )
    problems += _flat_dir_problems(skill_dir, "scripts", _is_script_file, ".py files")
    return problems


def link_problems(skill_dir: Path) -> list[str]:
    """Every markdown link in ``SKILL.md`` or a rule that leaves the skill or dangles.

    ``SKILL.md`` may link only its own ``references/<file>.md``; a rule may link
    any existing file inside the same skill directory (``../references/x.md``).
    Each problem names the linking file, its line and the link target.

    Example: a rule linking ``../../other/references/z.md`` ->
    ``["rules/r.md:6: link '../../other/references/z.md': target ... escapes ..."]``.
    """
    problems: list[str] = []
    for path in _linking_files(skill_dir):
        relative = path.relative_to(skill_dir).as_posix()
        for link in extract_markdown_links(path.read_text(encoding="utf-8")):
            reason = classify_link(
                link.target, base_dir=path.parent, root_dir=skill_dir, allowed_domains=()
            )
            if reason is None and path.name == "SKILL.md":
                reason = _skill_md_link_reason(link.target)
            if reason is not None:
                problems.append(f"{relative}:{link.line}: link {link.target!r}: {reason}")
    return problems


def nesting_problems(skill_dir: Path) -> list[str]:
    """Each ``SKILL.md``, rule or reference line naming a directory under ``references/``.

    References stay one level deep; the bare ``references/`` of a drawn skill
    tree is not nesting (D78(16)). Each problem names the file, line and match.

    Example: a rule saying ``references/deep/guide.md`` ->
    ``["rules/r.md:6: names 'references/deep/' (references are one level deep)"]``.
    """
    texts = [*_linking_files(skill_dir), *_files(skill_dir / "references", "*.md")]
    problems: list[str] = []
    for path in texts:
        relative = path.relative_to(skill_dir).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            problems += [
                f"{relative}:{number}: names {match!r} (references are one level deep)"
                for match in _NESTED_REFERENCE.findall(line)
            ]
    return problems


def _flat_dir_problems(skill_dir: Path, name: str, allowed: _FileTest, what: str) -> list[str]:
    """Each entry of ``skill_dir/name`` that is a directory or a file ``allowed`` rejects."""
    side_dir = skill_dir / name
    if not side_dir.is_dir():
        return []
    return [
        f"{name}/{entry.name}: {name}/ holds only {what}"
        for entry in sorted(side_dir.iterdir())
        if not entry.is_file() or not allowed(entry.name)
    ]


def _is_rule_file(name: str) -> bool:
    return name.endswith((".md", ".md.j2"))


def _is_reference_file(name: str) -> bool:
    return name.endswith(".md") or name in LICENSE_COPY_NAMES


def _is_script_file(name: str) -> bool:
    return name.endswith(".py")


def _linking_files(skill_dir: Path) -> list[Path]:
    """``SKILL.md`` and every rule source of ``skill_dir``, sorted."""
    rules = [*_files(skill_dir / "rules", "*.md"), *_files(skill_dir / "rules", "*.md.j2")]
    return [skill_dir / "SKILL.md", *sorted(rules)]


def _files(directory: Path, pattern: str) -> list[Path]:
    """The files directly in ``directory`` matching ``pattern``, sorted; ``[]`` without it."""
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob(pattern) if path.is_file())


def _skill_md_link_reason(target: str) -> str | None:
    """Why ``SKILL.md`` may not link ``target``: only ``references/<file>.md`` is allowed."""
    path = PurePosixPath(target.split("#", 1)[0])
    if not str(path) or str(path) == ".":
        return None  # an anchor in SKILL.md itself
    if len(path.parts) == 2 and path.parts[0] == "references" and path.suffix == ".md":
        return None
    return "SKILL.md links only its own references/<file>.md"
