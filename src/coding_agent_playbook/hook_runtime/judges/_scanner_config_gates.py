"""gate_weakening's scanner rules: secret and SAST scanners loosened on either forge (specs/prF-forge-adapter.md §14).

- ``scanner-config-changed``: any change to a scanner's own config file
  (:data:`SCANNER_CONFIG_FILES`, at any depth). Its direction is unknown, so any
  change counts, as ``config-loosening`` does for an unknown key.
- ``scanner-loosened-in-ci``: an added line of a CI file that sets
  ``SAST_DISABLED``, ``SECRET_DETECTION_DISABLED`` or a ``*_EXCLUDED_PATHS``
  variable as a YAML key (``variables:`` / ``env:``), unless the same setting is
  removed at the same indent in the same file (a move; a job's setting moved to
  the global ``variables:`` widens it, so it counts). CI files are the GitHub
  workflows and the policy's GitLab CI files: the rule is forge-neutral (§14),
  and a workflow can run GitLab's analyzer images, which read these variables.

Values follow GitLab 16.0+ (the 15.x templates that skipped on any value are
out of support): a ``*_DISABLED`` switches a scanner off when YAML reads it as
``true`` or ``1`` (unquoted ``true`` / ``yes`` / ``on`` in any case, which GitLab
turns into ``"true"``; quoted only ``"true"`` / ``"1"``). An ``*_EXCLUDED_PATHS``
loosens unless it is empty. A value the line alone cannot tell (none: GitLab's
expanded ``value:`` form, a flow mapping, a block scalar, an alias, a ``$VAR``)
counts. Comments and references (``if: $SAST_DISABLED``) are no settings.

Known limits of line patterns: a changed ``value:`` under an unchanged expanded
key, a flow mapping ``variables: {SAST_DISABLED: "true"}``, and values set in
the project's CI/CD settings (or by ``export`` in a script, which ``rules:``
never see) are not in the diff lines this rule reads.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING, Final, NamedTuple

from coding_agent_playbook.hook_runtime.judges._gate_weakening_files import (
    FileWeakening,
    is_workflow_path,
)
from coding_agent_playbook.hook_runtime.judges._yaml_lines import unquoted, without_comment

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
#: ``NAME: value`` as a YAML mapping key, quoted or not; groups: indent, name, raw value.
_SCANNER_SETTING = re.compile(
    r"""^([ \t]*)(?:-[ \t]+)?["']?"""
    r"""(SAST_DISABLED|SECRET_DETECTION_DISABLED|[A-Z][A-Z0-9_]*_EXCLUDED_PATHS)"""
    r"""["']?[ \t]*:(?:[ \t]+(.*?))?[ \t]*$"""
)
#: Unquoted scalars YAML 1.1 (GitLab's parser) reads as ``true`` or ``1``.
_YAML_TRUE: Final = frozenset({"true", "yes", "on", "1"})
#: Quoted values GitLab 16.0+ templates compare against (``== 'true' || == '1'``).
_QUOTED_TRUE: Final = frozenset({"true", "1"})
#: Unquoted scalars that are empty in YAML: ``null`` and ``~``.
_YAML_NULL: Final = frozenset({"", "null", "~"})
#: A value's first character that defers it elsewhere: a mapping, block scalar, alias or variable.
_DEFERRED_START: Final = ("{", "[", "|", ">", "*", "&", "!")
#: Shown for ``NAME:`` with no value on the line (GitLab's expanded ``value:`` form).
_VALUE_BELOW: Final = "(value on the next lines)"


class _ScannerSetting(NamedTuple):
    """One ``NAME: value`` line as compared: indent, variable name, value as shown."""

    indent: int
    name: str
    shown: str


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
        FileWeakening(path, "scanner-loosened-in-ci", f"sets {s.name}: {s.shown}", (s.name,))
        for s in sorted(gained)
    ]


def _loosening_settings(lines: Iterable[str]) -> Counter[_ScannerSetting]:
    found: Counter[_ScannerSetting] = Counter()
    for line in lines:
        match = _SCANNER_SETTING.match(without_comment(line))
        if match is None or not _loosens(match[2], match[3] or ""):
            continue
        shown = unquoted(match[3] or "").strip() or _VALUE_BELOW
        found[_ScannerSetting(len(match[1]), match[2], shown)] += 1
    return found


def _loosens(name: str, raw: str) -> bool:
    """Whether ``raw`` (quotes kept: ``"0"`` is a string, ``0`` an integer) loosens ``name``."""
    if not raw or raw.startswith(_DEFERRED_START) or "$" in raw:
        return True  # the line alone cannot tell, so it counts
    quoted = unquoted(raw) != raw
    value = unquoted(raw).strip()
    if name.endswith("_EXCLUDED_PATHS"):
        return bool(value) and (quoted or value.lower() not in _YAML_NULL)
    return value in _QUOTED_TRUE if quoted else value.lower() in _YAML_TRUE
