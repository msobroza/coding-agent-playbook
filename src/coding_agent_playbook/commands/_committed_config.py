"""Rewrite ``.coding-agent-playbook.toml`` from itself alone (SPEC §7.2).

Shared by ``playbook init`` and ``playbook check --refresh``. Both update the
*committed* config, never the effective one ``FileSystemStateSource.load_config``
returns: that one has the gitignored ``.coding-agent-playbook.local.toml`` merged
in, so saving it commits one engineer's personal overrides for the whole team,
and the round trip through ``Config`` alone drops the committed tables it does
not manage (``[links]``, ``[metrics]``). Before v0.18 both commands did both.

Every :class:`ConfigRewrite` is built here, by a ``plan_*`` function that reads
the committed file itself or requires that there is none, and
:meth:`ConfigRewrite.save` is the committed file's only production writer
(pinned by ``tests/unit/test_committed_config.py``).
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.config import Config
from coding_agent_playbook.config_entries import unmanaged_config_entries, with_unmanaged_entries
from coding_agent_playbook.sources.filesystem import FileSystemStateSource

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.detector import Facts

_COMMITTED = FileSystemStateSource._CONFIG_FILENAME


@dataclasses.dataclass(frozen=True)
class ConfigRewrite:
    """A checked rewrite of the committed config: the exact table to write, and its ``Config``.

    Built only by :func:`plan_first_config`, :func:`plan_committed_update` and
    :func:`plan_detector_cache_refresh`, each of which has already checked that
    ``table``, with the local file merged on top, loads.
    """

    config: Config
    table: dict[str, Any]

    def save(self, state: FileSystemStateSource) -> Config:
        """Write ``table`` to the committed file; return its ``Config``.

        Example::

            >>> plan_detector_cache_refresh(state, {}).save(state)  # doctest: +SKIP
        """
        state.save_config_table(self.table)
        return self.config


def _checked_rewrite(
    state: FileSystemStateSource, config: Config, table: dict[str, Any]
) -> ConfigRewrite:
    """``ConfigRewrite(config, table)``, once ``table`` is known to load with the local file.

    ``state.preview_config`` merges the local file over ``table`` and runs the
    result through ``Config.from_dict``, so a ``ConfigError`` (exit 2) surfaces
    here, before anything is written, and not from the next command.
    """
    state.preview_config(table)
    return ConfigRewrite(config, table)


def plan_first_config(state: FileSystemStateSource, config: Config) -> ConfigRewrite:
    """The checked rewrite that creates the committed file from ``config`` (a first ``init``).

    Refuses with ``FileExistsError`` when the file exists: an existing file is
    rewritten only from itself (:func:`plan_committed_update`), never from a
    ``Config`` built elsewhere — such as ``load_config``'s merge with the local file.

    Example::

        >>> plan_first_config(state, config).table == config.to_dict()  # doctest: +SKIP
        True
    """
    if state.has_committed_config():
        raise FileExistsError(
            f"{_COMMITTED} exists; rewrite it with plan_committed_update, "
            "which starts from the file itself"
        )
    return _checked_rewrite(state, config, config.to_dict())


def plan_committed_update(
    state: FileSystemStateSource, update: Callable[[Config], Config]
) -> ConfigRewrite:
    """The checked rewrite of the committed file with ``update`` applied to its ``Config``.

    Reads the committed file alone (``read_committed_config_table``; the local
    file is never merged in), hands its ``Config`` to ``update``, writes the
    result through ``Config.to_dict`` and carries everything ``Config`` does not
    own over verbatim (``config_entries.with_unmanaged_entries``). Nothing is
    written. ``init`` re-runs use it: the answers replace what ``Config`` owns.

    Raises ``FileNotFoundError`` without the committed file and ``ConfigError``
    (naming it) for one ``Config`` would misread — including one missing a
    required key (``[engine] version``) only the local file supplies: copying
    that personal value into the committed file is exactly the bug this avoids.

    Example::

        >>> plan = plan_committed_update(  # doctest: +SKIP
        ...     state, lambda c: dataclasses.replace(c, overlays_enabled=[])
        ... )
    """
    committed = state.read_committed_config_table()
    updated = update(Config.from_dict(committed, source=_COMMITTED))
    table = with_unmanaged_entries(updated.to_dict(), unmanaged_config_entries(committed))
    return _checked_rewrite(state, updated, table)


def plan_detector_cache_refresh(
    state: FileSystemStateSource, cache: dict[str, Any]
) -> ConfigRewrite:
    """The checked rewrite of the committed file with only ``[detector_cache]`` replaced.

    The committed table is written back as parsed with that one entry swapped
    (appended when absent) — not through ``Config.to_dict``, whose round trip also
    dropped an explicit ``adapters_enabled = []``/``description = ""``/empty
    ``[user_choices]`` and filled a partial ``[storage]`` or an ``[output]``
    without ``commit``. ``Config.from_dict`` still checks the result, so the same
    ``FileNotFoundError``/``ConfigError`` as :func:`plan_committed_update`.

    Example::

        >>> plan_detector_cache_refresh(state, {"has_ci": True}).table["detector_cache"]  # doctest: +SKIP
        {'has_ci': True}
    """
    table = {**state.read_committed_config_table(), "detector_cache": cache}
    return _checked_rewrite(state, Config.from_dict(table, source=_COMMITTED), table)


def detector_cache_table(facts: Facts) -> dict[str, Any]:
    """The ``[detector_cache]`` table for ``facts`` (from ``detector.detect``).

    Sets are not TOML, so each becomes a sorted list; every other fact passes
    through as is.

    Example::

        >>> detector_cache_table({"dev_tools": {"ruff", "mypy"}, "has_ci": True})
        {'dev_tools': ['mypy', 'ruff'], 'has_ci': True}
    """
    return {key: sorted(value) if isinstance(value, set) else value for key, value in facts.items()}
