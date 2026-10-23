"""The pure gate-weakening scanner (specs/prK-hook-pack.md §E.2 gate-weakening-guard).

``gate_weakening.scan`` takes parsed diff lines and config file pairs, never git, so
every rule is pinned here without a repository: the added-line patterns and
their trailing-justification escape, the TOML key diffs that loosen a checker,
the pre-commit hook and workflow step removals, the ``.gitleaks.toml`` watch
(``scanner-config-changed``; its peers in ``test_gate_weakening_scanners``),
the skipped paths, and the consumer layer that may only add rules.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.hook_runtime.judges._gate_weakening_files import is_workflow_path
from coding_agent_playbook.hook_runtime.judges.gate_weakening import (
    DEFAULT_ADDED_LINE_PATTERNS,
    DEFAULT_JUSTIFICATION_REGEX,
    DEFAULT_PROTECTED_CONFIG_KEYS,
    AddedLine,
    ConfigPair,
    LinePattern,
    RemovedLine,
    ScanPolicy,
    ScanReport,
    is_config_path,
    policy_from_table,
    scan,
)
from tests.import_probe import run_python_probe

POLICY = ScanPolicy()

#: One flagged sample per default rule: (path, added text).
SAMPLES: dict[str, tuple[str, str]] = {
    "type-ignore": ("src/pkg/a.py", "x = f()  # type: ignore[attr-defined]"),
    "noqa": ("src/pkg/a.py", "import os  # noqa: F401"),
    "noqa-security": ("src/pkg/a.py", "assert token  # noqa: S105"),
    "pragma-no-cover": ("src/pkg/a.py", "if debug:  # pragma: no cover"),
    "nosec": ("src/pkg/a.py", "run(cmd, shell=True)  # nosec"),
    "pytest-skip-marker": ("tests/test_a.py", "@pytest.mark.skip(reason='flaky')"),
    "pytest-skipif-true": ("tests/test_a.py", "@pytest.mark.skipif(True, reason='later')"),
    "pytest-xfail-non-strict": ("tests/test_a.py", "@pytest.mark.xfail(reason='bug 12')"),
    "pytest-skip-call": ("tests/test_a.py", "    pytest.skip('no database')"),
    "cast-any": ("src/pkg/a.py", "value = cast(Any, raw)"),
    "bare-any": ("src/pkg/a.py", "def load(raw: Any) -> None:"),
    "verify-false": ("src/pkg/a.py", "requests.get(url, verify=False)"),
    "self-service-pragma": ("deploy/app.env.example", "TOKEN=abc  # playbook: allow-secret"),
}


def _scan_lines(*lines: AddedLine, policy: ScanPolicy = POLICY) -> ScanReport:
    return scan(lines, (), (), policy)


def _rules(report: ScanReport) -> list[str]:
    return [finding.rule for finding in report.findings]


def _pyproject(before: str | None, after: str | None, *added: str) -> ScanReport:
    lines = [AddedLine("pyproject.toml", number, text) for number, text in enumerate(added, 1)]
    return scan(lines, (), [ConfigPair("pyproject.toml", before, after)], POLICY)


# --- added-line patterns -----------------------------------------------------------------------


def test_samples_cover_every_default_pattern() -> None:
    assert set(SAMPLES) == {pattern.rule for pattern in DEFAULT_ADDED_LINE_PATTERNS}


@pytest.mark.parametrize("rule", sorted(SAMPLES))
def test_added_line_pattern_is_flagged(rule: str) -> None:
    path, text = SAMPLES[rule]

    report = _scan_lines(AddedLine(path, 7, text))

    assert _rules(report) == [rule]
    finding = report.findings[0]
    assert (finding.path, finding.line, finding.justified) == (path, 7, False)
    assert report.blocking == report.findings
    assert report.exit_code == 1


def test_justified_type_ignore_passes() -> None:
    line = AddedLine("src/pkg/a.py", 3, "x = f()  # type: ignore[attr-defined]  # stub gap")

    assert _scan_lines(line).findings == ()


def test_a_pragma_after_a_pragma_is_no_justification() -> None:
    line = AddedLine("src/pkg/a.py", 3, "x = f()  # type: ignore  # noqa")

    assert _rules(_scan_lines(line)) == ["type-ignore", "noqa"]


def test_strict_xfail_not_flagged() -> None:
    lines = [
        AddedLine("tests/test_a.py", 1, "@pytest.mark.xfail(strict=True, reason='bug 12')"),
        AddedLine("tests/test_a.py", 2, "@pytest.mark.xfail(reason='bug 12', strict=True)"),
        AddedLine("tests/test_a.py", 3, "@pytest.mark.skipif(sys.platform == 'win32', reason='x')"),
    ]

    assert _scan_lines(*lines).findings == ()


def test_removed_lines_never_flagged() -> None:
    removed = [
        RemovedLine("src/pkg/a.py", 4, "x = f()  # type: ignore"),
        RemovedLine("tests/test_a.py", 9, "@pytest.mark.skip"),
    ]

    assert scan((), removed, (), POLICY).findings == ()


def test_bare_any_only_in_source_roots_outside_tests_and_imports() -> None:
    lines = [
        AddedLine("src/pkg/a.py", 1, "from typing import Any"),
        AddedLine("src/pkg/a.py", 2, "    # Any value works here"),
        AddedLine("src/tests/test_a.py", 3, "def f(x: Any) -> None: ..."),
        AddedLine("scripts/tool.py", 4, "def f(x: Any) -> None: ..."),
    ]

    assert _scan_lines(*lines).findings == ()
    flat = ScanPolicy(source_roots=("",))
    assert _rules(_scan_lines(lines[3], policy=flat)) == ["bare-any"]


def test_patterns_are_scoped_to_their_paths() -> None:
    assert (
        _scan_lines(AddedLine("docs/guide.md", 1, "use `# type: ignore` sparingly")).findings == ()
    )


def test_justified_self_service_pragma_is_a_note_not_a_block() -> None:
    line = AddedLine("deploy/app.env", 2, "KEY=x  # playbook: allow-secret  # test fixture key")

    report = _scan_lines(line)

    assert _rules(report) == ["self-service-pragma"]
    assert report.findings[0].justified
    assert report.blocking == ()
    assert report.notes == report.findings
    assert report.exit_code == 0


# --- skipped paths -----------------------------------------------------------------------------


def test_eval_fixture_paths_skipped() -> None:
    path = "src/coding_agent_playbook/resources/eval_samples/t1/setup/app/db.py"
    pair = ConfigPair(
        "pkg/eval_samples/t1/setup/pyproject.toml", "[tool.mypy]\nstrict = true\n", ""
    )

    report = scan([AddedLine(path, 1, "q = f()  # type: ignore")], (), [pair], POLICY)

    assert report.findings == ()


def test_playbook_policy_toml_not_flagged() -> None:
    before = "[metrics]\nfail_on_breach = true\n"
    lines = [AddedLine(".coding-agent-playbook.local.toml", 1, "x = 1  # playbook: allow-secret")]
    pairs = [ConfigPair(".coding-agent-playbook.toml", before, "[metrics]\n")]

    assert scan(lines, (), pairs, POLICY).findings == ()
    assert not is_config_path(".coding-agent-playbook.toml")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("pyproject.toml", True),
        ("pkg/pyproject.toml", True),
        ("ruff.toml", True),
        (".ruff.toml", True),
        (".pre-commit-config.yaml", False),
        ("src/pyproject.py", False),
    ],
)
def test_is_config_path(path: str, expected: bool) -> None:
    assert is_config_path(path) is expected


# --- TOML loosening ----------------------------------------------------------------------------

_ADDOPTS = '[tool.pytest.ini_options]\naddopts = ["-ra", "--cov-fail-under={}"]\n'


def test_lowering_cov_fail_under_is_loosening() -> None:
    report = _pyproject(_ADDOPTS.format(80), _ADDOPTS.format(70))

    assert _rules(report) == ["config-loosening"]
    finding = report.findings[0]
    assert finding.kind == "loosening"
    assert "--cov-fail-under 80 → 70" in finding.detail
    assert report.blocking == report.notes == report.findings


def test_raising_cov_fail_under_is_not_loosening() -> None:
    assert _pyproject(_ADDOPTS.format(80), _ADDOPTS.format(90)).findings == ()


def test_justified_loosening_is_a_note_only() -> None:
    after = _ADDOPTS.format(70)
    comment = '    "--cov-fail-under=70",  # integration suite moved to nightly'

    report = _pyproject(_ADDOPTS.format(80), after, comment)

    assert report.findings[0].justified
    assert report.blocking == ()
    assert report.notes == report.findings


def test_addopts_string_form_and_dropped_guards_are_loosening() -> None:
    before = '[tool.pytest.ini_options]\naddopts = "--strict-markers --cov-fail-under 80"\n'
    after = '[tool.pytest.ini_options]\naddopts = "-p no:warnings --ignore=tests/slow"\n'

    (finding,) = _pyproject(before, after).findings

    assert "--cov-fail-under 80 → (absent)" in finding.detail
    assert "drops --strict-markers" in finding.detail
    assert "adds --ignore=tests/slow, no:warnings" in finding.detail


def test_mypy_ignore_missing_imports_switched_on_is_loosening() -> None:
    before = "[tool.mypy]\nstrict = true\n"
    after = "[tool.mypy]\nstrict = true\nignore_missing_imports = true\n"

    assert "ignore_missing_imports: (absent) → true" in _pyproject(before, after).findings[0].detail


def test_mypy_strict_false_is_loosening() -> None:
    report = _pyproject("[tool.mypy]\nstrict = true\n", "[tool.mypy]\nstrict = false\n")

    assert _rules(report) == ["config-loosening"]
    assert "[tool.mypy] strict: true → false" in report.findings[0].detail


def test_mypy_turning_strict_on_is_not_loosening() -> None:
    assert _pyproject("[tool.mypy]\n", "[tool.mypy]\nstrict = true\n").findings == ()


def test_removing_the_mypy_table_is_loosening() -> None:
    report = _pyproject("[tool.mypy]\nstrict = true\n", "[project]\nname = 'x'\n")

    assert "true → (absent)" in report.findings[0].detail


def test_ruff_ignore_growth_is_loosening() -> None:
    before = '[tool.ruff.lint]\nignore = ["E501"]\nselect = ["E", "F", "B"]\n'
    after = '[tool.ruff.lint]\nignore = ["E501", "F401"]\nselect = ["E", "F"]\n'

    details = [finding.detail for finding in _pyproject(before, after).findings]

    assert any("ignore" in d and "F401" in d for d in details)
    assert any("select" in d and "B" in d for d in details)
    tighter = '[tool.ruff.lint]\nignore = []\nselect = ["E", "F", "B", "UP"]\n'
    assert _pyproject(before, tighter).findings == ()


def test_ruff_toml_keys_are_read_without_the_tool_prefix() -> None:
    pair = ConfigPair("ruff.toml", '[lint]\nignore = ["E501"]\n', '[lint]\nignore = ["E", "F"]\n')

    report = scan((), (), [pair], POLICY)

    assert _rules(report) == ["config-loosening"]


def test_pytest_filterwarnings_and_xfail_strict_loosening() -> None:
    before = '[tool.pytest.ini_options]\nfilterwarnings = ["error"]\nxfail_strict = true\n'
    after = '[tool.pytest.ini_options]\nfilterwarnings = ["error", "ignore::UserWarning"]\n'

    details = " | ".join(finding.detail for finding in _pyproject(before, after).findings)

    assert "filterwarnings" in details and "ignore::UserWarning" in details
    assert "xfail_strict: true → (absent)" in details


def test_commitizen_unknown_direction_counts_as_loosening() -> None:
    before = (
        '[tool.commitizen]\nname = "cz_conventional_commits"\nschema_pattern = "^(feat|fix):"\n'
    )
    after = '[tool.commitizen]\nname = "cz_conventional_commits"\nschema_pattern = "^(\\\\w+):"\n'

    report = _pyproject(before, after)

    assert _rules(report) == ["config-loosening"]
    assert "schema_pattern" in report.findings[0].detail


def test_newly_added_commitizen_table_is_not_loosening() -> None:
    after = '[tool.commitizen]\nname = "cz_customize"\n'

    assert _pyproject("[project]\nname = 'x'\n", after).findings == ()


def test_pyproject_that_no_longer_parses_is_loosening() -> None:
    report = _pyproject("[tool.mypy]\nstrict = true\n", "[tool.mypy\nstrict = true\n")

    assert _rules(report) == ["config-loosening"]
    assert "no longer parses" in report.findings[0].detail


# --- file-level removals ------------------------------------------------------------------------


def test_precommit_hook_removal_flagged() -> None:
    removed = [
        RemovedLine(".pre-commit-config.yaml", 20, "      - id: mypy"),
        RemovedLine(".pre-commit-config.yaml", 21, "        name: mypy"),
    ]

    report = scan((), removed, (), POLICY)

    assert _rules(report) == ["precommit-hook-removed"]
    assert "'mypy'" in report.findings[0].detail
    assert report.findings[0].kind == "loosening"


def test_precommit_hook_moved_within_the_file_is_not_removed() -> None:
    added = [AddedLine(".pre-commit-config.yaml", 3, "      - id: mypy")]
    removed = [RemovedLine(".pre-commit-config.yaml", 20, "      - id: mypy")]

    assert scan(added, removed, (), POLICY).findings == ()


def test_workflow_step_removal_flagged() -> None:
    removed = [
        RemovedLine(".github/workflows/ci.yml", 38, "      - name: mypy (strict)"),
        RemovedLine(".github/workflows/ci.yml", 39, "        run: mypy"),
    ]

    report = scan((), removed, (), POLICY)

    assert _rules(report) == ["workflow-step-removed"]
    assert "'mypy (strict)'" in report.findings[0].detail


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".github/workflows/ci.yml", True),
        ("svc/.github/workflows/release.yaml", True),
        (".github/workflows/sub/ci.yml", False),
        (".github/secret_scanning.yml", False),
        (".gitlab-ci.yml", False),
    ],
)
def test_is_workflow_path_matches_github_workflows_at_any_depth(path: str, expected: bool) -> None:
    assert is_workflow_path(path) is expected


def test_renamed_workflow_step_with_a_reason_is_justified() -> None:
    path = ".github/workflows/ci.yml"
    removed = [RemovedLine(path, 38, "      - name: mypy (strict)")]
    added = [
        AddedLine(path, 38, "      - name: mypy  # mypy (strict) renamed: strict is in config")
    ]

    report = scan(added, removed, (), POLICY)

    assert [finding.justified for finding in report.findings] == [True]


def test_gitleaks_change_flagged() -> None:
    added = [AddedLine(".gitleaks.toml", 5, 'paths = ["fixtures/"]')]

    report = scan(added, (), (), POLICY)

    assert _rules(report) == ["scanner-config-changed"]
    assert report.exit_code == 1


# --- consumer layer ----------------------------------------------------------------------------


def test_consumer_extend_adds_patterns_never_removes() -> None:
    row = {"id": "type-ignore", "regex": r"TODO\(skip\)", "paths": ["*.py"]}
    table = {
        "added_line_patterns": [row],
        "protected_config_keys": ["tool.mypy.warn_unused_ignores"],
    }

    policy = policy_from_table(table)

    assert policy.patterns[: len(DEFAULT_ADDED_LINE_PATTERNS)] == DEFAULT_ADDED_LINE_PATTERNS
    assert policy.patterns[-1] == LinePattern("type-ignore", r"TODO\(skip\)", ("*.py",))
    assert policy.protected_keys == (
        *DEFAULT_PROTECTED_CONFIG_KEYS,
        "tool.mypy.warn_unused_ignores",
    )
    assert policy.justification == DEFAULT_JUSTIFICATION_REGEX
    lines = [AddedLine("a.py", 1, "x = 1  # type: ignore"), AddedLine("b.py", 1, "TODO(skip)")]
    assert _rules(_scan_lines(*lines, policy=policy)) == ["type-ignore", "type-ignore"]


def test_consumer_protected_key_with_unknown_direction_flags_any_change() -> None:
    policy = policy_from_table({"protected_config_keys": ["tool.mypy.warn_unused_ignores"]})
    before = "[tool.mypy]\nwarn_unused_ignores = false\n"
    pair = ConfigPair("pyproject.toml", before, "[tool.mypy]\nwarn_unused_ignores = true\n")

    assert _rules(scan((), (), [pair], policy)) == ["config-loosening"]


def test_consumer_justification_regex_replaces_the_default() -> None:
    policy = policy_from_table({"justification_regex": r"#\s*JUSTIFIED:"})
    lines = [
        AddedLine("a.py", 1, "x = f()  # type: ignore  # stub gap"),
        AddedLine("a.py", 2, "y = f()  # type: ignore  # JUSTIFIED: upstream stub"),
    ]

    report = _scan_lines(*lines, policy=policy)

    assert [finding.line for finding in report.findings] == [1]


@pytest.mark.parametrize(
    ("table", "message"),
    [
        ({"added_line_patterns": "x"}, "added_line_patterns"),
        ({"added_line_patterns": [{"id": "a"}]}, r"added_line_patterns\[0\]"),
        ({"added_line_patterns": [{"id": "a", "regex": "("}]}, "does not compile"),
        ({"added_line_patterns": ["x"]}, "expected a table"),
        ({"added_line_patterns": [{"id": "a", "regex": "b", "paths": []}]}, "paths"),
        ({"added_line_patterns": [{"id": "a", "regex": "b*"}]}, "matches an empty line"),
        ({"protected_config_keys": [1]}, "protected_config_keys"),
        ({"justification_regex": ""}, "justification_regex"),
    ],
)
def test_malformed_consumer_table_names_the_value(table: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        policy_from_table(table)


# --- report shape -------------------------------------------------------------------------------


def test_findings_are_sorted_and_render_as_text_and_json() -> None:
    lines = [
        AddedLine("src/pkg/b.py", 9, "x = 1  # noqa"),
        AddedLine("src/pkg/a.py", 2, "y = 2  # type: ignore"),
    ]

    report = _scan_lines(*lines)

    assert [finding.path for finding in report.findings] == ["src/pkg/a.py", "src/pkg/b.py"]
    first = report.findings[0]
    assert first.line_text() == "src/pkg/a.py:2: type-ignore: y = 2  # type: ignore"
    assert first.to_json() == {
        "path": "src/pkg/a.py",
        "line": 2,
        "rule": "type-ignore",
        "kind": "suppression",
        "detail": "y = 2  # type: ignore",
        "justified": False,
    }


def test_importing_gate_scan_does_not_load_tomllib() -> None:
    code = "import sys, coding_agent_playbook.hook_runtime.judges.gate_weakening; print('tomllib' in sys.modules)"

    assert run_python_probe(code) == "False"
