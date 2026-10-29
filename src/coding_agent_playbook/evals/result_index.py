"""The result index: every committed release metrics file a record may carry from (spec D1).

``playbook eval --record`` reuses any committed result, not only the previous
release's file of the same target (ADR 0013 carried from that one file).
:meth:`ReleaseIndex.load` reads ``<root>/*/metrics/*.json`` and skips, naming
the reason, each file that cannot be read, fails the schema, records no setup
digest, or names a release that is not a version. :meth:`ReleaseIndex.plan`
keeps the files whose setup matches this run's
(``evals.setup_digest.setups_match``) and indexes their entries that record an
inputs digest; an entry without one is never carried. Each sample carries the
first entry at its inputs digest, newest release first and, within a release,
the target's own file before the others by name. Nothing here runs an agent or
decides a score.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from packaging.version import InvalidVersion, Version

from coding_agent_playbook.evals.release_carry import CarryPlan, carried_entry
from coding_agent_playbook.evals.release_metrics_schema import (
    INPUTS_DIGEST_KEY,
    SETUP_DIGEST_KEY,
    SETUP_KEY,
    ReleaseMetricsError,
    validate_release_metrics,
)
from coding_agent_playbook.evals.setup_digest import differing_setup_parts, setups_match

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from pathlib import Path

_NEW_SAMPLE: Final = "new sample (in no committed release with this setup)"
_INPUTS_CHANGED: Final = "inputs digest changed"
_NO_USABLE_FILE: Final = "no committed release metrics file matches this setup"
#: How many skipped files the full-rerun reason names before counting the rest.
_SKIPS_NAMED: Final = 3


@dataclass(frozen=True)
class IndexedFile:
    """One validated release metrics file at ``path``, for ``target`` in ``release``.

    Example::

        >>> IndexedFile(Path("0.3.0/metrics/opus.json"), "0.3.0", "opus", {}).label
        '0.3.0 (opus)'
    """

    path: Path
    release: str
    target: str
    data: Mapping[str, Any]

    @property
    def label(self) -> str:
        """The file as a carry plan names its source: ``"<release> (<target>)"``."""
        return f"{self.release} ({self.target})"


@dataclass(frozen=True)
class ReleaseIndex:
    """The usable release metrics ``files``, newest release first, and the ``skipped`` ones.

    Each ``skipped`` line is ``"<path>: <reason>"``.

    Example::

        >>> ReleaseIndex.load(Path("catalog/releases")).plan(  # doctest: +SKIP
        ...     target_name="opus", setup=parts.as_dict(), inputs={"review/x": "ab12"}
        ... ).sources
        {'review/x': '0.4.0 (opus)'}
    """

    files: tuple[IndexedFile, ...]
    skipped: tuple[str, ...]

    @classmethod
    def load(cls, root: Path, *, exclude: Path | None = None) -> ReleaseIndex:
        """Index ``root/*/metrics/*.json``, leaving out ``exclude`` (the record's own output).

        Example::

            >>> ReleaseIndex.load(Path("catalog/releases"), exclude=out).skipped  # doctest: +SKIP
            ()
        """
        excluded = exclude.resolve() if exclude is not None else None
        files: list[IndexedFile] = []
        skipped: list[str] = []
        for path in sorted(root.glob("*/metrics/*.json")):
            if path.resolve() == excluded:
                continue
            indexed = _read(path)
            if isinstance(indexed, str):
                skipped.append(f"{path}: {indexed}")
                continue
            files.append(indexed)
        files.sort(key=lambda indexed: Version(indexed.release), reverse=True)
        return cls(tuple(files), tuple(skipped))

    def plan(
        self, *, target_name: str, setup: Mapping[str, object], inputs: Mapping[str, str]
    ) -> CarryPlan:
        """Which of ``inputs`` (sample id to inputs digest) rerun, and where the rest come from.

        ``setup`` is this run's setup parts (``SetupParts.as_dict``). With no
        file of this setup every sample reruns, and the reason names the first
        skipped files.

        Example::

            >>> index.plan(target_name="opus", setup=setup, inputs={"t/a": "d"}).rerun  # doctest: +SKIP
            {}
        """
        usable = [indexed for indexed in self.files if setups_match(indexed.data[SETUP_KEY], setup)]
        if not usable:
            reason = _no_usable_reason([*self.skipped, *self._setup_skips(setup)])
            return CarryPlan(reason, dict.fromkeys(sorted(inputs), reason), {})
        return _carry_plan(_in_priority(usable, target_name), inputs)

    def _setup_skips(self, setup: Mapping[str, object]) -> list[str]:
        """``"<path>: <reason>"`` for each indexed file whose setup differs from ``setup``."""
        return [
            f"{indexed.path}: the setup differs in "
            + ", ".join(differing_setup_parts(indexed.data[SETUP_KEY], setup))
            for indexed in self.files
        ]


def _read(path: Path) -> IndexedFile | str:
    """The file at ``path`` indexed, or why it is skipped."""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
        validate_release_metrics(data)
    except (OSError, ValueError) as exc:
        return f"cannot read the file: {exc}"
    except ReleaseMetricsError as exc:
        return str(exc)
    reason = _unusable_reason(data)
    if reason is not None:
        return reason
    return IndexedFile(path, data["release"], data["target"]["name"], data)


def _unusable_reason(data: Mapping[str, Any]) -> str | None:
    """Why a valid file cannot be carried from; ``None`` when it can."""
    if SETUP_DIGEST_KEY not in data or SETUP_KEY not in data:
        return "records no setup digest"
    try:
        Version(data["release"])
    except InvalidVersion:
        return f"release {data['release']!r} is not a version"
    return None


def _no_usable_reason(skips: Sequence[str]) -> str:
    """The full-rerun reason: the first :data:`_SKIPS_NAMED` skips, then how many more."""
    if not skips:
        return _NO_USABLE_FILE
    named = "; ".join(skips[:_SKIPS_NAMED])
    rest = len(skips) - _SKIPS_NAMED
    return f"{_NO_USABLE_FILE}: {named}" + (f"; and {rest} more" if rest > 0 else "")


def _in_priority(files: Sequence[IndexedFile], target_name: str) -> list[IndexedFile]:
    """``files`` newest release first; within a release, ``target_name``'s own file first."""
    by_target = sorted(files, key=lambda indexed: (indexed.target != target_name, indexed.target))
    return sorted(by_target, key=lambda indexed: Version(indexed.release), reverse=True)


def _carry_plan(ordered: Sequence[IndexedFile], inputs: Mapping[str, str]) -> CarryPlan:
    """Each sample carried from the first file in ``ordered`` holding it at its inputs digest."""
    rerun: dict[str, str] = {}
    carried: dict[str, Mapping[str, object]] = {}
    sources: dict[str, IndexedFile] = {}
    for sample_id, digest in sorted(inputs.items()):
        source = _source(ordered, sample_id, digest)
        if isinstance(source, str):
            rerun[sample_id] = source
            continue
        entry = source.data["samples"][sample_id]
        carried[sample_id] = carried_entry(
            entry, release=source.release, commit=source.data["commit"], target=source.target
        )
        sources[sample_id] = source
    labels = {sample_id: source.label for sample_id, source in sources.items()}
    return CarryPlan(None, rerun, carried, _reported_model(ordered, sources.values()), labels)


def _source(ordered: Sequence[IndexedFile], sample_id: str, digest: str) -> IndexedFile | str:
    """The first file holding ``sample_id`` at ``digest``, or why the sample reruns."""
    holders = [indexed for indexed in ordered if _inputs_digest(indexed, sample_id) is not None]
    for indexed in holders:
        if _inputs_digest(indexed, sample_id) == digest:
            return indexed
    return _INPUTS_CHANGED if holders else _NEW_SAMPLE


def _inputs_digest(indexed: IndexedFile, sample_id: str) -> str | None:
    """The inputs digest ``indexed`` records for ``sample_id``; ``None`` when it holds none.

    An entry written before inputs digests existed is not indexed (spec D1), so
    it never carries and never makes a sample's reason "inputs digest changed".
    """
    entry: Mapping[str, Any] = indexed.data["samples"].get(sample_id, {})
    digest: str | None = entry.get(INPUTS_DIGEST_KEY)
    return digest


def _reported_model(ordered: Sequence[IndexedFile], used: Iterable[IndexedFile]) -> str | None:
    """The reported model of the newest file in ``ordered`` that a carried entry came from."""
    used_paths = {indexed.path for indexed in used}
    for indexed in ordered:
        if indexed.path in used_paths:
            reported: str | None = indexed.data["target"]["reported_model"]
            return reported
    return None
