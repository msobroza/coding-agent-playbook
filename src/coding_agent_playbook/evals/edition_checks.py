"""The offline edition checks: pins, editions and their digests agree (#281 ticket 09, ADR 0012).

A pin freezes a whole experiment: the edition's text, the sample (``sample.toml``
and ``setup/``) and the prompt text the sample renders. :func:`edition_problems`
reports, for one catalog, every way that freeze has broken:

- a core sample pins an edition that does not exist under ``editions/``;
- an edition no core sample pins (editions exist only while a pin needs them);
- an edition whose files differ from its digests file, or whose digests file
  names another tag or records no pin for a sample that pins it;
- a pinned sample that no longer renders to its recorded prompt digest (an
  engine or renderer change) or whose sample digest moved (an edited sample).

CI runs it over the shipped catalog (``tests/catalog/test_editions_catalog.py``),
so such a change fails until the sample is unfrozen and frozen again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE
from coding_agent_playbook.evals.prompting import PromptResolutionError
from coding_agent_playbook.evals.sample_digest import rendered_prompt_digest, sample_digest
from coding_agent_playbook.evals.task_registry import EVAL_SAMPLES_DIR, collect_layer_samples
from coding_agent_playbook.release.edition import EditionError, edition_file_problems, load_edition
from coding_agent_playbook.release.edition_digests import EDITIONS_DIRNAME, edition_dir

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.release.edition import Edition

__all__ = ["edition_problems"]

_CORE_DIRNAME = "core"
_FIX = "unfreeze and freeze the sample again"


def edition_problems(catalog_dir: Path) -> list[str]:
    """Every problem with the editions and pins of ``catalog_dir``; ``[]`` when all agree.

    Example::

        >>> edition_problems(Path("catalog"))  # doctest: +SKIP
        []
    """
    samples, errors = collect_layer_samples(
        catalog_dir / _CORE_DIRNAME / EVAL_SAMPLES_DIR, ENGINE_PACKAGE
    )
    problems = [str(error) for error in errors]
    pinned = [sample for sample in samples if sample.edition is not None]
    for root in _edition_dirs(catalog_dir):
        problems += _edition_dir_problems(root, pinned)
    for sample in pinned:
        problems += _pin_problems(catalog_dir, sample)
    return problems


def _edition_dirs(catalog_dir: Path) -> list[Path]:
    editions = catalog_dir / EDITIONS_DIRNAME
    if not editions.is_dir():
        return []
    return sorted(entry for entry in editions.iterdir() if entry.is_dir())


def _edition_dir_problems(root: Path, pinned: list[EvalSample]) -> list[str]:
    """The edition at ``root``: pinned by a sample, its files and tag as its digests file says."""
    tag = root.name
    problems: list[str] = []
    if not any(sample.edition == tag for sample in pinned):
        problems.append(f"{root}: edition {tag} exists but no eval sample pins it; unfreeze it")
    problems += edition_file_problems(root)
    try:
        edition = load_edition(root)
    except EditionError as exc:
        return [*problems, str(exc)]
    if edition.tag != tag:
        problems.append(f"{root}: its digests file names tag {edition.tag}, not {tag}")
    return problems


def _pin_problems(catalog_dir: Path, sample: EvalSample) -> list[str]:
    """``sample``'s pin: its edition exists, records it, and both digests still hold."""
    tag = str(sample.edition)
    root = edition_dir(catalog_dir, tag)
    where = f"{sample.source_path}: sample {sample.id!r} pins edition {tag}"
    if not root.is_dir():
        return [f"{where}, which does not exist under {root.parent}; freeze it or drop the pin"]
    try:
        edition = load_edition(root)
    except EditionError:
        return []  # reported once, for the edition directory
    pin = edition.digests.pin(sample.id)
    if pin is None:
        return [f"{where}, but the edition records no pin for it; {_FIX}"]
    problems: list[str] = []
    if sample_digest(sample) != pin.sample_digest:
        problems.append(f"{where}: its sample digest moved (sample.toml or setup/); {_FIX}")
    rendered = _rendered(sample, edition)
    if rendered != pin.rendered_prompt_digest:
        problems.append(
            f"{where}: its rendered prompt changed (an engine or renderer change), "
            f"{rendered} != recorded {pin.rendered_prompt_digest}; {_FIX}"
        )
    return problems


def _rendered(sample: EvalSample, edition: Edition) -> str:
    try:
        return rendered_prompt_digest(sample, edition)
    except PromptResolutionError as exc:
        return f"<unrenderable: {exc}>"
