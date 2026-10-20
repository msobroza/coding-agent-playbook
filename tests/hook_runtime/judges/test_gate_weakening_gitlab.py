"""gate-scan over GitLab CI files (specs/prF-forge-adapter.md §10.3, Q52, Q54).

The scanner compares a CI file's text before and after the change with line
patterns only (the hook runtime may not import YAML): a job, a ``script:`` /
``before_script:`` / ``after_script:`` item or an ``include:`` entry that is
gone and not re-added in the same file blocks like a removed GitHub workflow
step, and so does the ``playbook-ci`` job being removed or made optional.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.hook_runtime.judges.gate_weakening import (
    DEFAULT_CI_CONFIG_GLOBS,
    AddedLine,
    ConfigPair,
    ScanPolicy,
    ScanReport,
    is_config_path,
    policy_from_table,
    scan,
)

POLICY = ScanPolicy()
CI_FILE = ".gitlab-ci.yml"

PIPELINE = """\
stages: [test]

variables:
  PIP_CACHE_DIR: .cache/pip

include:
  - local: .gitlab/ci/lint.yml
  - template: Jobs/SAST.gitlab-ci.yml

.python: &python
  image: python:3.12

unit-tests:
  <<: *python
  stage: test
  before_script:
    - pip install -e ".[dev]"
  script:
    - pytest -q
    - mypy
  after_script:
    - echo done

playbook-ci:
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  variables:
    GIT_DEPTH: 0
  script:
    - git fetch origin "$CI_MERGE_REQUEST_TARGET_BRANCH_NAME"
    - playbook ci --base "$CI_MERGE_REQUEST_DIFF_BASE_SHA"
"""


def _scan_ci(before: str | None, after: str | None, path: str = CI_FILE) -> ScanReport:
    return scan((), (), [ConfigPair(path, before, after)], POLICY)


def _found(report: ScanReport) -> list[tuple[str, str]]:
    return [(finding.rule, finding.detail) for finding in report.findings]


def test_an_unchanged_pipeline_is_clean() -> None:
    assert _scan_ci(PIPELINE, PIPELINE).findings == ()


def test_a_removed_job_blocks() -> None:
    after = PIPELINE.replace(
        'unit-tests:\n  <<: *python\n  stage: test\n  before_script:\n    - pip install -e ".[dev]"\n'
        "  script:\n    - pytest -q\n    - mypy\n  after_script:\n    - echo done\n\n",
        "",
    )

    report = _scan_ci(PIPELINE, after)

    assert _found(report) == [("gitlab-ci-job-removed", "job 'unit-tests' removed")]
    assert report.exit_code == 1
    assert report.findings[0].kind == "loosening"


def test_a_moved_job_is_not_removed() -> None:
    start = PIPELINE.index("playbook-ci:")
    after = PIPELINE[start:] + "\n" + PIPELINE[:start]

    assert _scan_ci(PIPELINE, after).findings == ()


def test_global_keywords_and_hidden_jobs_are_not_jobs() -> None:
    after = PIPELINE.replace("stages: [test]\n", "").replace(
        "variables:\n  PIP_CACHE_DIR: .cache/pip\n", ""
    )
    after = after.replace(".python: &python\n  image: python:3.12\n", "")

    assert _scan_ci(PIPELINE, after).findings == ()


def test_a_removed_script_item_blocks_in_each_script_section() -> None:
    after = (
        PIPELINE.replace("    - mypy\n", "")
        .replace('    - pip install -e ".[dev]"\n', "    - pip install -e .\n")
        .replace("    - echo done\n", "    - echo finished\n")
    )

    report = _scan_ci(PIPELINE, after)

    assert _found(report) == [
        ("gitlab-ci-script-removed", "script item 'echo done' removed"),
        ("gitlab-ci-script-removed", "script item 'mypy' removed"),
        ("gitlab-ci-script-removed", "script item 'pip install -e \".[dev]\"' removed"),
    ]


def test_a_script_item_moved_to_another_job_or_given_a_comment_is_kept() -> None:
    after = PIPELINE.replace("    - mypy\n", "    - pytest -q  # the unit suite\n").replace(
        "    - pytest -q\n", "    - mypy\n", 1
    )

    assert _scan_ci(PIPELINE, after).findings == ()


def test_a_removed_job_reports_only_the_job_not_its_items() -> None:
    start = PIPELINE.index("playbook-ci:")

    report = _scan_ci(PIPELINE, PIPELINE[:start])

    assert _found(report) == [("gitlab-ci-job-removed", "job 'playbook-ci' removed")]


def test_inline_and_block_scalar_scripts_are_items() -> None:
    before = (
        "lint:\n  script: ruff check .\n\nbuild:\n  script:\n    - |\n      make\n      make test\n"
    )
    after = "lint:\n  script: echo skipped\n\nbuild:\n  script:\n    - |\n      make\n"

    report = _scan_ci(before, after)

    assert _found(report) == [
        ("gitlab-ci-script-removed", "script item 'make\\nmake test' removed"),
        ("gitlab-ci-script-removed", "script item 'ruff check .' removed"),
    ]


def test_default_and_deprecated_global_scripts_are_watched() -> None:
    before = "default:\n  before_script:\n    - make deps\nafter_script:\n  - make report\n"

    report = _scan_ci(before, "default:\n  image: python:3.12\n")

    assert [detail for _, detail in _found(report)] == [
        "script item 'make deps' removed",
        "script item 'make report' removed",
    ]


def test_a_removed_include_entry_blocks() -> None:
    before = (
        "include:\n"
        "  - local: .gitlab/ci/lint.yml\n"
        "  - template: Jobs/SAST.gitlab-ci.yml\n"
        "  - component: $CI_SERVER_FQDN/org/secret-detection/secret-detection@1.0\n"
        "  - remote: 'https://example.com/ci.yml'\n"
        "  - project: group/ci-config\n"
        "    ref: v2\n"
        "    file:\n"
        "      - /templates/test.yml\n"
        "      - /templates/scan.yml\n"
        "  - 'shared/extra.yml'\n"
    )
    after = (
        "include:\n"
        "  - local: .gitlab/ci/lint.yml\n"
        "  - project: group/ci-config\n"
        "    ref: v3\n"
        "    file:\n"
        "      - /templates/test.yml\n"
    )

    report = _scan_ci(before, after)

    assert [detail for _, detail in _found(report)] == [
        "include '/templates/scan.yml' removed",
        "include 'component: $CI_SERVER_FQDN/org/secret-detection/secret-detection@1.0' removed",
        "include 'remote: https://example.com/ci.yml' removed",
        "include 'shared/extra.yml' removed",
        "include 'template: Jobs/SAST.gitlab-ci.yml' removed",
    ]
    assert {rule for rule, _ in _found(report)} == {"gitlab-ci-include-removed"}


def test_an_inline_include_is_an_entry() -> None:
    report = _scan_ci("include: '.gitlab/ci/lint.yml'\n", "stages: [test]\n")

    assert _found(report) == [
        ("gitlab-ci-include-removed", "include '.gitlab/ci/lint.yml' removed")
    ]


@pytest.mark.parametrize(
    ("added", "mark"),
    [
        ("  allow_failure: true\n", "allow_failure: true"),
        ("  when: manual\n", "when: manual"),
        ("  allow_failure:\n    exit_codes: [1]\n", "allow_failure:"),
    ],
)
def test_making_the_playbook_ci_job_optional_blocks(added: str, mark: str) -> None:
    after = PIPELINE.replace("playbook-ci:\n", "playbook-ci:\n" + added)

    report = _scan_ci(PIPELINE, after)

    assert _found(report) == [("playbook-ci-job-loosened", f"job 'playbook-ci' gains {mark}")]


def test_a_never_rule_on_the_playbook_ci_job_blocks() -> None:
    rule = '    - if: $CI_PIPELINE_SOURCE == "merge_request_event"\n'
    after = PIPELINE.replace(rule, "    - when: never\n" + rule)

    report = _scan_ci(PIPELINE, after)

    assert _found(report) == [("playbook-ci-job-loosened", "job 'playbook-ci' gains when: never")]


def test_allow_failure_false_or_another_job_going_manual_is_no_loosening() -> None:
    after = PIPELINE.replace("playbook-ci:\n", "playbook-ci:\n  allow_failure: false\n")
    after = after.replace("unit-tests:\n", "unit-tests:\n  when: manual\n")

    assert _scan_ci(PIPELINE, after).findings == ()


def test_a_reason_comment_naming_the_job_justifies_its_removal() -> None:
    start = PIPELINE.index("unit-tests:")
    end = PIPELINE.index("playbook-ci:")
    after = PIPELINE[:start] + PIPELINE[end:]
    reason = AddedLine(CI_FILE, 12, "# unit-tests moved to the nightly pipeline project")

    report = scan([reason], (), [ConfigPair(CI_FILE, PIPELINE, after)], POLICY)

    assert [finding.justified for finding in report.findings] == [True]
    assert report.exit_code == 0


def test_a_new_ci_file_loses_nothing_and_a_deleted_one_loses_every_job() -> None:
    assert _scan_ci(None, PIPELINE).findings == ()

    report = _scan_ci(PIPELINE, None)

    assert [rule for rule, _ in _found(report)] == [
        "gitlab-ci-job-removed",
        "gitlab-ci-job-removed",
        "gitlab-ci-include-removed",
        "gitlab-ci-include-removed",
    ]


# --- which files ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".gitlab-ci.yml", True),
        ("services/api/.gitlab-ci.yml", True),
        (".gitlab/ci/lint.yml", True),
        (".gitlab/ci/jobs/test.yaml", True),
        (".gitlab/ci/README.md", False),
        ("ci/.gitlab/ci/lint.yml", False),
        ("gitlab-ci.yml", False),
    ],
)
def test_the_watched_gitlab_ci_files(path: str, expected: bool) -> None:
    assert is_config_path(path) is expected
    removed_job = _scan_ci("lint:\n  script: [ruff]\n", "", path=path)
    assert bool(removed_job.findings) is expected


def test_ci_config_globs_extend_the_watched_files() -> None:
    policy = policy_from_table({"ci_config_globs": ["ci/*.gitlab-ci.yml"]})
    pair = ConfigPair("ci/deploy.gitlab-ci.yml", "deploy:\n  script: [make deploy]\n", "")

    assert policy.ci_config_globs == (*DEFAULT_CI_CONFIG_GLOBS, "ci/*.gitlab-ci.yml")
    assert is_config_path("ci/deploy.gitlab-ci.yml", policy)
    assert not is_config_path("ci/deploy.gitlab-ci.yml")
    assert [f.rule for f in scan((), (), [pair], policy).findings] == ["gitlab-ci-job-removed"]


@pytest.mark.parametrize("value", ["ci/*.yml", [""], [1]])
def test_malformed_ci_config_globs_name_the_value(value: object) -> None:
    with pytest.raises(ValueError, match="ci_config_globs"):
        policy_from_table({"ci_config_globs": value})
