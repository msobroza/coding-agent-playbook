"""The GitLab release jobs (ADR 0014): each release's metric bundle on a GitLab Release.

``release-report`` builds the bundle with ``scripts/release_report.py`` and keeps
it as a never-expiring artifact; ``release`` creates the GitLab Release
``v<version>`` with release-cli, one asset link per bundle file, or updates it
through the Releases API when it already exists. Both run on a version tag
pipeline, or on a manual web/API pipeline of the default branch with a
``RELEASE_VERSION`` variable, which backfills an older tag (its own
``.gitlab-ci.yml`` has no release jobs). These tests pin that wiring, the
GitHub ``publish-release`` job's counterpart, and that the docs jobs keep their
rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
GITLAB_CI = ROOT / ".gitlab-ci.yml"
REPORT_JOB = "release-report"
RELEASE_JOB = "release"
RELEASE_RULES = [
    {"if": r"$CI_COMMIT_TAG =~ /^v\d+\.\d+\.\d+$/"},
    {
        "if": "$CI_PIPELINE_SOURCE =~ /^(web|api)$/ && $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH"
        " && $RELEASE_VERSION"
    },
]
TAG_REPORT_CALL = (
    'python scripts/release_report.py --version "$V" --checkout . --out release-report'
)
BACKFILL_REPORT_CALL = (
    'python scripts/release_report.py --version "$V" --checkout tag-tree --out release-report'
)
ASSET_URL = 'ASSET_BASE="$CI_PROJECT_URL/-/jobs/$REPORT_JOB_ID/artifacts/file/release-report"'


class _GitLabLoader(yaml.SafeLoader):
    """A safe loader that reads GitLab's ``!reference [job, key]`` tag as its list."""


def _reference(loader: yaml.SafeLoader, node: yaml.SequenceNode) -> list[Any]:
    return loader.construct_sequence(node)


_GitLabLoader.add_constructor("!reference", _reference)


def _ci() -> dict[str, Any]:
    data = yaml.load(GITLAB_CI.read_text(encoding="utf-8"), Loader=_GitLabLoader)
    assert isinstance(data, dict), f"{GITLAB_CI} must be a YAML mapping, got {data!r}"
    return data


def _job(name: str) -> dict[str, Any]:
    ci = _ci()
    assert name in ci, f"missing job {name!r} in {GITLAB_CI}; keys: {sorted(ci)}"
    job: dict[str, Any] = ci[name]
    return job


def _rules(name: str) -> list[dict[str, Any]]:
    job = _job(name)
    template = job.get("extends")
    rules: list[dict[str, Any]] = job.get("rules") or _job(str(template)).get("rules", [])
    return rules


def _script(name: str) -> str:
    return "\n".join(str(line) for line in _job(name)["script"])


def test_release_jobs_run_only_on_version_tags() -> None:
    # A version tag pipeline, or a manual default-branch pipeline naming one.
    assert _rules(REPORT_JOB) == RELEASE_RULES
    assert _rules(RELEASE_JOB) == RELEASE_RULES


def test_release_needs_the_report_job() -> None:
    release = _job(RELEASE_JOB)

    assert release["needs"] == [REPORT_JOB]
    assert _job(REPORT_JOB)["stage"] == "build"
    assert _ci()["stages"].index("build") < _ci()["stages"].index(release["stage"])


def test_images_are_variables() -> None:
    variables = _ci()["variables"]

    assert variables["RELEASE_CLI_IMAGE"] == "registry.gitlab.com/gitlab-org/release-cli:latest"
    assert _job(REPORT_JOB)["image"] == "$PYTHON_IMAGE"
    assert _job(RELEASE_JOB)["image"] == "$RELEASE_CLI_IMAGE"


def test_the_report_artifacts_never_expire() -> None:
    artifacts = _job(REPORT_JOB)["artifacts"]

    assert artifacts["paths"] == ["release-report/"]
    assert artifacts["expire_in"] == "never"
    assert artifacts["reports"]["dotenv"] == "release.env"
    assert "REPORT_JOB_ID=$CI_JOB_ID" in _script(REPORT_JOB)


def test_the_report_reads_the_tag_tree() -> None:
    script = _script(REPORT_JOB)

    assert 'V="${CI_COMMIT_TAG#v}"' in script
    assert TAG_REPORT_CALL in script
    assert 'V="$RELEASE_VERSION"' in script
    assert 'git ls-remote --exit-code --tags origin "refs/tags/v$V"' in script
    assert 'git worktree add --detach tag-tree "v$V"' in script
    assert BACKFILL_REPORT_CALL in script
    assert "python -m pip install -e . matplotlib" in script


def test_release_links_every_bundle_file_and_never_creates_a_tag() -> None:
    script = _script(RELEASE_JOB)

    assert "for f in release-report/*; do" in script
    assert ASSET_URL in script
    assert "release-cli create" in script
    # release-cli's --ref defaults to $CI_COMMIT_SHA, which would create a
    # missing tag on the default branch's HEAD; the tag itself as the ref
    # cannot resolve when the tag is missing, so create fails instead.
    assert (
        'release-cli create --name "$RELEASE_TAG" --tag-name "$RELEASE_TAG" --ref "$RELEASE_TAG"'
        in script
    )
    assert script.count("--ref") == 1
    assert _job(RELEASE_JOB)["variables"]["GIT_STRATEGY"] == "none"


def test_release_updates_an_existing_release() -> None:
    script = _script(RELEASE_JOB)

    assert "--request PUT" in script
    assert "JOB-TOKEN: $CI_JOB_TOKEN" in script
    assert 'RELEASE_API="$CI_API_V4_URL/projects/$CI_PROJECT_ID/releases/$RELEASE_TAG"' in script
    assert '"$RELEASE_API"' in script


def test_a_rerun_replaces_the_asset_links() -> None:
    # The PUT changes only the notes: the links of the previous report job are
    # deleted and one link per current bundle file is posted.
    script = _script(RELEASE_JOB)

    assert '"$RELEASE_API/assets/links?per_page=100"' in script
    assert "grep -o '\"id\":[0-9]*'" in script
    assert (
        '--request DELETE --header "JOB-TOKEN: $CI_JOB_TOKEN" "$RELEASE_API/assets/links/$link_id"'
        in script
    )
    assert '--request POST --header "JOB-TOKEN: $CI_JOB_TOKEN"' in script
    assert '--data-urlencode "name=$name" --data-urlencode "url=$ASSET_BASE/$name"' in script
    assert script.index("--request PUT") < script.index("--request DELETE")
    assert script.index("--request DELETE") < script.index("--request POST")


def test_the_docs_jobs_are_untouched() -> None:
    assert _job("docs")["rules"] == [{"if": '$CI_PIPELINE_SOURCE == "merge_request_event"'}]
    assert _job("pages")["rules"] == [{"if": "$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH"}]
    assert _job("docs")["stage"] == "test"
    assert _job("pages")["stage"] == "deploy"
