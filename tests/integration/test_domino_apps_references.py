"""The domino-apps skill's decision guide and its navigation (prU C-domino-apps-refs).

Two seams: the Domino probe as sync leaves it (the emitted skill lists the
reference under "References and examples" and ships its file), and the
reference file itself, an engine-written decision guide (D49): a title, at most
120 lines, no link and no URL, rule ids in plain text, routing to every rule the
mapping names. The expected open-when line and routed rule ids come from
``specs/prU-core-python-skills/mapping-domino-apps.md``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest

from tests._attributions import load_core_attributions
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
#: Hyphenated words in the guide that look like rule ids but are not.
_NOT_RULE_IDS: Final = frozenset({"domino-apps", "domino-jobs", "domino-agents", "domino-username"})
_RULE_ID_LIKE: Final = re.compile(r"(?<![\w-])domino-[a-z0-9-]+(?![\w-])")
_BACKTICKED_RULE_ID: Final = re.compile(r"`domino-[a-z0-9-]+`")
_LINK_OR_URL: Final = re.compile(r"\]\(|https?://|www\.")
_MAX_LINES: Final = 120


def _guide() -> str:
    return (core_skill_root(_SKILL) / _PATH).read_text(encoding="utf-8")


def test_domino_probe_lists_the_guide_with_its_open_when(domino_probe_repo: Path) -> None:
    skill_md = (domino_probe_repo / ".claude" / "skills" / _SKILL / "SKILL.md").read_text(
        encoding="utf-8"
    )
    listed = skill_md.partition("## References and examples\n")[2]
    lines = [line for line in listed.splitlines() if line.startswith("- [")]
    assert lines == [f"- [{_PATH}]({_PATH}) — Open when: {_OPEN_WHEN}"]


def test_domino_probe_ships_the_guide(domino_probe_repo: Path) -> None:
    emitted = domino_probe_repo / ".claude" / "skills" / _SKILL / _PATH
    assert emitted.read_bytes() == (core_skill_root(_SKILL) / _PATH).read_bytes()


def test_guide_has_the_decision_guide_shape() -> None:
    text = _guide()
    assert text.startswith("# "), "the guide opens with a title"
    assert len(text.splitlines()) <= _MAX_LINES
    assert not _LINK_OR_URL.search(text), "the guide holds no link and no URL"
    assert not _BACKTICKED_RULE_ID.search(text), "the guide backticks a rule id"


@pytest.mark.parametrize("rule_id", _ROUTES)
def test_guide_routes_to_each_mapped_rule(rule_id: str) -> None:
    assert re.search(rf"(?<![\w-]){re.escape(rule_id)}(?![\w-])", _guide()), rule_id


def test_every_rule_id_the_guide_names_exists() -> None:
    named = set(_RULE_ID_LIKE.findall(_guide())) - _NOT_RULE_IDS
    unknown = named - set(core_rules())
    assert not unknown, f"the guide names rule ids no skill ships: {sorted(unknown)}"


@pytest.mark.parametrize("rule_id", _SEE_FROM)
def test_rule_names_the_guide_by_bare_file_name(rule_id: str) -> None:
    rule = core_skill_root(_SKILL) / "rules" / f"{rule_id}.md"
    notes = rule.read_text(encoding="utf-8").partition("## Notes\n")[2]
    assert "app-troubleshooting.md" in notes


def test_guide_is_engine_written_in_attributions() -> None:
    assert _PATH in load_core_attributions().engine_written[_SKILL]
