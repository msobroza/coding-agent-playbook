"""The content digest of one catalog artifact: a rule, prompt, skill or hook (#281 ticket 03).

:func:`artifact_digest` is the single definition. ``playbook sync`` records it in
the lockfile and names the artifacts whose digest moved since the last sync;
release manifests, editions and release metrics reuse it, so it is computed
from the loaded artifact object (any artifact source, not only the filesystem)
and covers what changes the agent's behaviour:

- the frontmatter, normalized: keys sorted, values as plain JSON, an empty or
  ``None`` value the same as an absent key, and the bookkeeping keys in
  :data:`BOOKKEEPING_KEYS` dropped;
- the body before rendering (``template_body``; a skill's ``body``);
- the side files: a skill's ``rules/``, ``scripts/``, ``references/`` and
  ``examples/`` files and a hook's ``scripts/``, each as its sha256 under its
  path relative to the artifact directory.

The digest is the sha256 of the canonical JSON of those parts
(:func:`~coding_agent_playbook.lockfile.canonical_json.canonical_json`), so it
is the same on every machine and supported Python version.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook.artifacts.hook import Hook
from coding_agent_playbook.artifacts.member_reference import RULES_DIR
from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.lockfile.canonical_json import canonical_json

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

__all__ = ["BOOKKEEPING_KEYS", "DigestKind", "artifact_digest", "digest_kind"]

#: The artifact kinds a digest is computed for, as the lockfile spells them.
DigestKind = Literal["rule", "prompt", "skill", "hook"]

#: Frontmatter keys that never change what the agent is told: the retired
#: hand-bumped ``version`` and a prompt's ``eval_samples`` back-references.
#: Rule, prompt and hook loaders now refuse both (#281 ticket 04), but a skill's
#: frontmatter stays open (vendored SKILL.md files may carry ``version``) and
#: frozen editions will be read by a lenient loader, so the digest still drops them.
BOOKKEEPING_KEYS: Final[frozenset[str]] = frozenset({"version", "eval_samples"})

#: Bytecode caches the skill writer never copies, so they never reach a digest either.
_SKIPPED_DIRS: Final[frozenset[str]] = frozenset({"__pycache__"})
_SKIPPED_SUFFIXES: Final[tuple[str, ...]] = (".pyc", ".pyo")

type DigestArtifact = Rule | Prompt | Skill | Hook


def digest_kind(artifact: DigestArtifact) -> DigestKind:
    """The kind ``artifact`` is recorded under in the lockfile.

    Raises ``TypeError`` naming the value for anything that is not a rule,
    prompt, skill or hook.

    Example::

        >>> digest_kind(skill)  # doctest: +SKIP
        'skill'
    """
    if isinstance(artifact, Rule):
        return "rule"
    if isinstance(artifact, Prompt):
        return "prompt"
    if isinstance(artifact, Skill):
        return "skill"
    if isinstance(artifact, Hook):
        return "hook"
    raise TypeError(f"cannot digest {artifact!r}; expected a Rule, Prompt, Skill or Hook")


def artifact_digest(artifact: DigestArtifact) -> str:
    """The sha256 hex content digest of ``artifact`` (see the module docstring).

    Reordering or reformatting the frontmatter keeps it; editing the body, a
    behaviour-relevant key or a side file changes it.

    Example::

        >>> artifact_digest(Rule.from_markdown(path, "<repo-local>"))  # doctest: +SKIP
        '5f3c...'
    """
    payload = {
        "kind": digest_kind(artifact),
        "frontmatter": _normalized_frontmatter(_frontmatter_mapping(artifact)),
        "body": _source_body(artifact),
        "files": _side_file_hashes(artifact),
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _frontmatter_mapping(artifact: DigestArtifact) -> Mapping[str, Any]:
    """The frontmatter as a mapping: a skill's open dict, else the dataclass fields."""
    if isinstance(artifact, Skill):
        return artifact.frontmatter
    return dataclasses.asdict(artifact.frontmatter)


def _source_body(artifact: DigestArtifact) -> str:
    """The body before rendering; a skill has no template, so its body as loaded."""
    return artifact.body if isinstance(artifact, Skill) else artifact.template_body


def _normalized_frontmatter(frontmatter: Mapping[str, Any]) -> dict[str, Any]:
    """``frontmatter`` without bookkeeping keys and empty values, as plain JSON values."""
    return {
        str(key): _plain_json(value)
        for key, value in frontmatter.items()
        if str(key) not in BOOKKEEPING_KEYS and value not in ([], {}, (), None)
    }


def _plain_json(value: object) -> object:
    """``value`` with tuples as lists, keys as strings and dates as ISO text.

    YAML can load a date for a skill's open frontmatter; ISO text keeps it
    deterministic. Anything else that JSON cannot spell raises ``TypeError``
    naming the value.
    """
    if isinstance(value, dict):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain_json(item) for item in value]
    if isinstance(value, _dt.date | _dt.datetime):
        return value.isoformat()
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(
        f"cannot digest frontmatter value {value!r}; expected JSON-like data "
        "(str, int, float, bool, None, list, dict or a date)"
    )


def _side_file_hashes(artifact: DigestArtifact) -> dict[str, str]:
    """``{path relative to the artifact dir: sha256}`` of every side file, sorted by path."""
    hashes: dict[str, str] = {}
    for home, side_dir in _side_dirs(artifact):
        for path in _files_under(side_dir):
            relative = path.relative_to(home).as_posix()
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(hashes.items()))


def _side_dirs(artifact: DigestArtifact) -> list[tuple[Path, Path]]:
    """``(artifact dir, side dir)`` for each side dir the artifact has on disk."""
    if isinstance(artifact, Hook):
        if artifact.scripts_dir is None:
            return []
        return [(artifact.scripts_dir.parent, artifact.scripts_dir)]
    if not isinstance(artifact, Skill):
        return []
    home = artifact.source_dir or artifact.side_dir_home()
    dirs = [path for _, path in artifact.side_dirs() if path is not None]
    if home is not None and (home / RULES_DIR).is_dir():
        dirs.append(home / RULES_DIR)
    return [(home or path.parent, path) for path in dirs]


def _files_under(root: Path) -> Iterator[Path]:
    """Every regular file under ``root``, sorted, without following directory symlinks.

    Dot entries and bytecode caches are skipped: they are machine-local noise
    the skill writer never copies, so they must not move the digest.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name for name in dirnames if not name.startswith(".") and name not in _SKIPPED_DIRS
        )
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if name.startswith(".") or name.endswith(_SKIPPED_SUFFIXES) or not path.is_file():
                continue
            yield path
