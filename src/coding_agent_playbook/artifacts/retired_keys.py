"""Keys an artifact used to carry and now must not: each one's replacement (#281).

``version`` was an integer nothing read, bumped in a handful of content edits;
the engine now computes a content digest of each artifact instead. A prompt's
``eval_samples`` list duplicated the samples' own ``prompt_id``. Rules,
prompts, hooks and ``sample.toml`` refuse both with the message below rather
than a bare "unknown key", so an author learns what replaced the key.

Stdlib-only and importing nothing from the package: ``artifacts.hook_schema``
(loaded on the ``hooks`` light path) imports it.
"""

from __future__ import annotations

from typing import Final

#: Retired key -> what replaced it and what to do with the line.
RETIRED_KEYS: Final[dict[str, str]] = {
    "version": (
        "the engine now computes a content digest of each artifact; delete the 'version' line"
    ),
    "eval_samples": (
        "a prompt's eval samples are the samples whose prompt_id names it; "
        "delete the 'eval_samples' list"
    ),
}


def retired_key_problem(key: object) -> str | None:
    """The refusal message for a retired ``key``, or ``None`` when ``key`` was never retired.

    Example::

        >>> retired_key_problem("version").split(":")[0]
        "retired key 'version'"
        >>> retired_key_problem("tags") is None
        True
    """
    reason = RETIRED_KEYS.get(str(key))
    if reason is None:
        return None
    return f"retired key {str(key)!r}: {reason}"
