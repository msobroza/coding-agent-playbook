"""The gate-weakening scanner: one policy for the Stop stage and ``playbook gate-scan`` (specs/prK-hook-pack.md §E.2).

gate-weakening-guard's ``gate-integrity`` stage and its off-workstation twin
``playbook gate-scan`` both call :func:`scan`, so the hook and CI can never
disagree. The scanner is pure: it takes parsed diff lines and config file
pairs, never git, and the caller (``SafeGit`` in the CLI, the Stop stage in
the hook) does the I/O.

What it flags:

- **Added lines** matching :data:`DEFAULT_ADDED_LINE_PATTERNS`: checker
  suppressions (``# type: ignore``, ``# noqa``, ``# pragma: no cover``,
  ``# nosec``), skipped or non-strict tests, ``cast(Any, ...)``, a new bare
  ``Any`` under the source roots, ``verify=False``, and the self-service
  escape pragmas of §E.4. A trailing reason (:data:`DEFAULT_JUSTIFICATION_REGEX`)
  after the match exempts a suppression, e.g.
  ``# type: ignore[attr-defined]  # stub gap``.
- **Loosened config** (``_gate_scan_files``): the protected TOML keys of
  :data:`DEFAULT_PROTECTED_CONFIG_KEYS`, removed pre-commit hooks and workflow
  steps, and any ``.gitleaks.toml`` change. These and the escape pragmas always
  reach the user as notes (:attr:`ScanReport.notes`), justified or not.

Eval fixtures and the playbook policy files (control-plane-guard's, so nothing
is flagged twice) are skipped. A consumer's ``[hooks.gate-weakening-guard]``
table may only add patterns and protected keys (:func:`policy_from_table`).

Import-light: ``re`` and the runtime's own stdlib helpers at module level;
``tomllib`` loads only when a config file is compared.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook._gate_scan_files import (
    TOML_PREFIXES,
    FileWeakening,
    removal_weakenings,
    toml_loosenings,
)
from coding_agent_playbook.hook_runtime._git_parse import AddedLine, RemovedLine
from coding_agent_playbook.hook_runtime.caps import clean_text, clip
from coding_agent_playbook.hook_runtime.globs import GlobSet, compile_globs
from coding_agent_playbook.hook_runtime.handlers._eval_paths import FIXTURE_GLOBS

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, Sequence

__all__ = [
    "DEFAULT_ADDED_LINE_PATTERNS",
    "DEFAULT_JUSTIFICATION_REGEX",
    "DEFAULT_PROTECTED_CONFIG_KEYS",
    "AddedLine",
    "ConfigPair",
    "Finding",
    "FindingKind",
    "LinePattern",
    "RemovedLine",
    "ScanPolicy",
    "ScanReport",
    "is_config_path",
    "policy_from_table",
    "scan",
]

type FindingKind = Literal["suppression", "pragma", "loosening"]

PYTHON_GLOBS: Final = ("*.py", "*.pyi")
ANY_FILE: Final = ("**",)
#: control-plane-guard owns the playbook policy files (§E.1).
POLICY_FILE_GLOBS: Final = (".coding-agent-playbook*.toml",)
TEST_PATH_GLOBS: Final = ("**/tests/**", "**/test/**", "test_*.py", "*_test.py", "conftest.py")
CONSUMER_TABLE: Final = "[hooks.gate-weakening-guard]"
#: git reports exact paths: match them without the darwin/win32 case folding.
_GLOB_PLATFORM: Final = "linux"
_DETAIL_CHARS: Final = 160


@dataclass(frozen=True, slots=True)
class LinePattern:
    """One added-line rule: ``regex`` searched in lines of files matching ``paths``.

    ``source_only`` limits it further to the policy's source roots, tests excluded.
    Example: ``LinePattern("verify-false", r"\\bverify\\s*=\\s*False\\b")``.
    """

    rule: str
    regex: str
    paths: tuple[str, ...] = PYTHON_GLOBS
    kind: FindingKind = "suppression"
    source_only: bool = False


#: The engine's added-line rules; order matters only when two matches overlap (first wins).
DEFAULT_ADDED_LINE_PATTERNS: Final[tuple[LinePattern, ...]] = (
    LinePattern("type-ignore", r"#\s*type:\s*ignore\b(?:\[[^\]]*\])?"),
    LinePattern(
        "noqa-security",
        r"#\s*(?i:noqa):\s*(?:[A-Z]+[0-9]+\s*,\s*)*S[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*",
    ),
    LinePattern(
        "noqa",
        r"#\s*(?i:noqa)\b(?!:\s*(?:[A-Z]+[0-9]+\s*,\s*)*S[0-9])"
        r"(?::\s*[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*)?",
    ),
    LinePattern("pragma-no-cover", r"#\s*pragma:\s*no\s*cover\b"),
    LinePattern("nosec", r"#\s*nosec\b(?:\s+B[0-9]+(?:\s*,\s*B[0-9]+)*)?"),
    LinePattern("pytest-skip-marker", r"\bpytest\.mark\.skip\b"),
    LinePattern("pytest-skipif-true", r"\bpytest\.mark\.skipif\(\s*(?:True|1)\s*[,)]"),
    LinePattern(
        "pytest-xfail-non-strict",
        r"\bpytest\.(?:mark\.xfail\b(?![^#\n]*\bstrict\s*=\s*True\b)|xfail\()",
    ),
    LinePattern("pytest-skip-call", r"\bpytest\.skip\("),
    LinePattern("cast-any", r"""\bcast\(\s*["']?(?:typing\.)?Any["']?\s*,"""),
    LinePattern(
        "bare-any",
        r"^(?!\s*(?:from|import)\s)[^#]*?(?<![\w.])(?:typing\.)?Any\b",
        source_only=True,
    ),
    LinePattern("verify-false", r"\bverify\s*=\s*False\b"),
    LinePattern(
        "self-service-pragma",
        r"playbook:\s*(?:allow-secret|trusted-artifact)\b",
        ANY_FILE,
        "pragma",
    ),
)

#: The dotted TOML keys whose loosening is flagged (ruff.toml drops the ``tool.ruff.`` prefix).
DEFAULT_PROTECTED_CONFIG_KEYS: Final[tuple[str, ...]] = (
    "tool.mypy.strict",
    "tool.mypy.ignore_missing_imports",
    "tool.mypy.exclude",
    "tool.ruff.lint.ignore",
    "tool.ruff.lint.select",
    "tool.pytest.ini_options.addopts",
    "tool.pytest.ini_options.filterwarnings",
    "tool.pytest.ini_options.xfail_strict",
    "tool.commitizen.name",
    "tool.commitizen.schema_pattern",
    "tool.commitizen.allowed_prefixes",
    "tool.commitizen.bump_pattern",
)

#: A trailing comment of 3+ characters that is not itself another pragma.
DEFAULT_JUSTIFICATION_REGEX: Final = (
    r"#\s*(?!(?i:type:|noqa|nosec|pragma\b|fmt:|playbook:))[A-Za-z][^#]{2,}"
)


@dataclass(frozen=True, slots=True)
class ScanPolicy:
    """Everything :func:`scan` applies; the defaults are the engine's policy.

    ``source_roots`` are repo-relative directories (``""`` is the repo root).
    Example: ``ScanPolicy(source_roots=("",))`` for a flat-layout repository.
    """

    patterns: tuple[LinePattern, ...] = DEFAULT_ADDED_LINE_PATTERNS
    protected_keys: tuple[str, ...] = DEFAULT_PROTECTED_CONFIG_KEYS
    justification: str = DEFAULT_JUSTIFICATION_REGEX
    source_roots: tuple[str, ...] = ("src",)
    skip_globs: tuple[str, ...] = (*FIXTURE_GLOBS, *POLICY_FILE_GLOBS)


@dataclass(frozen=True, slots=True)
class ConfigPair:
    """One config file's text before and after the change (``None``: absent).

    Example: ``ConfigPair("pyproject.toml", "[tool.mypy]\\nstrict = true\\n", None)``.
    """

    path: str
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class Finding:
    """One flagged change; ``line`` is 0 for a file-level finding.

    Example: ``Finding("a.py", 3, "noqa", "suppression", "x = 1  # noqa").line_text()``
    is ``'a.py:3: noqa: x = 1  # noqa'``.
    """

    path: str
    line: int
    rule: str
    kind: FindingKind
    detail: str
    justified: bool = False

    def line_text(self) -> str:
        """``path[:line]: rule: detail``, the one-line text form."""
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{where}: {self.rule}: {self.detail}"

    def to_json(self) -> dict[str, object]:
        """The finding as a JSON object."""
        return {
            "path": self.path,
            "line": self.line,
            "rule": self.rule,
            "kind": self.kind,
            "detail": self.detail,
            "justified": self.justified,
        }


@dataclass(frozen=True, slots=True)
class ScanReport:
    """The findings of one scan, sorted by path and line.

    Example: ``ScanReport().exit_code == 0``.
    """

    findings: tuple[Finding, ...] = ()

    @property
    def blocking(self) -> tuple[Finding, ...]:
        """The unjustified findings: they fail ``gate-scan`` and block a Stop."""
        return tuple(finding for finding in self.findings if not finding.justified)

    @property
    def notes(self) -> tuple[Finding, ...]:
        """Loosened config and escape pragmas: always shown to the user, justified or not."""
        return tuple(finding for finding in self.findings if finding.kind != "suppression")

    @property
    def exit_code(self) -> int:
        """``1`` when anything blocks, else ``0`` (``playbook gate-scan``'s exit code)."""
        return 1 if self.blocking else 0


def scan(
    added: Iterable[AddedLine],
    removed: Iterable[RemovedLine],
    config_pairs: Iterable[ConfigPair],
    policy: ScanPolicy,
) -> ScanReport:
    """Flag the gate weakenings among ``added`` / ``removed`` lines and ``config_pairs``.

    Example::

        >>> scan([AddedLine("a.py", 1, "x = f()  # type: ignore")], (), (), ScanPolicy()).exit_code
        1
    """
    rules = _Rules.of(policy)
    kept_added = [line for line in added if not rules.skip.matches(line.path)]
    kept_removed = [line for line in removed if not rules.skip.matches(line.path)]
    pairs = [pair for pair in config_pairs if not rules.skip.matches(pair.path)]
    findings = [finding for line in kept_added for finding in _line_findings(line, rules)]
    findings += _file_findings(kept_added, kept_removed, pairs, rules)
    return ScanReport(tuple(sorted(findings, key=lambda f: (f.path, f.line))))


def is_config_path(path: str) -> bool:
    """Whether :func:`scan` compares ``path``'s keys, so the caller must pass its :class:`ConfigPair`.

    Example::

        >>> is_config_path("pkg/pyproject.toml"), is_config_path("setup.cfg")
        (True, False)
    """
    return path.rpartition("/")[2] in TOML_PREFIXES


def policy_from_table(table: Mapping[str, object], base: ScanPolicy | None = None) -> ScanPolicy:
    """``base`` (default: the engine policy) extended by a ``[hooks.gate-weakening-guard]`` table.

    ``added_line_patterns`` (rows ``{id, regex, paths?}``) and
    ``protected_config_keys`` only add; ``justification_regex`` replaces. Other
    keys are left to ``playbook validate``. Raises ``ValueError`` naming the bad value.

    Example::

        >>> policy_from_table({"protected_config_keys": ["tool.mypy.warn_unused_ignores"]}
        ...                   ).protected_keys[-1]
        'tool.mypy.warn_unused_ignores'
    """
    start = base if base is not None else ScanPolicy()
    patterns = _pattern_rows(table.get("added_line_patterns", []))
    keys = _key_rows(table.get("protected_config_keys", []))
    justification = table.get("justification_regex", start.justification)
    if not isinstance(justification, str) or not justification:
        raise ValueError(
            f"{CONSUMER_TABLE} justification_regex = {justification!r}: expected a non-empty regex"
        )
    _compiled("justification_regex", justification)
    return replace(
        start,
        patterns=_extended(start.patterns, patterns),
        protected_keys=_extended(start.protected_keys, keys),
        justification=justification,
    )


# --- line rules --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Rules:
    """A :class:`ScanPolicy` compiled once per scan."""

    patterns: tuple[tuple[LinePattern, re.Pattern[str], GlobSet], ...]
    justification: re.Pattern[str]
    skip: GlobSet
    tests: GlobSet
    source_roots: tuple[str, ...]
    protected_keys: tuple[str, ...]

    @classmethod
    def of(cls, policy: ScanPolicy) -> _Rules:
        compiled = tuple(
            (pattern, _compiled(pattern.rule, pattern.regex), _globs(pattern.paths))
            for pattern in policy.patterns
        )
        return cls(
            patterns=compiled,
            justification=_compiled("justification_regex", policy.justification),
            skip=_globs(policy.skip_globs),
            tests=_globs(TEST_PATH_GLOBS),
            source_roots=policy.source_roots,
            protected_keys=policy.protected_keys,
        )

    def applying_to(self, path: str) -> Iterator[tuple[LinePattern, re.Pattern[str]]]:
        """The patterns whose scope covers ``path``, in policy order."""
        for pattern, regex, globs in self.patterns:
            if globs.matches(path) and (not pattern.source_only or self._in_source(path)):
                yield pattern, regex

    def _in_source(self, path: str) -> bool:
        under = any(not root or path.startswith(f"{root}/") for root in self.source_roots)
        return under and not self.tests.matches(path)


def _line_findings(line: AddedLine, rules: _Rules) -> list[Finding]:
    found: list[Finding] = []
    for pattern, match in _first_matches(line.text, rules.applying_to(line.path)):
        justified = rules.justification.search(line.text, match.end()) is not None
        if justified and pattern.kind == "suppression":
            continue  # a justified suppression is no finding at all
        found.append(
            Finding(line.path, line.line, pattern.rule, pattern.kind, _detail(line.text), justified)
        )
    return found


def _first_matches(
    text: str, patterns: Iterable[tuple[LinePattern, re.Pattern[str]]]
) -> Iterator[tuple[LinePattern, re.Match[str]]]:
    """Each match not overlapping an earlier one: ``cast(Any, x)`` is one finding, not two."""
    taken: list[tuple[int, int]] = []
    for pattern, regex in patterns:
        for match in regex.finditer(text):
            start, end = match.span()
            if not any(start < done_end and done_start < end for done_start, done_end in taken):
                taken.append((start, end))
                yield pattern, match


# --- file-level rules --------------------------------------------------------------------------


def _file_findings(
    added: Sequence[AddedLine],
    removed: Sequence[RemovedLine],
    pairs: Sequence[ConfigPair],
    rules: _Rules,
) -> list[Finding]:
    added_texts = _texts(added)
    weakenings = removal_weakenings(added_texts, _texts(removed))
    for pair in pairs:
        if is_config_path(pair.path):
            weakenings += toml_loosenings(pair.path, pair.before, pair.after, rules.protected_keys)
    return [_file_finding(w, added_texts.get(w.path, ()), rules) for w in weakenings]


def _file_finding(weakening: FileWeakening, added: Sequence[str], rules: _Rules) -> Finding:
    """A reason on an added line of the same file that names the change justifies it."""
    justified = any(
        rules.justification.search(text) is not None
        and (not weakening.tokens or any(token in text for token in weakening.tokens))
        for text in added
    )
    detail = clip(clean_text(weakening.detail), _DETAIL_CHARS)
    return Finding(weakening.path, 0, weakening.rule, "loosening", detail, justified)


def _texts(lines: Iterable[AddedLine | RemovedLine]) -> dict[str, list[str]]:
    by_path: dict[str, list[str]] = {}
    for line in lines:
        by_path.setdefault(line.path, []).append(line.text)
    return by_path


# --- consumer table ----------------------------------------------------------------------------


def _pattern_rows(value: object) -> tuple[LinePattern, ...]:
    if not isinstance(value, list):
        raise ValueError(
            f"{CONSUMER_TABLE} added_line_patterns = {value!r}: expected a list of "
            '{id = "<rule>", regex = "<python re>", paths = ["<glob>", ...]} rows'
        )
    return tuple(_pattern_row(index, row) for index, row in enumerate(value))


def _pattern_row(index: int, row: object) -> LinePattern:
    where = f"{CONSUMER_TABLE} added_line_patterns[{index}] = {row!r}"
    if not isinstance(row, dict):
        raise ValueError(f"{where}: expected a table {{id, regex, paths}}")
    rule, regex, paths = row.get("id"), row.get("regex"), row.get("paths", list(PYTHON_GLOBS))
    if not (isinstance(rule, str) and rule and isinstance(regex, str) and regex):
        raise ValueError(f"{where}: expected non-empty string 'id' and 'regex' keys")
    if not (isinstance(paths, list) and paths and all(isinstance(p, str) for p in paths)):
        raise ValueError(f"{where}: expected 'paths' to be a non-empty list of globs")
    if _compiled(f"added_line_patterns[{index}]", regex).search("") is not None:
        raise ValueError(f"{where}: the regex matches an empty line, so it would flag every line")
    return LinePattern(rule, regex, tuple(paths))


def _key_rows(value: object) -> tuple[str, ...]:
    if not (isinstance(value, list) and all(isinstance(k, str) and k for k in value)):
        raise ValueError(
            f"{CONSUMER_TABLE} protected_config_keys = {value!r}: expected a list of dotted "
            'TOML keys, e.g. ["tool.mypy.warn_unused_ignores"]'
        )
    return tuple(value)


def _extended[T](base: tuple[T, ...], extra: Iterable[T]) -> tuple[T, ...]:
    """``base`` then each new item of ``extra``: an extension never removes a rule."""
    added = [item for item in dict.fromkeys(extra) if item not in base]
    return (*base, *added)


# --- shared ------------------------------------------------------------------------------------


def _compiled(name: str, regex: str) -> re.Pattern[str]:
    try:
        return re.compile(regex)
    except re.error as exc:
        raise ValueError(f"{name} regex {regex!r} does not compile: {exc}") from None


def _globs(patterns: Iterable[str]) -> GlobSet:
    return compile_globs(patterns, platform=_GLOB_PLATFORM)


def _detail(text: str) -> str:
    return clip(clean_text(text.strip()), _DETAIL_CHARS)
