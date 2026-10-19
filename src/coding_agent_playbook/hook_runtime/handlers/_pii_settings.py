"""The ``pii`` handler-config key of the hooks that only observe PII (specs/prK-hook-pack.md §E.5).

local-audit-log counts PII categories in a prompt's record and
precompact-checkpoint masks PII in the prompts it re-injects, but only when an
overlay enabled PII: it lists the named detectors (``security.pii.PII_DETECTORS``)
in the hook's ``pii`` key. The engine ships ``pii: []``, and the key is
``extend`` (§A.6), so no layer can switch off a detector an overlay listed.
``security.pii`` is imported only once the list is non-empty, so a hook with
PII off pays nothing for it on the prompt path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.registry import ConfigKey

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
    from coding_agent_playbook.security.pii import PiiConfig

__all__ = ["PII_CONFIG_KEY", "PII_KEY", "pii_settings"]

PII_KEY: Final = "pii"
#: Detector names; ``extend`` because a detector is a deny-table entry (§A.6).
PII_CONFIG_KEY: Final = ConfigKey("list", "extend")


def pii_settings(config: HookConfig) -> PiiConfig | None:
    """The PII scan ``config`` enables, or ``None`` when its ``pii`` list is empty.

    ``config`` is the calling hook's view over its own ``CONFIG_SCHEMA``, which
    declares ``pii``; a non-list ``pii`` reads as empty (validate refuses it).
    Raises ``ValueError`` naming an unknown detector (an internal error for
    the failure policy: ``on_error: open``).

    Example::

        >>> pii_settings(HookConfig({"pii": ["iban"]}, CONFIG_SCHEMA)).detectors  # doctest: +SKIP
        ('iban',)
        >>> pii_settings(HookConfig({}, CONFIG_SCHEMA)) is None  # doctest: +SKIP
        True
    """
    names = config.strings(PII_KEY, blanks="keep")
    if not names:
        return None
    from coding_agent_playbook.security.pii import pii_config

    return pii_config({"detectors": list(names)})
