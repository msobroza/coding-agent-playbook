"""Parse an Agent Harness tree into the :mod:`~.models` object model (Track H1).

:func:`parse_harness` walks a harness root and classifies every directory:

- a ``.harnessleaf`` marker → an opaque :class:`LeafMarker` (never recursed);
- a typed leaf per the root ``.leaf-detectors`` (``skill`` leaves parse
  ``SKILL.md`` and capture ``scripts/`` + internal ``references/``);
- otherwise a grouping directory (read its routing file, then recurse).

Routing-file names derive from the **top-level** ancestor segment and propagate
through the whole subtree. Dotfiles and dot-directories are skipped. Markdown
files become :class:`ContentFile` (optional ``description`` from frontmatter);
non-markdown files become :class:`RawAsset` (read as **bytes**, sha256-hashed —
never assume UTF-8). See ``specs/prH-agent-harness.md`` §A/§B.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness.leaf_detectors import (
    LEAF_TYPE_OPAQUE,
    leaf_type,
    parse_leaf_detectors,
    routing_file_name,
)
from coding_agent_playbook.agent_harness.models import (
    ContentFile,
    HarnessDirectory,
    HarnessTree,
    LeafMarker,
    NotAHarnessError,
    RawAsset,
    ScriptFile,
    SkillLeaf,
)
from coding_agent_playbook.artifacts.frontmatter import split_frontmatter

if TYPE_CHECKING:
    from pathlib import Path

HARNESS_FILENAME = "HARNESS.md"
LEAF_DETECTORS_FILENAME = ".leaf-detectors"
SKILL_FILENAME = "SKILL.md"
SCRIPTS_DIRNAME = "scripts"
REFERENCES_DIRNAME = "references"

#: Detector leaf type that triggers SKILL.md parsing.
SKILL_LEAF_TYPE = "skill"


def parse_harness(root: Path) -> HarnessTree:
    """Parse the harness rooted at ``root`` into a :class:`HarnessTree`.

    Raises:
        NotAHarnessError: if ``root/HARNESS.md`` is absent.
        ValueError: if ``HARNESS.md`` lacks a required ``name``/``description``.
    """
    harness_md = root / HARNESS_FILENAME
    if not harness_md.is_file():
        raise NotAHarnessError(f"no {HARNESS_FILENAME} at {root}")

    frontmatter, body = split_frontmatter(harness_md.read_text(encoding="utf-8"))
    name = frontmatter.get("name")
    description = frontmatter.get("description")
    if not name or not description:
        raise ValueError(f"{HARNESS_FILENAME} requires non-empty 'name' and 'description'")

    detectors_file = root / LEAF_DETECTORS_FILENAME
    detectors = (
        parse_leaf_detectors(detectors_file.read_text(encoding="utf-8"))
        if detectors_file.is_file()
        else {}
    )

    directories = tuple(
        _parse_directory(child, routing_file_name(child.name), detectors)
        for child in _iter_subdirs(root)
    )
    return HarnessTree(
        name=name, description=description, body=body, path=root, directories=directories
    )


def _iter_subdirs(directory: Path) -> list[Path]:
    """Yield non-dot subdirectories of ``directory`` in deterministic order."""
    return sorted(
        child for child in directory.iterdir() if child.is_dir() and not child.name.startswith(".")
    )


def _parse_directory(
    directory: Path, routing_name: str, detectors: dict[str, str]
) -> HarnessDirectory:
    """Parse a grouping directory into a :class:`HarnessDirectory`.

    A directory carrying ``.harnessleaf`` is *terminal* (decision in §A): it
    records a :class:`LeafMarker` for itself, keeps its routing description and
    own content files, but is **not** recursed into — generic clients treat it
    as an opaque unit (e.g. ``evals/`` shields eval internals).
    """
    children: list[HarnessDirectory] = []
    leaves: list[SkillLeaf | LeafMarker] = []

    if leaf_type(directory, detectors) == LEAF_TYPE_OPAQUE:
        leaves.append(LeafMarker(path=directory))  # terminal — no recursion
    else:
        for sub in _iter_subdirs(directory):
            kind = leaf_type(sub, detectors)
            if kind == LEAF_TYPE_OPAQUE:
                leaves.append(LeafMarker(path=sub))  # opaque — do not recurse
            elif kind == SKILL_LEAF_TYPE:
                leaves.append(_parse_skill_leaf(sub))  # typed leaf — stop recursing
            else:
                # Grouping dir: routing name propagates from the top-level ancestor.
                children.append(_parse_directory(sub, routing_name, detectors))

    description = _routing_description(directory, routing_name)
    content = _parse_content_files(directory, skip={routing_name})
    return HarnessDirectory(
        name=directory.name,
        routing_file_name=routing_name,
        description=description,
        path=directory,
        children=tuple(children),
        leaves=tuple(leaves),
        content=tuple(content),
    )


def _parse_skill_leaf(directory: Path) -> SkillLeaf:
    """Parse a ``skill`` leaf: ``SKILL.md`` metadata + ``scripts/`` + ``references/``."""
    frontmatter, body = split_frontmatter((directory / SKILL_FILENAME).read_text(encoding="utf-8"))
    return SkillLeaf(
        name=str(frontmatter.get("name", "")),
        description=str(frontmatter.get("description", "")),
        body=body,
        path=directory,
        scripts=_parse_scripts(directory / SCRIPTS_DIRNAME),
        references=_parse_reference_files(directory / REFERENCES_DIRNAME),
    )


def _parse_scripts(scripts_dir: Path) -> tuple[ScriptFile, ...]:
    """Enumerate ``scripts/*`` non-recursively, capturing each file's exec bit."""
    if not scripts_dir.is_dir():
        return ()
    files = sorted(p for p in scripts_dir.iterdir() if p.is_file())
    return tuple(
        ScriptFile(path=path, executable=bool(path.stat().st_mode & 0o111)) for path in files
    )


def _parse_reference_files(references_dir: Path) -> tuple[ContentFile, ...]:
    """Capture a skill's internal ``references/`` as content files (md only)."""
    if not references_dir.is_dir():
        return ()
    return tuple(
        _content_file(path)
        for path in sorted(references_dir.iterdir())
        if path.is_file() and _is_markdown(path)
    )


def _parse_content_files(directory: Path, *, skip: set[str]) -> list[ContentFile | RawAsset]:
    """Classify ``directory``'s own files: markdown → content, others → raw asset.

    ``skip`` excludes the directory's routing file (it is not content).
    """
    items: list[ContentFile | RawAsset] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.name.startswith(".") or path.name in skip:
            continue
        if _is_markdown(path):
            items.append(_content_file(path))
        else:
            items.append(_raw_asset(path))
    return items


def _read_description(path: Path) -> str | None:
    """Read an optional ``description`` from ``path``'s frontmatter (else ``None``).

    Decode/parse failures are swallowed deliberately: a content or routing ``.md``
    may legitimately be plain markdown with no parseable frontmatter, in which case
    there is simply no description to surface.
    """
    try:
        frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    raw = frontmatter.get("description")
    return str(raw) if raw is not None else None


def _content_file(path: Path) -> ContentFile:
    """Build a :class:`ContentFile`, reading an optional ``description`` frontmatter."""
    return ContentFile(
        filename=path.name, description=_read_description(path), path=path, is_markdown=True
    )


def _raw_asset(path: Path) -> RawAsset:
    """Build a :class:`RawAsset`, hashing the file's bytes (never decode)."""
    data = path.read_bytes()
    return RawAsset(path=path, sha256=hashlib.sha256(data).hexdigest())


def _routing_description(directory: Path, routing_name: str) -> str | None:
    """Read the grouping dir's routing-file ``description`` if the file exists."""
    routing_file = directory / routing_name
    if not routing_file.is_file():
        return None
    return _read_description(routing_file)


def _is_markdown(path: Path) -> bool:
    return path.name.endswith(".md") or path.name.endswith(".md.j2")
