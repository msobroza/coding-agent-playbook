"""The overlay checks ``playbook init`` runs before it writes anything.

Split out of ``commands/init.py`` (CP-2, specs/prT-package-layout.md AC.5.5), verbatim.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.catalog.roots import canonical_overlay_name
from coding_agent_playbook.config.files import CONFIG_LOCAL_FILENAME
from coding_agent_playbook.config.framework import (
    bundled_framework_names,
    framework_layers,
    framework_package,
)
from coding_agent_playbook.validation import preflight as _sync_preflight

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.commands._init_answers import Answers


def overlay_lists_to_check(
    answers: Answers, local: Mapping[str, Any]
) -> list[tuple[list[str], str]]:
    """Each overlay list init must check before writing, with the setting that lists it.

    ``--overlays`` always: it is what the committed file gets, so every teammate
    without a local file syncs with it. And a local ``overlays_enabled`` when
    ``.coding-agent-playbook.local.toml`` sets one: it replaces the committed
    list (SPEC §7.2), so it is what init's own final sync runs with. Checking
    only that one let an unusable ``--overlays`` reach the committed file, where
    it broke every teammate's ``playbook sync``.

    Example::

        >>> overlay_lists_to_check({"overlays": ["a"]}, {"overlays_enabled": ["b"]})  # doctest: +SKIP
        [(['a'], '--overlays'), (['b'], 'overlays_enabled in .coding-agent-playbook.local.toml')]
    """
    lists = [(list(answers["overlays"]), "--overlays")]
    if "overlays_enabled" in local:
        origin = f"overlays_enabled in {CONFIG_LOCAL_FILENAME}"
        lists.append((list(local["overlays_enabled"]), origin))
    return lists


def refuse_unusable_overlays(overlays: list[str], origin: str) -> bool:
    """Print an ``error:`` and return ``True`` when one of ``overlays`` is unusable.

    Uses the sync preflight's own check, so init never writes a config that
    every ``playbook sync`` mode would then refuse to run with. ``origin`` names
    the setting the overlays came from (``--overlays`` or the local file's list).
    """
    unusable = _sync_preflight.unusable_overlays(overlays)
    if not unusable:
        return False
    listed = "".join(f"\n  {problem}" for problem in unusable)
    print(
        f"error: {origin} names overlay package(s) or bundled plugin(s) that cannot be used "
        f"here; nothing was written:{listed}",
        file=sys.stderr,
    )
    return True


def refuse_unusable_framework(choice: str | None) -> bool:
    """Print an ``error:`` and return ``True`` when ``choice`` names no usable framework.

    ``None`` (no choice) and ``none`` pass. Otherwise the layer ``choice``
    resolves to must pass the overlay preflight and ship ``framework.toml``
    (D57), so init never commits a framework every sync would refuse.

    Example::

        >>> refuse_unusable_framework("superpowers")
        False
    """
    package = None if choice is None else framework_package(choice)
    if package is None:
        return False
    unusable = _sync_preflight.unusable_overlays([package])
    if not unusable and framework_layers([package]):
        return False
    reason = str(unusable[0]) if unusable else f"{package} ships no framework.toml"
    known = ", ".join(sorted(bundled_framework_names()))
    print(
        f"error: --framework {choice!r} is not a usable framework ({reason}); "
        f"use {known}, an overlay module that ships framework.toml, or none; "
        "nothing was written",
        file=sys.stderr,
    )
    return True


def warn_deprecated_flag_overlays(deprecated: tuple[str, ...]) -> None:
    """Print one stderr ``warning: --overlays:`` line per distinct deprecated name.

    ``deprecated`` is what ``canonical_overlay_list`` rewrote in ``--overlays``
    (SPEC v0.19). The local file's list is not warned about here: init's final
    sync goes through ``SyncContext.from_repo``, which does that.

    Example::

        >>> warn_deprecated_flag_overlays(deprecated)  # doctest: +SKIP
        warning: --overlays: '<old>' is deprecated; use '<new>'
    """
    for old in dict.fromkeys(deprecated):
        print(
            f"warning: --overlays: '{old}' is deprecated; use '{canonical_overlay_name(old)}'",
            file=sys.stderr,
        )
