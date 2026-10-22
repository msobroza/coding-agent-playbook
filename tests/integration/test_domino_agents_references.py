"""The domino-agents skill's decision guides and their navigation (prU C-domino-agents-refs).

Two seams: the Domino probe as sync leaves it (the emitted skill lists each
reference under "References and examples" and ships its file), and the
reference files themselves, which are engine-written decision guides (D49):
at most 120 lines, rule ids in plain text, no links and no URLs. The expected
open-when lines and routed rule ids come from
``specs/prU-core-python-skills/mapping-domino-agents.md``. The mapping's
``credentials-by-call.md`` ships as ``auth-by-call.md``: sync refuses to copy a
file whose name matches the secret-path policy (``*credentials*``), which the
ship test catches.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest

from tests._attributions import load_core_attributions
from tests._catalog import core_skill_root

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SKILL: Final = "domino-agents"
#: Each reference's open-when line, in the order the mapping lists them.
_OPEN_WHEN: Final = {
    "references/agent-lifecycle.md": (
        "Planning where agent code runs (workspace, Job, scheduled Job or deployed agent)"
        " or which SDK name a Domino release uses."
    ),
    "references/auth-by-call.md": (
        "Code calls an LLM provider, a Domino-hosted model, another App or agent, or the"
        " Domino API, and the right credential is unclear."
    ),
}
#: The rule ids each guide routes to (the mapping's "Routes to" column).
_ROUTES: Final = {
    "references/agent-lifecycle.md": (
        "domino-agent-app-factory",
        "domino-agent-settings",
        "domino-agent-config-file",
        "domino-agent-trace-entrypoint",
        "domino-agent-sdk-names",
        "domino-agent-dev-eval-job",
        "domino-agent-evaluators",
        "domino-agent-eval-out-of-band",
        "domino-agent-prod-eval-watermark",
    ),
    "references/auth-by-call.md": (
        "domino-agent-llm-keys",
        "domino-agent-access-token",
        "domino-agent-endpoint-auth",
        "domino-agent-redact-traces",
        "domino-agent-settings",
        "a2a-client-deadlines",
    ),
}
#: D49's cap on an internal reference.
_MAX_LINES: Final = 120
_LINK: Final = re.compile(r"\]\(")
_URL: Final = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://|\bwww\.")
_BACKTICKED_RULE_ID: Final = re.compile(r"`(?:domino-agent|a2a)-[a-z0-9-]+`")


def test_domino_probe_lists_each_reference_with_its_open_when(domino_probe_repo: Path) -> None:
    skill_md = (domino_probe_repo / ".claude" / "skills" / _SKILL / "SKILL.md").read_text(
        encoding="utf-8"
    )
    listed = skill_md.partition("## References and examples\n")[2]
    lines = [line for line in listed.splitlines() if line.startswith("- [")]
    assert lines == [f"- [{path}]({path}) — Open when: {text}" for path, text in _OPEN_WHEN.items()]


@pytest.mark.parametrize("path", list(_OPEN_WHEN))
def test_domino_probe_ships_each_reference(domino_probe_repo: Path, path: str) -> None:
    emitted = domino_probe_repo / ".claude" / "skills" / _SKILL / path
    assert emitted.read_bytes() == (core_skill_root(_SKILL) / path).read_bytes()


def test_reference_probe_ships_no_domino_agents_reference(reference_probe_repo: Path) -> None:
    assert not (reference_probe_repo / ".claude" / "skills" / _SKILL).exists()


@pytest.mark.parametrize("path", list(_OPEN_WHEN))
def test_guide_is_a_short_plain_text_decision_guide(path: str) -> None:
    text = (core_skill_root(_SKILL) / path).read_text(encoding="utf-8")
    assert text.startswith("# "), path
    assert len(text.splitlines()) <= _MAX_LINES, path
    assert not _LINK.search(text), f"{path} links: rule ids and files are named in plain text"
    assert not _URL.search(text), f"{path} holds a URL"
    assert not _BACKTICKED_RULE_ID.search(text), f"{path} backticks a rule id"


@pytest.mark.parametrize("path", list(_ROUTES))
def test_guide_routes_to_its_mapped_rules(path: str) -> None:
    text = (core_skill_root(_SKILL) / path).read_text(encoding="utf-8")
    rules = core_skill_root(_SKILL) / "rules"
    for rule_id in _ROUTES[path]:
        assert (rules / f"{rule_id}.md").is_file(), rule_id
        assert re.search(rf"\b{re.escape(rule_id)}\b", text), f"{path} never names {rule_id}"


def test_guides_are_engine_written_in_attributions() -> None:
    engine_written = load_core_attributions().engine_written[_SKILL]
    assert set(_OPEN_WHEN) <= set(engine_written)
