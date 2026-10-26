"""What one eval run grades: a pinned sample's frozen edition, or the current text (#281 ticket 09).

A core sample with ``edition = "vX"`` (its pin, CONTEXT.md) grades the frozen
copy of the graded set in ``catalog/editions/vX/``, so its score stays
comparable while authors improve the current text. :func:`graded_source` picks
the source of one run; ``playbook eval --edition head`` passes ``head=True`` to
grade the current text instead. :func:`graded_record` is what a report records
about it: the source (the edition tag or ``head``), the graded prompt's digest,
the sample digest and the engine version.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import coding_agent_playbook
from coding_agent_playbook.catalog.prompt_sets import DEFAULT_PROMPT_SET
from coding_agent_playbook.evals.release_metrics import GRADED_HEAD
from coding_agent_playbook.evals.sample_digest import prompt_digest, sample_digest
from coding_agent_playbook.evals.task_registry import sample_layer_root
from coding_agent_playbook.release.edition import EditionError, load_edition
from coding_agent_playbook.release.edition_digests import edition_dir

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.catalog.prompt_sets import PromptSet
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.release.edition import Edition

__all__ = ["GradedRecord", "GradedSource", "graded_record", "graded_source", "sample_edition_dir"]


@dataclass(frozen=True)
class GradedSource:
    """The text one run grades: ``edition`` when the sample's pin applies, else the current text.

    Example::

        >>> GradedSource(None).label
        'head'
    """

    edition: Edition | None

    @property
    def label(self) -> str:
        """The edition's tag, or ``head`` for the current text."""
        return self.edition.tag if self.edition is not None else GRADED_HEAD

    @property
    def note(self) -> str:
        """The phrase a result line ends with, saying what was graded.

        Example::

            >>> GradedSource(None).note
            'graded head'
        """
        if self.edition is None:
            return f"graded {GRADED_HEAD}"
        return f"graded edition {self.edition.tag} (frozen; overrides ignored)"


@dataclass(frozen=True)
class GradedRecord:
    """What a report records about the graded text.

    ``source`` is an edition tag or ``head``; ``prompt_digest`` the graded
    prompt's ``artifact_digest`` (``None`` when the sample resolves to no
    prompt); ``sample_digest`` covers ``sample.toml`` and ``setup/``.

    Example::

        >>> GradedRecord("head", None, "ab", "9.9.9", "graded head").as_dict()["source"]
        'head'
    """

    source: str
    prompt_digest: str | None
    sample_digest: str
    engine_version: str
    note: str

    def as_dict(self) -> dict[str, object]:
        """The record's JSON view (the ``note`` is text-report only)."""
        return {
            "source": self.source,
            "prompt_digest": self.prompt_digest,
            "sample_digest": self.sample_digest,
            "engine_version": self.engine_version,
        }


def sample_edition_dir(sample: EvalSample, tag: str) -> Path:
    """Where edition ``tag`` lives for ``sample``: ``editions/<tag>`` beside its layer.

    A core sample sits at ``<catalog>/core/eval_samples/<prompt>/<name>/``, so its
    editions are under ``<catalog>/editions/`` (checkout and wheel alike).

    Example::

        >>> sample_edition_dir(sample, "v0.1.0")  # doctest: +SKIP
        PosixPath('catalog/editions/v0.1.0')
    """
    layer = sample_layer_root(sample.source_path)
    if layer is None:
        raise EditionError(
            f"sample {sample.id!r} pins edition {tag} but lies outside a layer's "
            f"eval_samples/<prompt>/<name>/ ({sample.source_path})"
        )
    return edition_dir(layer.parent, tag)


def graded_source(sample: EvalSample, *, head: bool = False) -> GradedSource:
    """The text ``sample`` grades: its pinned edition, or the current text when unpinned or ``head``.

    Raises :class:`EditionError` when the pinned edition cannot be loaded.

    Example::

        >>> graded_source(unpinned_sample).label  # doctest: +SKIP
        'head'
    """
    if head or sample.edition is None:
        return GradedSource(None)
    return GradedSource(load_edition(sample_edition_dir(sample, sample.edition)))


def graded_record(
    sample: EvalSample, source: GradedSource, prompt_set: PromptSet = DEFAULT_PROMPT_SET
) -> GradedRecord:
    """The record of ``sample`` graded on ``source`` (``prompt_set`` applies to head only).

    Example::

        >>> graded_record(sample, graded_source(sample)).source  # doctest: +SKIP
        'v0.1.0'
    """
    return GradedRecord(
        source=source.label,
        prompt_digest=prompt_digest(sample, prompt_set, edition=source.edition),
        sample_digest=sample_digest(sample),
        engine_version=coding_agent_playbook.__version__,
        note=source.note,
    )
