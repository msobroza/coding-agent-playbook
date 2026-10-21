"""gate-scan over secret- and SAST-scanner settings, on both forges (specs/prF-forge-adapter.md §14).

Any change to a scanner's own config file is flagged (``scanner-config-changed``),
and so is a CI file setting a variable that switches a scanner off or
excludes paths from it (``scanner-loosened-in-ci``).
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.hook_runtime.judges.gate_weakening import (
    AddedLine,
    RemovedLine,
    ScanPolicy,
    ScanReport,
    policy_from_table,
    scan,
)

POLICY = ScanPolicy()
SCANNER_CONFIGS = (
    ".gitleaks.toml",
    ".gitlab/secret-detection-ruleset.toml",
    ".gitlab/sast-ruleset.toml",
    ".github/secret_scanning.yml",
)


def _found(report: ScanReport) -> list[tuple[str, str, str]]:
    return [(finding.path, finding.rule, finding.detail) for finding in report.findings]


# --- scanner config files ----------------------------------------------------------------------


@pytest.mark.parametrize("path", SCANNER_CONFIGS)
def test_an_added_line_in_a_scanner_config_blocks(path: str) -> None:
    report = scan([AddedLine(path, 3, 'paths = ["fixtures/"]')], (), (), POLICY)

    assert _found(report) == [(path, "scanner-config-changed", f"{path} changed")]
    assert report.exit_code == 1


@pytest.mark.parametrize("path", SCANNER_CONFIGS)
def test_a_removed_line_in_a_scanner_config_blocks(path: str) -> None:
    report = scan((), [RemovedLine(path, 3, "[[rules]]")], (), POLICY)

    assert [finding.rule for finding in report.findings] == ["scanner-config-changed"]


def test_a_scanner_config_change_with_a_reason_is_justified() -> None:
    added = [AddedLine(".gitleaks.toml", 4, 'paths = ["tests/fixtures/"]  # fake keys only')]

    report = scan(added, (), (), POLICY)

    assert [finding.justified for finding in report.findings] == [True]


def test_a_nested_scanner_config_counts_and_a_lookalike_does_not() -> None:
    added = [
        AddedLine("services/api/.gitleaks.toml", 1, "[allowlist]"),
        AddedLine("docs/sast-ruleset.toml", 1, "[semgrep]"),
    ]

    report = scan(added, (), (), POLICY)

    assert [finding.path for finding in report.findings] == ["services/api/.gitleaks.toml"]


# --- CI variables that switch a scanner off ----------------------------------------------------

GITLAB_CI = ".gitlab-ci.yml"
WORKFLOW = ".github/workflows/ci.yml"


def _ci_rules(path: str, *texts: str, removed: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    added = [AddedLine(path, n, text) for n, text in enumerate(texts, 1)]
    gone = [RemovedLine(path, n, text) for n, text in enumerate(removed, 1)]
    report = scan(added, gone, (), POLICY)
    return [(finding.rule, finding.detail) for finding in report.findings]


@pytest.mark.parametrize(
    ("line", "detail"),
    [
        ('  SAST_DISABLED: "true"', "sets SAST_DISABLED: true"),
        ("    SECRET_DETECTION_DISABLED: 1", "sets SECRET_DETECTION_DISABLED: 1"),
        (
            '  SAST_EXCLUDED_PATHS: "spec, test, src/legacy"',
            "sets SAST_EXCLUDED_PATHS: spec, test, src/legacy",
        ),
        ("  SECRET_DETECTION_EXCLUDED_PATHS: docs/", "sets SECRET_DETECTION_EXCLUDED_PATHS: docs/"),
        ("  DS_EXCLUDED_PATHS: 'vendor'", "sets DS_EXCLUDED_PATHS: vendor"),
    ],
)
@pytest.mark.parametrize("path", [GITLAB_CI, ".gitlab/ci/security.yml", WORKFLOW])
def test_a_ci_file_setting_a_scanner_variable_blocks(path: str, line: str, detail: str) -> None:
    assert _ci_rules(path, line) == [("scanner-loosened-in-ci", detail)]


@pytest.mark.parametrize(
    "line",
    [
        '  # SAST_DISABLED: "true"',
        "    - if: $SAST_DISABLED == 'true'",
        '    - echo "$SECRET_DETECTION_EXCLUDED_PATHS"',
        "  SAST_DISABLED_REASON: none",
        "  MY_SAST_DISABLED: true",
    ],
)
def test_a_line_that_only_mentions_a_scanner_variable_is_clean(line: str) -> None:
    assert _ci_rules(GITLAB_CI, line) == []


@pytest.mark.parametrize(
    "line",
    [
        '  SAST_DISABLED: "false"',
        "  SECRET_DETECTION_DISABLED: 0",
        "  SAST_DISABLED: False",
        '  SECRET_DETECTION_DISABLED: ""',
        '  SAST_EXCLUDED_PATHS: ""',
    ],
)
def test_a_scanner_variable_left_switched_on_is_clean(line: str) -> None:
    """GitLab 16.0+ skips a job only on 'true' or '1'; an empty exclusion list excludes nothing."""
    assert _ci_rules(GITLAB_CI, line) == []


@pytest.mark.parametrize(
    ("line", "detail"),
    [
        ("  SAST_DISABLED: yes", "sets SAST_DISABLED: yes"),  # any value up to GitLab 15.11
        ('  SECRET_DETECTION_DISABLED: "TRUE"', "sets SECRET_DETECTION_DISABLED: TRUE"),
        ("  SAST_DISABLED:", "sets SAST_DISABLED: (value on the next lines)"),  # expanded form
        ("  SAST_EXCLUDED_PATHS:", "sets SAST_EXCLUDED_PATHS: (value on the next lines)"),
    ],
)
def test_an_unclear_scanner_variable_value_blocks(line: str, detail: str) -> None:
    assert _ci_rules(GITLAB_CI, line) == [("scanner-loosened-in-ci", detail)]


def test_a_scanner_variable_outside_ci_files_is_clean() -> None:
    assert _ci_rules("docs/ci.yml", '  SAST_DISABLED: "true"') == []


def test_a_moved_scanner_variable_is_clean_and_a_changed_one_blocks() -> None:
    moved = _ci_rules(
        GITLAB_CI, '    SAST_EXCLUDED_PATHS: "spec"', removed=("  SAST_EXCLUDED_PATHS: spec",)
    )
    grown = _ci_rules(
        GITLAB_CI, '  SAST_EXCLUDED_PATHS: "spec, src"', removed=("  SAST_EXCLUDED_PATHS: spec",)
    )

    assert moved == []
    assert grown == [("scanner-loosened-in-ci", "sets SAST_EXCLUDED_PATHS: spec, src")]


def test_a_scanner_variable_with_a_reason_is_justified() -> None:
    added = [AddedLine(GITLAB_CI, 3, '  SAST_EXCLUDED_PATHS: "tests/fixtures"  # vendored samples')]

    report = scan(added, (), (), POLICY)

    assert [(f.rule, f.justified) for f in report.findings] == [("scanner-loosened-in-ci", True)]


def test_consumer_ci_config_globs_are_ci_files_too() -> None:
    policy = policy_from_table({"ci_config_globs": ["ci/*.gitlab-ci.yml"]})
    added = [AddedLine("ci/deploy.gitlab-ci.yml", 2, '  SECRET_DETECTION_DISABLED: "true"')]

    report = scan(added, (), (), policy)

    assert [finding.rule for finding in report.findings] == ["scanner-loosened-in-ci"]
