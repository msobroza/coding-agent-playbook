"""``playbook validate`` over a skill's ``playbook.references`` list (prU D47, D48).

The engine renders a skill's "References and examples" list from these entries,
so each must be usable: a mapping with ``path`` and a one-line ``open_when``
and an optional ``applies_if`` in the rule predicate language; the path is
relative, under ``references/`` or ``examples/``, and exists in the skill
directory (a file, or a directory such as one example project). Once a skill
declares ``sections`` or ``references``, every file under its ``references/``
and ``examples/`` must be covered by an entry (its own path or a parent
directory's); license files are exempt (D19). Skills that declare neither are
left as they are today (the ticket's "skills without sections behave as
today"); F-02's final-state test covers every core skill. A list-typed predicate
key given a bare string is reported here, never at render time.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.skills.playbook_block import PLAYBOOK_BLOCK_KEY, playbook_block
from coding_agent_playbook.skills.sections import (
    REFERENCES_KEY,
    declared_sections_value,
    one_line_phrase_problem,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from coding_agent_playbook.artifacts.skill import Skill

#: Evaluates one ``applies_if`` mapping; raises ``ValueError`` when it is malformed.
#: ``dict[str, Any]`` on purpose: the mapping is raw YAML handed unchanged to
#: ``detector.predicate.evaluate_predicate``, whose job is to reject bad shapes.
type PredicateCheck = Callable[[dict[str, Any]], object]

_FIELD: Final = f"'{PLAYBOOK_BLOCK_KEY}.{REFERENCES_KEY}'"
_ENTRY_KEYS: Final = ("path", "open_when", "applies_if")
_LISTED_DIRS: Final = ("references", "examples")
_PATH_SHAPE: Final = (
    "'path' must be a relative path under references/ or examples/, e.g. 'references/guide.md'"
)


def skill_reference_problems(skill: Skill, check_predicate: PredicateCheck) -> list[str]:
    """Every problem of ``skill``'s ``playbook.references`` list and its unlisted files.

    Example: ``skill_reference_problems(skill, lambda p: None)`` -> ``[]`` for a skill
    whose every references/ and examples/ file is listed.
    """
    block = playbook_block(skill)
    if REFERENCES_KEY not in block:
        declares_sections = declared_sections_value(skill) is not None
        return _unlisted_problems(skill, []) if declares_sections else []
    value = block[REFERENCES_KEY]
    if not isinstance(value, list):
        return [
            f"{_FIELD} must be a list of mappings with keys path, open_when and optional "
            f"applies_if, got {type(value).__name__} {value!r}"
        ]
    problems = [
        f"{_entry_label(index, entry)}: {problem}"
        for index, entry in enumerate(value, start=1)
        for problem in _entry_problems(entry, skill, check_predicate)
    ]
    listed = [entry["path"] for entry in value if _is_listed_path(entry)]
    return [*problems, *_unlisted_problems(skill, listed)]


def _entry_label(index: int, entry: object) -> str:
    """``reference 'references/guide.md' (entry 1 of 'playbook.references')``."""
    where = f"entry {index} of {_FIELD}"
    path = entry.get("path") if isinstance(entry, Mapping) else None
    return f"reference {path!r} ({where})" if isinstance(path, str) else f"reference {where}"


def _entry_problems(entry: object, skill: Skill, check_predicate: PredicateCheck) -> list[str]:
    """Shape, path and ``applies_if`` problems of one entry."""
    if not isinstance(entry, Mapping):
        return [
            "must be a mapping with keys path, open_when and optional applies_if, "
            f"got {type(entry).__name__} {entry!r}"
        ]
    problems = [
        f"has unknown key {key!r}; allowed keys: {', '.join(_ENTRY_KEYS)}"
        for key in sorted(str(key) for key in entry if key not in _ENTRY_KEYS)
    ]
    open_when_problem = one_line_phrase_problem("open_when", entry.get("open_when"))
    problems.extend([] if open_when_problem is None else [open_when_problem])
    problems.extend(_path_problems(entry.get("path"), _skill_dir(skill)))
    problems.extend(_applies_if_problems(entry, check_predicate))
    return problems


def _path_problems(value: object, skill_dir: Path | None) -> list[str]:
    """The path's shape, then whether it exists in the skill directory."""
    if value is None:
        return ["is missing 'path'"]
    if not _is_listable(value):
        return [_PATH_SHAPE]
    if skill_dir is not None and not (skill_dir / str(value)).exists():
        return [f"{value} does not exist in the skill directory"]
    return []


def _is_listable(value: object) -> bool:
    """A relative POSIX path without ``..`` whose first part is references or examples."""
    if not isinstance(value, str) or not value:
        return False
    parts = PurePosixPath(value).parts
    return (
        not PurePosixPath(value).is_absolute()
        and ".." not in parts
        and len(parts) >= 2
        and parts[0] in _LISTED_DIRS
    )


def _is_listed_path(entry: object) -> bool:
    """Whether ``entry`` is a mapping with a well-shaped ``path`` (it then covers files)."""
    return isinstance(entry, Mapping) and _is_listable(entry.get("path"))


def _applies_if_problems(entry: Mapping[Any, Any], check_predicate: PredicateCheck) -> list[str]:
    """The optional gate is a mapping, checked one predicate key at a time.

    ``Mapping[Any, Any]``: raw YAML, whose keys need not be strings; the predicate
    check rejects whatever it cannot read.
    """
    if "applies_if" not in entry:
        return []
    predicate = entry["applies_if"]
    if not isinstance(predicate, Mapping):
        return [
            "'applies_if' must be a mapping of predicate keys, got "
            f"{type(predicate).__name__} {predicate!r}"
        ]
    return list(_predicate_problems(predicate, check_predicate))


def _predicate_problems(
    predicate: Mapping[Any, Any], check_predicate: PredicateCheck
) -> Iterator[str]:
    # One key at a time: a predicate stops at the first key that does not hold.
    for key, value in predicate.items():
        try:
            check_predicate({key: value})
        except ValueError as exc:
            yield f"applies_if: {exc}"


def _skill_dir(skill: Skill) -> Path | None:
    """Where the skill's files live: its source dir, else a side directory's parent."""
    if skill.source_dir is not None:
        return skill.source_dir
    side_dir = skill.references_dir or skill.scripts_dir or skill.examples_dir
    return None if side_dir is None else side_dir.parent


def _unlisted_problems(skill: Skill, listed: list[str]) -> list[str]:
    """One problem per references/ or examples/ file that no entry covers."""
    skill_dir = _skill_dir(skill)
    if skill_dir is None:
        return []
    covered = [PurePosixPath(path) for path in listed]
    return [
        f"{relative} is not listed in {_FIELD}; add an entry with its path (or a parent "
        "directory) and open_when (license files are exempt)"
        for relative in _listable_files(skill_dir)
        if not any(relative == path or path in relative.parents for path in covered)
    ]


def _listable_files(skill_dir: Path) -> list[PurePosixPath]:
    """Every file under references/ and examples/, sorted, minus license files."""
    files = [
        PurePosixPath(path.relative_to(skill_dir).as_posix())
        for name in _LISTED_DIRS
        for path in (skill_dir / name).rglob("*")
        if path.is_file()
    ]
    return sorted(path for path in files if not _is_license(path))


def _is_license(path: PurePosixPath) -> bool:
    """License copies need no entry (D19, D47); D47 exempts nothing else."""
    return path.name.upper().startswith(("LICENSE", "COPYING"))
