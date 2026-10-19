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

from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.registry import ConfigKey

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.security.pii import PiiConfig

__all__ = ["PII_CONFIG_KEY", "PII_KEY", "pii_settings"]

PII_KEY: Final = "pii"
#: Detector names; ``extend`` because a detector is a deny-table entry (§A.6).
PII_CONFIG_KEY: Final = ConfigKey("list", "extend")
#: The schema every PII-observing hook declares ``pii`` with (each lists ``PII_KEY: PII_CONFIG_KEY``).
_PII_SCHEMA: Final[Mapping[str, ConfigKey]] = MappingProxyType({PII_KEY: PII_CONFIG_KEY})


def pii_settings(config: Mapping[str, Any]) -> PiiConfig | None:
    """The PII scan ``config`` enables, or ``None`` when its ``pii`` list is empty.

    Raises ``ValueError`` naming an unknown detector or a ``pii`` value that is
    not a list of strings (an internal error for the failure policy: ``on_error: open``).

    Example::

        >>> pii_settings({"pii": ["iban"]}).detectors  # doctest: +SKIP
        ('iban',)
        >>> pii_settings({}) is None
        True
    """
    names = HookConfig(config, _PII_SCHEMA).strings(PII_KEY, blanks="keep", strict=True)
    if not names:
        return None
    from coding_agent_playbook.security.pii import pii_config

    return pii_config({"detectors": list(names)})
