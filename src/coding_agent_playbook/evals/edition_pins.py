"""Pin the graded core samples to an edition, or unpin them (#281 ticket 13, ADR 0012).

``scripts/release.py freeze vX`` writes the edition's files first
(``release.edition_freeze``), then :func:`pin_graded_samples` sets
``edition = "vX"`` in every core sample whose prompt the tag graded (found
through the task registry, ``evals.task_registry``) and returns each pin's
digests, computed by the engine's own functions (``evals.sample_digest``) after
the line is written, so the sample digest covers it. ``unfreeze`` calls
:func:`unpin_samples`.

The ``edition`` line is edited as text, so comments and layout survive; each
edit is checked by parsing the file before and after, and an edit that would
change any other key refuses instead of writing.
"""

from __future__ import annotations

import re
import tomllib
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE
from coding_agent_playbook.evals.sample_digest import rendered_prompt_digest, sample_digest
from coding_agent_playbook.evals.task_registry import (
    EVAL_SAMPLES_DIR,
    TaskRegistry,
    load_layer_samples,
    load_task_sample,
)
from coding_agent_playbook.release.edition import load_edition
from coding_agent_playbook.release.edition_digests import PinDigests, edition_dir

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.release.edition import Edition

__all__ = [
    "EditionPinError",
    "pin_graded_samples",
    "unpin_samples",
    "with_edition_line",
    "without_edition_line",
]

_EDITION_KEY: Final = "edition"
_EDITION_LINE: Final = re.compile(r"(?m)^edition[ \t]*=.*(?:\r?\n|$)")
_TABLE_HEADER: Final = re.compile(r"[ \t]*\[")
_CORE_DIRNAME: Final = "core"


class EditionPinError(ValueError):
    """A sample that cannot be pinned or unpinned; the message names it and what to do."""


def pin_graded_samples(
    catalog_dir: Path, tag: str, prompt_ids: Iterable[str]
) -> tuple[PinDigests, ...]:
    """Pin every core sample of ``prompt_ids``'s tasks to edition ``tag``; returns their pins.

    The edition's files and digests file must already be written. Refuses
    (:class:`EditionPinError`) when no sample grades those prompts or one is
    pinned to another edition; nothing is written then.

    Example::

        >>> pin_graded_samples(Path("catalog"), "v0.1.0", ["review"])  # doctest: +SKIP
        (PinDigests(sample='review/spot-the-bug', ...), ...)
    """
    wanted = sorted(set(prompt_ids))
    graded = _graded_samples(_core_samples(catalog_dir), wanted)
    if not graded:
        raise EditionPinError(f"no core eval sample grades {wanted}: edition {tag} pins nothing")
    elsewhere = [f"{s.id} ({s.edition})" for s in graded if s.edition not in (None, tag)]
    if elsewhere:
        raise EditionPinError(
            f"samples pinned to another edition: {elsewhere}; unfreeze it before freezing {tag}"
        )
    _rewrite_all([s.source_path for s in graded], lambda text: with_edition_line(text, tag))
    edition = load_edition(edition_dir(catalog_dir, tag))
    return tuple(_pin(sample.source_path.parent, edition) for sample in graded)


def unpin_samples(catalog_dir: Path, tag: str) -> list[str]:
    """Drop the ``edition`` line of every core sample pinned to ``tag``; returns their ids.

    Example::

        >>> unpin_samples(Path("catalog"), "v0.1.0")  # doctest: +SKIP
        ['review/spot-the-bug', ...]
    """
    pinned = [s for s in _core_samples(catalog_dir) if s.edition == tag]
    _rewrite_all([s.source_path for s in pinned], without_edition_line)
    return sorted(sample.id for sample in pinned)


def _core_samples(catalog_dir: Path) -> list[EvalSample]:
    root = catalog_dir / _CORE_DIRNAME / EVAL_SAMPLES_DIR
    return load_layer_samples(root, ENGINE_PACKAGE)


def _graded_samples(samples: list[EvalSample], prompt_ids: list[str]) -> list[EvalSample]:
    """The samples of the tasks ``prompt_ids`` names, in task then sample order."""
    registry = TaskRegistry.build(samples, {sample.prompt_id for sample in samples})
    tasks = {task.prompt_id: task.samples for task in registry.tasks()}
    return [sample for prompt_id in prompt_ids for sample in tasks.get(prompt_id, ())]


def _pin(sample_dir: Path, edition: Edition) -> PinDigests:
    """The digests of the sample at ``sample_dir``, reloaded so its ``edition`` line counts."""
    sample = load_task_sample(sample_dir, source_package=ENGINE_PACKAGE)
    return PinDigests(sample.id, rendered_prompt_digest(sample, edition), sample_digest(sample))


def _rewrite_all(paths: list[Path], edit: Callable[[str], str]) -> None:
    """Apply ``edit`` to every file, writing none unless all of them can be edited."""
    edited = [(path, _edited(path, edit)) for path in paths]
    for path, new in edited:
        if new is not None:
            path.write_bytes(new.encode("utf-8"))


def _edited(path: Path, edit: Callable[[str], str]) -> str | None:
    """``path``'s new text, ``None`` when the edit leaves it as it is."""
    text = path.read_bytes().decode("utf-8")
    try:
        new = edit(text)
    except EditionPinError as exc:
        raise EditionPinError(f"{path}: {exc}") from exc
    return None if new == text else new


# --------------------------------------------------------------------------- #
# The edition line of one sample.toml
# --------------------------------------------------------------------------- #


def with_edition_line(text: str, tag: str) -> str:
    """``text`` (a ``sample.toml``) with ``edition = "<tag>"`` among its top-level keys.

    An existing ``edition`` line is replaced; otherwise the line goes after the
    last top-level key, before the first table.

    Example::

        >>> with_edition_line('id = "review/x"\\n\\n[gate]\\n', "v9.9.9")
        'id = "review/x"\\nedition = "v9.9.9"\\n\\n[gate]\\n'
    """
    line = f'{_EDITION_KEY} = "{tag}"\n'
    if _EDITION_LINE.search(text):
        new = _EDITION_LINE.sub(line, text, count=1)
    else:
        lines = text.splitlines(keepends=True)
        at = next((i for i, row in enumerate(lines) if _TABLE_HEADER.match(row)), len(lines))
        while at > 0 and _blank_or_comment(lines[at - 1]):
            at -= 1
        if at > 0 and not lines[at - 1].endswith("\n"):
            lines[at - 1] += "\n"
        lines.insert(at, line)
        new = "".join(lines)
    _check_only_edition_changed(text, new, tag)
    return new


def without_edition_line(text: str) -> str:
    """``text`` without its top-level ``edition`` line.

    Example::

        >>> without_edition_line('id = "review/x"\\nedition = "v9.9.9"\\n')
        'id = "review/x"\\n'
    """
    new = _EDITION_LINE.sub("", text, count=1)
    _check_only_edition_changed(text, new, None)
    return new


def _blank_or_comment(row: str) -> bool:
    stripped = row.strip()
    return not stripped or stripped.startswith("#")


def _check_only_edition_changed(old: str, new: str, tag: str | None) -> None:
    before = {k: v for k, v in _parse(old).items() if k != _EDITION_KEY}
    expected: dict[str, Any] = before if tag is None else {**before, _EDITION_KEY: tag}
    if _parse(new) != expected:
        want = "drop" if tag is None else f'set edition = "{tag}" in'
        raise EditionPinError(
            f"cannot {want} this sample.toml without changing its other keys; edit by hand"
        )


def _parse(text: str) -> dict[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise EditionPinError(f"not valid TOML after the edit: {exc}") from exc
