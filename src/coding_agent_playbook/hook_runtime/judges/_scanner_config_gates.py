"""gate_weakening's scanner rules: secret and SAST scanners loosened on either forge (specs/prF-forge-adapter.md §14).

- ``scanner-config-changed``: any change to a scanner's own config file
  (:data:`SCANNER_CONFIG_FILES`, at any depth). Its direction is unknown, so any
  change counts, as ``config-loosening`` does for an unknown key.
- ``scanner-loosened-in-ci``: an added line of a CI file (a GitHub workflow or
  a GitLab CI file of the policy) that sets ``SAST_DISABLED``,
  ``SECRET_DETECTION_DISABLED`` or a ``*_EXCLUDED_PATHS`` variable as a YAML
  key (``variables:`` / ``env:``), unless the same setting is removed from the
  same file (a move). Only lines are read, never YAML (Q54).

What is not a loosening: a comment, a reference (``if: $SAST_DISABLED``), a
``*_DISABLED`` set to ``false``, ``0`` or ``""``, and a ``*_EXCLUDED_PATHS`` set
to ``""``. GitLab 16.0+ templates skip a job only on ``'true'`` or ``'1'``, but
up to 15.11 any non-empty value did, so ``yes`` or ``TRUE`` still count. Known
limits: a value set in the project's CI/CD settings, or by ``export`` in a
script (which ``rules:`` never see anyway), is not in the diff.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.judges._gate_weakening_files import (
    FileWeakening,
    is_workflow_path,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

__all__ = ["SCANNER_CONFIG_FILES", "scanner_weakenings"]

#: gitleaks' default config, GitLab's secret-detection and SAST rulesets, GitHub's secret scanning paths.
SCANNER_CONFIG_FILES: Final = (
    ".gitleaks.toml",
    ".gitlab/secret-detection-ruleset.toml",
    ".gitlab/sast-ruleset.toml",
    ".github/secret_scanning.yml",
)
#: ``NAME: value`` as a YAML mapping key, quoted or not; group 1 the name, 2 the raw value.
_SCANNER_SETTING = re.compile(
    r"""^[ \t]*(?:-[ \t]+)?["']?"""
    r"""(SAST_DISABLED|SECRET_DETECTION_DISABLED|[A-Z][A-Z0-9_]*_EXCLUDED_PATHS)"""
    r"""["']?[ \t]*:(?:[ \t]+(.*?))?[ \t]*$"""
)
#: A trailing `` # comment``, so a reason after the value is not part of it.
_TRAILING_COMMENT = re.compile(r"[ \t]+#.*$")
#: ``*_DISABLED`` values that leave the scanner on (GitLab 16.0+ skips only on ``true`` / ``1``).
_STILL_ENABLED: Final = frozenset({"false", "0", ""})
#: Shown for ``NAME:`` with no value (GitLab's expanded ``value:`` form): unknown, so flagged.
_VALUE_BELOW: Final = "(value on the next lines)"


def scanner_weakenings(
    added: Mapping[str, Sequence[str]],
    removed: Mapping[str, Sequence[str]],
    is_ci_config: Callable[[str], bool],
) -> list[FileWeakening]:
    """Scanner config files a diff touches, and scanner variables its CI files set.

    ``added`` / ``removed`` map each path to its added / removed line texts;
    ``is_ci_config`` says whether a path is one of the policy's GitLab CI files.

    Example::

        >>> [w.rule for w in scanner_weakenings({".gitleaks.toml": ["[allowlist]"]}, {}, bool)]
        ['scanner-config-changed']
    """
    found = [
        FileWeakening(path, "scanner-config-changed", f"{path} changed", ())
        for path in sorted({*added, *removed})
        if _is_scanner_config(path)
    ]
    for path in sorted(added):
        if is_workflow_path(path) or is_ci_config(path):
            found += _ci_loosenings(path, added[path], removed.get(path, ()))
    return found


def _is_scanner_config(path: str) -> bool:
    return any(path == name or path.endswith(f"/{name}") for name in SCANNER_CONFIG_FILES)


def _ci_loosenings(path: str, added: Sequence[str], removed: Sequence[str]) -> list[FileWeakening]:
    """The loosening settings ``added`` gains that ``removed`` does not give back (a move)."""
    gained = _loosening_settings(added) - _loosening_settings(removed)
    return [
        FileWeakening(path, "scanner-loosened-in-ci", f"sets {name}: {value}", (name,))
        for name, value in sorted(gained)
    ]


def _loosening_settings(lines: Iterable[str]) -> Counter[tuple[str, str]]:
    """Each loosening ``(name, shown value)``; quotes and spacing never tell two apart."""
    found: Counter[tuple[str, str]] = Counter()
    for line in lines:
        match = _SCANNER_SETTING.match(_TRAILING_COMMENT.sub("", line))
        if match is not None and _loosens(match[1], match[2] or ""):
            found[match[1], _unquoted(match[2] or "").strip() or _VALUE_BELOW] += 1
    return found


def _loosens(name: str, raw: str) -> bool:
    """``raw`` keeps its quotes: a bare ``NAME:`` is unknown, an explicit ``""`` is empty."""
    if not raw:
        return True
    value = _unquoted(raw).strip()
    if name.endswith("_EXCLUDED_PATHS"):
        return bool(value)
    return value.lower() not in _STILL_ENABLED


def _unquoted(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text
