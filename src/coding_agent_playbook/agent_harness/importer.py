"""The Agent Harness importer behind ``playbook import-harness`` (PR H Track H3).

Parses an Agent Harness tree back into canonical ``Rule`` / ``Prompt`` / ``Skill``
(and, from the sidecar, ``Hook``) artifacts and writes them into an overlay
directory (default ``playbook/``) in the
:class:`~coding_agent_playbook.catalog.source.FileSystemArtifactSource` layout,
so a later ``playbook sync`` can re-read them.

Two fidelity tiers (``specs/prH-agent-harness.md`` §C):

- **Lossless** (:mod:`._lossless`) — when a ``.playbook/manifest.toml`` sidecar is
  present, every non-native field (rule ``scope``/``globs``/..., prompt
  ``includes_rules``/..., skill ``extra_frontmatter`` + per-script ``executable``
  bit) is rebuilt from the manifest, keyed by each artifact's harness-relative
  path. Script exec bits are restored on POSIX (no-op on Windows).
- **Best-effort** (:mod:`._best_effort`) — no sidecar (a foreign harness): kinds
  are inferred from directory placement, non-native fields are defaulted, and
  every lossy assumption is collected as a warning that the command reports to
  stderr — the importer never silently guesses.

The parsing/reconstruction core (:func:`import_harness` -> :class:`ImportResult`)
is kept separate from file writing (:func:`write_import`, through
:mod:`._import_writes`) so callers and the round-trip tests can assert on the
reconstructed objects directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.agent_harness._best_effort import read_best_effort
from coding_agent_playbook.agent_harness._import_writes import (
    write_hook,
    write_prompt,
    write_raw_asset,
    write_rule,
    write_skill,
)
from coding_agent_playbook.agent_harness._lossless import read_lossless
from coding_agent_playbook.agent_harness.manifest import read_manifest
from coding_agent_playbook.agent_harness.models import NotAHarnessError
from coding_agent_playbook.skills.naming import skill_id_of

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill

#: Source-package marker recorded on every imported artifact.
IMPORTED_SOURCE_PACKAGE: Final = "<imported>"


@dataclass
class ImportResult:
    """Reconstructed canonical artifacts plus any lossiness warnings.

    ``raw_assets`` are non-markdown passthrough files (a foreign harness may
    ship binaries with no canonical home); they are written verbatim but cannot
    be re-read as canonical artifacts.
    """

    rules: list[Rule] = field(default_factory=list)
    prompts: list[Prompt] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    hooks: list[Hook] = field(default_factory=list)
    raw_assets: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def import_harness(harness_root: Path) -> ImportResult:
    """Parse the tree into canonical artifacts (lossless with the sidecar manifest); writes nothing.

    Uses the ``.playbook/manifest.toml`` sidecar for lossless reconstruction when
    present, else falls back to best-effort structural inference (surfacing the
    lossiness as warnings).

    Raises:
        NotAHarnessError: when ``harness_root`` has no ``HARNESS.md``.

    Example: ``result = import_harness(Path("vendor/some-harness"))``.
    """
    if not (harness_root / "HARNESS.md").is_file():
        raise NotAHarnessError(f"no HARNESS.md at {harness_root}")
    result = ImportResult()
    manifest = read_manifest(harness_root)
    if manifest is None:
        read_best_effort(harness_root, result, source_package=IMPORTED_SOURCE_PACKAGE)
    else:
        read_lossless(harness_root, manifest, result, source_package=IMPORTED_SOURCE_PACKAGE)
    return result


def write_import(result: ImportResult, into: Path) -> None:
    """Write rules, prompts, skills, hooks and raw assets under ``into`` (was ``_write_result``).

    A member rule whose skill is imported alongside lands in that skill's
    ``rules/`` (prU D22); see :func:`~._import_writes.write_rule`.

    Example: ``write_import(import_harness(harness_root), Path("playbook"))``.
    """
    skill_ids = {skill_id_of(skill) for skill in result.skills}
    for rule in result.rules:
        write_rule(rule, into, skill_ids=skill_ids)
    for prompt in result.prompts:
        write_prompt(prompt, into)
    for skill in result.skills:
        write_skill(skill, into)
    for hook in result.hooks:
        write_hook(hook, into)
    for asset in result.raw_assets:
        write_raw_asset(asset, into)
