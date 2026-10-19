"""The ``[links]`` table of ``.coding-agent-playbook.toml`` (SPEC §7.1, §12.6, PR L).

:class:`LinksConfig` and its parser, split out of ``links`` (the link checker)
and ``config.model``, so the config package holds the table parsers and
``config.model`` no longer imports the checker. Stdlib-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LinksConfig:
    """Parsed ``[links]`` table of ``.coding-agent-playbook.toml``.

    ``allowed_domains`` is the external-link allowlist (lowercase hostnames;
    subdomains of an entry are allowed too). Empty — the default — means fully
    strict: no external links at all.
    """

    allowed_domains: tuple[str, ...] = ()


def parse_links_config(data: dict[str, Any]) -> LinksConfig:
    """Parse a ``[links]`` table (already decoded from TOML) into a
    :class:`~coding_agent_playbook.config.tables.links.LinksConfig` (SPEC §7.1, PR L).

    The table shape::

        [links]
        allowed_domains = ["agentharnesses.io"]   # default: [] (fully strict)

    Domains are lowercased; subdomain matching happens at check time
    (:func:`coding_agent_playbook.validation.link_check.classify_link`).
    """
    raw = data.get("allowed_domains", [])
    if not isinstance(raw, list) or not all(isinstance(entry, str) for entry in raw):
        raise ValueError(f"[links] allowed_domains must be a list of strings, got {raw!r}")
    return LinksConfig(allowed_domains=tuple(entry.lower() for entry in raw))
