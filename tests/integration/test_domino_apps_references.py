"""The domino-apps skill's decision guide and its navigation (prU C-domino-apps-refs).

Two seams: the Domino probe as sync leaves it (the emitted skill lists the
reference under "References and examples" and ships its file), and the
reference file itself, an engine-written decision guide (D49): a title, at most
120 lines, no link and no URL, rule ids in plain text, routing to every rule the
mapping names, each symptom table carrying the evidence that confirms its
cause. ``_OPEN_WHEN``, ``_ROUTES``, ``_SEE_FROM`` and ``_SOURCES`` are a pinned
snapshot of the reference row of
``specs/prU-core-python-skills/mapping-domino-apps.md`` (a generated file the
tests do not parse): a mapping change must update them by hand.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest

from tests._attributions import MappingRow, load_core_attributions
from tests._catalog import core_rules, core_skill_root

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SKILL: Final = "domino-apps"
_PATH: Final = "references/app-troubleshooting.md"
_OPEN_WHEN: Final = (
    "An App never reaches Running, shows a blank page or a 404/502/504/413, loses data"
    " or sessions, or changed after a restart."
)
#: The rule ids the guide routes to (the mapping's "Routes to" column).
_ROUTES: Final = (
    "domino-app-bind-host-port",
    "domino-app-launch-script",
    "domino-app-url-prefix",
    "domino-app-relative-urls",
    "domino-app-dash",
    "domino-app-flask",
    "domino-app-streamlit",
    "domino-app-shiny",
    "domino-app-viewer-identity",
    "domino-app-verify-viewer-jwt",
    "domino-app-publisher-data-rights",
    "domino-app-starter-settings",
    "domino-app-endpoint-auth",
    "domino-app-production-server",
    "domino-app-proxy-limits",
    "domino-app-external-resources",
    "domino-app-replica-state",
    "domino-app-external-persistence",
    "domino-app-concurrent-writes",
    "domino-app-publish-from-commit",
    "domino-app-deployment-record",
    "domino-app-workspace-preview",
)
#: The rules that name the guide in their Notes (the mapping's "see" column).
_SEE_FROM: Final = (
    "domino-app-bind-host-port",
    "domino-app-url-prefix",
    "domino-app-launch-script",
    "domino-app-proxy-limits",
)
#: The domino-docs pages the mapping names as the guide's sources, plus a29497,
#: whose sizing the mapping's coverage table sends to the guide.
_SOURCES: Final = frozenset(
    {
        "user_guide/bb4b24",
        "user_guide/f47536",
        "admin_guide/71d6ad",
        "admin_guide/6469bf",
        "user_guide/2f5c0c",
        "user_guide/cfc79e",
        "user_guide/a29497",
    }
)
#: Support-bundle files the guide names as evidence (user_guide/bb4b24).
_BUNDLE_FILES: Final = (
    "execution.log",
    "executor.log",
    "logjam-*.log",
    "kubernetes-events.json",
    "nginx.log",
    "run.json",
    "run-history.json",
    "execution.yaml",
)
_EVIDENCE_HEADER: Final = "| Evidence | Likely cause | Rules |"
_BACKTICKED_RULE_ID: Final = re.compile(r"`domino-[a-z0-9-]+`")
_LINK_OR_URL: Final = re.compile(r"\]\(|https?://|www\.")
_MAX_LINES: Final = 120


def _whole_id(pattern: str) -> re.Pattern[str]:
    """Match ``pattern`` as a whole hyphenated id, never inside a longer one."""
    return re.compile(rf"(?<![\w-]){pattern}(?![\w-])")


_RULE_ID_LIKE: Final = _whole_id(r"domino-[a-z0-9-]+")


def _guide_path() -> Path:
    return core_skill_root(_SKILL) / _PATH


def _guide() -> str:
    return _guide_path().read_text(encoding="utf-8")


def _sections() -> dict[str, str]:
    """The guide's level-two sections, by heading."""
    parts = _guide().split("\n## ")[1:]
    return {part.partition("\n")[0]: part.partition("\n")[2] for part in parts}


def _row(symptom: str) -> list[str]:
    """The cells of the table row whose first cell is ``symptom``."""
    for line in _guide().splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.startswith("| ") and cells[0] == symptom:
            return cells
    raise AssertionError(f"no row for {symptom!r}")


def _domino_docs_rows() -> tuple[MappingRow, ...]:
    return load_core_attributions().sources["domino-docs"].skills[_SKILL].rows


def test_domino_probe_lists_the_guide_with_its_open_when(domino_probe_repo: Path) -> None:
    skill_md = (domino_probe_repo / ".claude" / "skills" / _SKILL / "SKILL.md").read_text(
        encoding="utf-8"
    )
    listed = skill_md.partition("## References and examples\n")[2]
    lines = [line for line in listed.splitlines() if line.startswith("- [")]
    assert lines == [f"- [{_PATH}]({_PATH}) — Open when: {_OPEN_WHEN}"]


def test_domino_probe_ships_the_guide(domino_probe_repo: Path) -> None:
    emitted = domino_probe_repo / ".claude" / "skills" / _SKILL / _PATH
    assert emitted.read_bytes() == _guide_path().read_bytes()


def test_guide_has_the_decision_guide_shape() -> None:
    text = _guide()
    assert text.startswith("# "), "the guide opens with a title"
    assert len(text.splitlines()) <= _MAX_LINES
    assert not _LINK_OR_URL.search(text), "the guide holds no link and no URL"
    assert not _BACKTICKED_RULE_ID.search(text), "the guide backticks a rule id"


@pytest.mark.parametrize("rule_id", _ROUTES)
def test_guide_routes_to_each_mapped_rule(rule_id: str) -> None:
    assert _whole_id(re.escape(rule_id)).search(_guide()), rule_id


def test_every_rule_id_the_guide_names_exists() -> None:
    unknown = set(_RULE_ID_LIKE.findall(_guide())) - set(core_rules())
    assert not unknown, f"the guide names rule ids no skill ships: {sorted(unknown)}"


def test_where_to_look_first_names_the_support_bundle_files() -> None:
    first = _sections()["Where to look first"]
    missing = [name for name in _BUNDLE_FILES if name not in first]
    assert not missing, f"'Where to look first' omits bundle files: {missing}"


def test_every_symptom_table_carries_its_evidence() -> None:
    tables = {
        heading: body
        for heading, body in _sections().items()
        if heading != "Where to look first" and "| --- |" in body
    }
    assert len(tables) >= 5
    for heading, body in tables.items():
        assert _EVIDENCE_HEADER in body, f"{heading!r} has no Evidence column"


def test_model_call_failures_sit_under_a_heading_that_names_them() -> None:
    owner = [heading for heading, body in _sections().items() if "| A model call fails" in body]
    assert len(owner) == 1
    assert "model call" in owner[0]


def test_environment_failures_route_to_the_deployment_record() -> None:
    rules = _row("A package install or import error")[-1]
    assert "domino-app-deployment-record" in rules
    assert "domino-app-publish-from-commit" not in rules


@pytest.mark.parametrize("rule_id", _SEE_FROM)
def test_rule_names_the_guide_by_bare_file_name(rule_id: str) -> None:
    rule = core_skill_root(_SKILL) / "rules" / f"{rule_id}.md"
    notes = rule.read_text(encoding="utf-8").partition("## Notes\n")[2]
    assert "app-troubleshooting.md" in notes


def test_guide_is_engine_written_in_attributions() -> None:
    assert _PATH in load_core_attributions().engine_written[_SKILL]


def test_exactly_the_mapped_sources_credit_the_guide() -> None:
    crediting = {row.upstream for row in _domino_docs_rows() if _PATH in row.targets}
    assert crediting == _SOURCES


def test_attribution_rows_have_no_stray_punctuation() -> None:
    stray = [row.upstream for row in _domino_docs_rows() if ".;" in row.changes]
    assert not stray, f"rows with '.;': {stray}"
