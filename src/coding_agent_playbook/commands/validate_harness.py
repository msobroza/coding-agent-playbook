"""``playbook validate-harness <path> [--strict]`` (PR H Track H4).

Runs ``harnesses-ref``-equivalent structural checks on an Agent Harness tree
(emitted by :class:`~coding_agent_playbook.adapters.agent_harness_adapter.AgentHarnessAdapter`
or authored by hand / foreign). This is the lint half of decision #3 in
``specs/prH-agent-harness.md`` §D: the playbook does **not** implement the
client runtime (``load_content`` / ``run_script``) — it validates structure.

Checks (``specs/prH-agent-harness.md`` §A + Track H4):

- **errors** (non-zero exit): ``HARNESS.md`` present with non-empty ``name`` and
  ``description``; every detected skill leaf carries non-empty ``name`` +
  ``description``.
- **warnings** (exit 0 by default; promoted to errors under ``--strict``): a
  grouping (non-leaf) subdirectory lacks its routing file
  (``<DIR>.upper() + ".md"``); a content ``.md`` file lacks a ``description``.

The check reuses :func:`coding_agent_playbook.harness.parser.parse_harness`
rather than re-walking the tree. ``parse_harness`` *raises* on a missing
``HARNESS.md`` (:exc:`NotAHarnessError`) or missing/empty required frontmatter
(:exc:`ValueError`), so both are caught and translated into ERROR reports instead
of crashing. Skill-leaf / routing / content findings are then derived from the
parsed :class:`~coding_agent_playbook.harness.models.Harness` model.

Routing-file presence is not surfaced directly by the model (a parsed
:class:`HarnessDirectory` exposes ``routing_file_name`` but its ``description``
is ``None`` both when the routing file is absent *and* when it exists without a
``description`` — ambiguous). We therefore do a single minimal existence check
per directory using the model's own ``path`` + ``routing_file_name`` — not a
re-walk of the tree.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.harness.models import (
    ContentFile,
    HarnessDirectory,
    LeafMarker,
    NotAHarnessError,
    SkillLeaf,
)
from coding_agent_playbook.harness.parser import parse_harness

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.harness.models import Harness

NAME: Final = "validate-harness"
HELP: Final = "lint an Agent Harness tree (structural checks, harnesses-ref-equivalent)"


@dataclass(frozen=True)
class _Finding:
    """One validation finding, anchored to a path (a string for reporting)."""

    path: str
    message: str


def _is_opaque(directory: HarnessDirectory) -> bool:
    """Whether ``directory`` carries a ``.harnessleaf`` marker FOR ITSELF.

    The parser records a :class:`LeafMarker` at the directory's own ``path`` for a
    directory that carries a ``.harnessleaf`` marker (e.g. a top-level ``evals/``).
    Per spec §A/§B such a directory is an opaque leaf — generic clients stop
    traversing it — so the validator must NEVER expect a routing file for it and
    must NOT inspect its internal content. Mirrors ``import_harness._walk_directory``.
    """
    return any(
        isinstance(leaf, LeafMarker) and leaf.path == directory.path for leaf in directory.leaves
    )


def _check_skill_leaves(directory: HarnessDirectory, errors: list[_Finding]) -> None:
    """Recurse a grouping directory, flagging skill leaves with empty metadata."""
    if _is_opaque(directory):
        return  # opaque .harnessleaf unit: terminal, never inspected (spec §A/§B)
    for leaf in directory.leaves:
        if isinstance(leaf, SkillLeaf):
            if not leaf.name:
                errors.append(_Finding(str(leaf.path), "skill leaf has empty 'name'"))
            if not leaf.description:
                errors.append(_Finding(str(leaf.path), "skill leaf has empty 'description'"))
    for child in directory.children:
        _check_skill_leaves(child, errors)


def _check_routing_and_content(directory: HarnessDirectory, warnings: list[_Finding]) -> None:
    """Recurse a grouping directory, warning on missing routing files / descriptions.

    Routing presence is checked via the model's ``path`` + ``routing_file_name``
    (a minimal supplemental existence check — see module docstring), since the
    parsed model can't disambiguate "absent routing file" from "routing file
    without a description".

    An opaque ``.harnessleaf`` directory is a terminal leaf (spec §A/§B): clients
    stop traversing it, so it must NEVER be expected to carry a routing file and
    its internal content must NOT be inspected. Skip both checks (and recursion)
    for such directories — mirrors ``import_harness._walk_directory``.
    """
    if _is_opaque(directory):
        return
    routing_file = directory.path / directory.routing_file_name
    if not routing_file.is_file():
        warnings.append(
            _Finding(
                str(directory.path),
                f"grouping directory lacks its routing file {directory.routing_file_name!r}",
            )
        )
    for item in directory.content:
        if isinstance(item, ContentFile) and not item.description:
            warnings.append(_Finding(str(item.path), "content '.md' lacks a 'description'"))
    for child in directory.children:
        _check_routing_and_content(child, warnings)


def _collect_findings(harness: Harness) -> tuple[list[_Finding], list[_Finding]]:
    """Derive (errors, warnings) from a successfully parsed :class:`Harness`.

    The root's own ``name``/``description`` are already validated by
    :func:`parse_harness` (it raises when either is empty), so only the per-branch
    skill-leaf / routing / content checks remain here.
    """
    errors: list[_Finding] = []
    warnings: list[_Finding] = []
    for directory in harness.directories:
        _check_skill_leaves(directory, errors)
        _check_routing_and_content(directory, warnings)
    return errors, warnings


def _report(errors: list[_Finding], warnings: list[_Finding], *, strict: bool) -> int:
    """Print findings + a summary line; return the process exit code.

    Errors print to stdout (the primary report); warnings print to stderr so they
    can be filtered independently. ``--strict`` promotes warnings to failures.
    """
    for err in errors:
        print(f"ERROR {err.path}: {err.message}")
    for warn in warnings:
        print(f"warning: {warn.path}: {warn.message}", file=sys.stderr)

    failed = bool(errors) or (strict and bool(warnings))
    if failed:
        promoted = " (warnings promoted by --strict)" if strict and warnings and not errors else ""
        print(
            f"validation failed with {len(errors)} error(s), {len(warnings)} warning(s){promoted}"
        )
        return 1
    print(f"OK harness validated ({len(warnings)} warning(s))")
    return 0


def configure(parser: argparse.ArgumentParser) -> None:
    """Declare ``playbook validate-harness [PATH] [--strict]`` (SPEC §12.10).

    Example::

        >>> configure(argparse.ArgumentParser(prog="playbook validate-harness"))  # doctest: +SKIP
    """
    parser.add_argument("path", nargs="?", help="path to the harness root (contains HARNESS.md)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="promote warnings (missing routing file / content description) to errors",
    )


def run(args: argparse.Namespace) -> int:
    """``playbook validate-harness <path> [--strict]`` (SPEC §12)."""
    raw_path = getattr(args, "path", None)
    if not raw_path:
        print("error: validate-harness requires a harness path", file=sys.stderr)
        return 2
    root = Path(raw_path)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    strict = bool(getattr(args, "strict", False))

    try:
        harness = parse_harness(root)
    except (NotAHarnessError, ValueError) as exc:
        # parse_harness raises NotAHarnessError when HARNESS.md is absent and
        # ValueError when its required name/description frontmatter is empty.
        # Translate both into ERROR reports instead of crashing.
        #
        # DELIBERATE exit-code choice: validate-harness reports an invalid/missing
        # HARNESS.md as a validation ERROR (rc 1), NOT a usage error (rc 2). This
        # intentionally differs from import-harness, which treats the same
        # condition as a usage error (rc 2). Do not "fix" this to rc 2 to match —
        # for a validator a malformed harness is precisely the failure it exists
        # to report.
        print(f"ERROR {root}: {exc}")
        print("validation failed with 1 error(s), 0 warning(s)")
        return 1

    errors, warnings = _collect_findings(harness)
    return _report(errors, warnings, strict=strict)
