"""The secret tables of ``guard_config.json`` (specs/prK-hook-pack.md §E.4).

The three secret hooks read one rendered policy, so they can never disagree:

- ``secret_path_exempt`` / ``secret_glob_exempt``: the exemptions beside K3's
  ``secret_path_globs``. ``SECRET_PATH_EXEMPT`` plus ``[guardrails.secrets]
  allow_paths`` cancel every glob; a ``SECRET_GLOB_EXEMPT`` row cancels only its
  own glob (``*credentials*.py`` is code, ``.env.credentials.py`` stays secret).
- ``secret_rules``: the engine ruleset's id, version and rule ids, plus the
  overlay ``extra_patterns`` of secret-content-guard and stop-diff-sweep as
  ``{id, regex, label}`` rows. Validate already refused a pattern
  ``screen_regex`` rejects; sync drops one again rather than render it.

Machine-independent, like every ``guard_config`` table (§D.8.3). Stdlib-only.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime._config_keys import regex_of
from coding_agent_playbook.security.patterns import (
    SECRET_CONTENT_RULES,
    SECRET_GLOB_EXEMPT,
    SECRET_PATH_EXEMPT,
    SECRET_RULESET_ID,
    SECRET_RULESET_VERSION,
)
from coding_agent_playbook.security.secrets import screen_regex

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.hooks_config import GuardrailsConfig

__all__ = ["PATTERN_SOURCES", "extra_pattern_rows", "secret_tables"]

#: The hooks (and the event of their handler) whose ``extra_patterns`` join the ruleset.
PATTERN_SOURCES: Final = (("secret-content-guard", "pre_tool_use"), ("stop-diff-sweep", "stop"))
_DEFAULT_LABEL: Final = "overlay secret pattern"
_ID_DIGEST_CHARS: Final = 8


def secret_tables(hooks: Sequence[ResolvedHook], guardrails: GuardrailsConfig) -> dict[str, Any]:
    """``secret_path_exempt``, ``secret_glob_exempt`` and ``secret_rules`` (module docstring).

    Example::

        >>> secret_tables([], GuardrailsConfig())["secret_rules"]["ruleset"]  # doctest: +SKIP
        'engine-secrets'
    """
    allow = [*SECRET_PATH_EXEMPT, *guardrails.secrets.allow_paths]
    return {
        "secret_path_exempt": list(dict.fromkeys(allow)),
        "secret_glob_exempt": {glob: list(exempt) for glob, exempt in SECRET_GLOB_EXEMPT.items()},
        "secret_rules": {
            "ruleset": SECRET_RULESET_ID,
            "version": SECRET_RULESET_VERSION,
            "rule_ids": [rule_id for rule_id, _, _ in SECRET_CONTENT_RULES],
            "extra_patterns": extra_pattern_rows(hooks),
        },
    }


def extra_pattern_rows(hooks: Iterable[ResolvedHook]) -> list[dict[str, str]]:
    """The merged ``extra_patterns`` of :data:`PATTERN_SOURCES` as ``{id, regex, label}`` rows.

    A row without an ``id`` gets ``extra-<sha256(regex)[:8]>``, stable across
    syncs; duplicates are dropped, first occurrence kept.

    Example::

        >>> extra_pattern_rows([])
        []
    """
    rows: list[dict[str, str]] = []
    sources = dict(PATTERN_SOURCES)
    for hook in hooks:
        handler = hook.handlers.get(sources.get(hook.id, ""))
        raw = None if handler is None else handler.config.get("extra_patterns")
        for item in raw if isinstance(raw, list) else ():
            row = _row(item)
            if row is not None and row not in rows:
                rows.append(row)
    return rows


def _row(item: object) -> dict[str, str] | None:
    """One screened ``{id, regex, label}`` row, or ``None`` for an unusable pattern."""
    regex = regex_of(item)
    if not regex or screen_regex(regex) is not None:
        return None
    table = item if isinstance(item, dict) else {}
    rule_id, label = table.get("id"), table.get("label")
    if not isinstance(rule_id, str) or not rule_id:
        digest = hashlib.sha256(regex.encode("utf-8")).hexdigest()[:_ID_DIGEST_CHARS]
        rule_id = f"extra-{digest}"
    return {
        "id": rule_id,
        "regex": regex,
        "label": label if isinstance(label, str) and label else _DEFAULT_LABEL,
    }
