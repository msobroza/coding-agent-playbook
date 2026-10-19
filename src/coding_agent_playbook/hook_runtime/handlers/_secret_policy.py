"""The secret policy the §E.4 secret hooks read from ``guard_config`` (specs/prK-hook-pack.md §E.4).

secrets-path-guard, secret-content-guard and stop-diff-sweep never read their
policy from an agent-editable file: sync rendered it (``_guard_config_secrets``).

- :func:`path_policy`: ``security.paths.PathPolicy`` from ``secret_path_globs``
  and the two exemption tables, extended by a hook's own ``extra_globs`` /
  ``allow_paths`` (its ``[guardrails.secrets]`` layer is already merged in).
- :func:`classify_path`: one ``NormalizedPath`` judged by its resolved key and,
  for a symlink, by its spelling, so no link hides a credential file.
- :func:`content_rules`: the engine rules plus ``secret_rules.extra_patterns``,
  compiled once per process.
- :func:`finding_line`: a masked ``"<rel>":<line> <rule-id> (<n> chars)``.

A private module: it registers no handler.
"""

from __future__ import annotations

import os
import posixpath
import re
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.security.paths import PathPolicy
from coding_agent_playbook.security.patterns import SECRET_GLOB_EXEMPT, SECRET_PATH_EXEMPT

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
    from coding_agent_playbook.hook_runtime.config.guard_tables import SecretPattern
    from coding_agent_playbook.hook_runtime.paths import NormalizedPath
    from coding_agent_playbook.security.paths import PathVerdict
    from coding_agent_playbook.security.secrets import SecretFinding, SecretRule

__all__ = [
    "classify_path",
    "content_rules",
    "finding_line",
    "path_policy",
    "spelled",
    "strings",
]


def path_policy(cfg: GuardConfig, config: Mapping[str, Any]) -> PathPolicy:
    """The rendered secret-path policy, extended by the hook's ``extra_globs`` / ``allow_paths``.

    Example::

        >>> path_policy(cfg, {"allow_paths": ["tests/fixtures/**"]}).allow[-1]  # doctest: +SKIP
        'tests/fixtures/**'
    """
    exempt = cfg.tables.secret_path_exempt(SECRET_PATH_EXEMPT)
    return PathPolicy(
        deny=_unique((*cfg.secret_paths.patterns, *strings(config.get("extra_globs")))),
        allow=_unique((*exempt, *strings(config.get("allow_paths")))),
        glob_exempt=cfg.tables.secret_glob_exempt(SECRET_GLOB_EXEMPT),
    )


def classify_path(
    policy: PathPolicy, path: NormalizedPath, *, home: str, platform: str
) -> PathVerdict | None:
    """``deny`` / ``ask`` for a secret ``path``; ``unknown`` for another hard link; else ``None``.

    The resolved ``key`` is matched against the resolved home (on macOS
    ``/home`` itself is a link); a symlink is also judged by the name it was
    spelled with (:func:`spelled`), so a secret-named link to an innocent file
    is still a secret path.

    Example::

        >>> classify_path(policy, normalized(".env"), home="/h", platform="linux")  # doctest: +SKIP
        'deny'
    """
    verdict = policy.classify(path.key, home=_real(home), platform=platform)
    if verdict is None and path.is_symlink:
        verdict = policy.classify(spelled(path), home=home, platform=platform)
    if verdict is not None:
        return verdict
    return "unknown" if path.nlink > 1 else None


def spelled(path: NormalizedPath) -> str:
    """The name ``path`` was given (its last link unresolved), repo-relative when inside.

    Example::

        >>> spelled(normalized("notes.txt"))  # a link to .env  # doctest: +SKIP
        'notes.txt'
    """
    parent = os.path.realpath(posixpath.dirname(path.path))
    name = posixpath.join(parent, posixpath.basename(path.path))
    root = (path.worktree_root or "").rstrip("/")
    return name[len(root) + 1 :] if root and name.startswith(root + "/") else name


def content_rules(cfg: GuardConfig) -> tuple[SecretRule, ...]:
    """The engine rules plus the rendered overlay ``extra_patterns``.

    A pattern that does not compile is dropped (validate refused it already).

    Example::

        >>> [r.rule_id for r in content_rules(cfg)][-1]  # doctest: +SKIP
        'acme-token'
    """
    # Imported here: secrets-path-guard (path-only) never compiles the content rules.
    from coding_agent_playbook.security.secrets import DEFAULT_RULES

    patterns = cfg.tables.secret_patterns()
    return DEFAULT_RULES + _compiled(patterns) if patterns else DEFAULT_RULES


def finding_line(finding: SecretFinding) -> str:
    """The masked location of ``finding``: rule, place and length, never the value.

    Example::

        >>> finding_line(SecretFinding("jwt", "JSON Web Token", "a.py", 3, 120))
        '"a.py":3 jwt (120 chars)'
    """
    where = quote_data(finding.path)
    if finding.line:
        where = f"{where}:{finding.line}"
    return f"{where} {finding.rule_id} ({finding.length} chars)"


def strings(value: object, *, default: Iterable[str] = ()) -> tuple[str, ...]:
    """``value`` as a tuple of its strings; ``default`` when it is not a list.

    Example::

        >>> strings(["a", 1, "b"]), strings(None, default=("x",))
        (('a', 'b'), ('x',))
    """
    if not isinstance(value, list):
        return tuple(default)
    return tuple(item for item in value if isinstance(item, str) and item)


@lru_cache(maxsize=8)
def _compiled(patterns: tuple[SecretPattern, ...]) -> tuple[SecretRule, ...]:
    """The overlay rows compiled once per process; a broken pattern is left out."""
    from coding_agent_playbook.security.secrets import SecretRule

    compiled: list[SecretRule] = []
    for pattern in patterns:
        try:
            compiled.append(SecretRule(pattern.id, re.compile(pattern.regex), pattern.label))
        except re.error:
            continue
    return tuple(compiled)


@lru_cache(maxsize=4)
def _real(home: str) -> str:
    return os.path.realpath(home)


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))
