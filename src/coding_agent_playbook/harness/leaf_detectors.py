"""Leaf detection for Agent Harness trees (Track H1).

A harness root may ship a ``.leaf-detectors`` file declaring a *leaf vocabulary*:
one ``leaf_type=relative_path`` rule per line. A directory containing a leaf
type's primary file is a *leaf* — a terminal unit the client stops traversing.
A ``.harnessleaf`` marker file forces any directory to become an opaque leaf of
type ``"leaf"`` and takes precedence over every detector.

Routing-file names derive from the **top-level** ancestor segment of a branch
and propagate through the whole subtree (everything under ``tools/`` routes to
``TOOLS.md``, even ``tools/db/relational/``). See ``specs/prH-agent-harness.md``
§A/§B and the harness spec's loading phases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

#: Presence-marker filename that forces a directory to be an opaque leaf.
HARNESS_LEAF_MARKER = ".harnessleaf"

#: Leaf type assigned to any directory carrying :data:`HARNESS_LEAF_MARKER`.
LEAF_TYPE_OPAQUE = "leaf"


def parse_leaf_detectors(text: str) -> dict[str, str]:
    """Parse a ``.leaf-detectors`` file body into a ``{leaf_type: relative_path}`` map.

    Blank lines and ``#`` comment lines are skipped. Each remaining line is
    split on its **first** ``=`` only (so an ``=`` inside the path is preserved),
    and both sides are stripped. Lines without an ``=`` are ignored.
    """
    detectors: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        detectors[key.strip()] = value.strip()
    return detectors


def routing_file_name(top_level_segment: str) -> str:
    """Return the routing-file name for a branch rooted at ``top_level_segment``.

    The name is the uppercased top-level segment plus ``.md`` (``skills`` →
    ``SKILLS.md``). Callers must pass the **top-level ancestor** segment for the
    whole subtree, not the immediate directory name — the name propagates down.
    """
    return top_level_segment.upper() + ".md"


def is_harness_leaf(directory: Path) -> bool:
    """Return whether ``directory`` carries a ``.harnessleaf`` marker file."""
    return (directory / HARNESS_LEAF_MARKER).is_file()


def leaf_type(directory: Path, detectors: dict[str, str]) -> str | None:
    """Classify ``directory`` against the leaf vocabulary.

    Returns:
        - :data:`LEAF_TYPE_OPAQUE` (``"leaf"``) if a ``.harnessleaf`` marker is
          present — this **takes precedence** over every detector;
        - otherwise the first detector ``leaf_type`` whose ``relative_path``
          exists inside ``directory``;
        - otherwise ``None`` (a grouping directory the client should recurse).
    """
    if is_harness_leaf(directory):
        return LEAF_TYPE_OPAQUE
    for detector_type, relative_path in detectors.items():
        if (directory / relative_path).is_file():
            return detector_type
    return None
