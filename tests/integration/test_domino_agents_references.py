"""The domino-agents skill's decision guides and their navigation (prU C-domino-agents-refs).

Two seams: the Domino probe as sync leaves it (the emitted skill lists each
reference under "References and examples" and ships its file), and the
reference files themselves. Their D49 shape (a title, at most 120 lines, no
links, no URLs) is the per-skill gate in ``tests/integration/test_core_skills.py``;
this module checks what is particular to these guides: the open-when lines, the
rule ids each routes to, and that every rule id they name exists or is pending.
The expected open-when lines and routed rule ids come from
``specs/prU-core-python-skills/mapping-domino-agents.md``. The file is named
``auth-by-call.md``, not ``credentials-by-call.md``: sync refuses to copy a
file whose name matches the secret-path policy (``*credentials*``), which the
ship test catches.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest

from tests._attributions import load_core_attributions
from tests._catalog import core_rules, core_skill_root
from tests._core_skill_layout import names_rule_id

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
#: The domino-jobs rule ids the guides name before those rules ship: they are in
#: mapping-domino-jobs.md and land with C-domino-jobs-01..04, which this ticket's
#: row in tickets.md lists as ordering dependencies. Any other id must already exist.
_PENDING_DOMINO_JOBS_IDS: Final = frozenset(
    {
        "domino-secrets-in-env-vars",
        "domino-paths-from-env",
        "domino-api-proxy-auth",
        "domino-env-var-names",
        "domino-job-exit-codes",
        "domino-job-entry-point",
        "domino-job-schedules",
        "domino-idempotent-jobs",
        "domino-mlflow-tracking",
    }
)
#: Hyphenated words in the guides that look like rule ids but are not.
_NOT_RULE_IDS: Final = frozenset({"domino-apps", "domino-jobs", "domino-username"})
_RULE_ID_LIKE: Final = re.compile(r"(?<![\w-])(?:domino|a2a)-[a-z0-9-]+(?![\w-])")
_BACKTICKED_RULE_ID: Final = re.compile(r"`(?:domino-agent|a2a)-[a-z0-9-]+`")


def test_domino_probe_lists_each_reference_with_its_open_when(domino_probe_repo: Path) -> None:
    skill_md = (domino_probe_repo / ".claude" / "skills" / _SKILL / "SKILL.md").read_text(
        encoding="utf-8"
    )
    listed = skill_md.partition("## References and examples\n")[2]
    # The section also lists examples/simple-agent-api (C-domino-agents-example);
    # this test pins only the references/ entries and their order.
    lines = [line for line in listed.splitlines() if line.startswith("- [references/")]
    assert lines == [f"- [{path}]({path}) — Open when: {text}" for path, text in _OPEN_WHEN.items()]


@pytest.mark.parametrize("path", list(_OPEN_WHEN))
def test_domino_probe_ships_each_reference(domino_probe_repo: Path, path: str) -> None:
    emitted = domino_probe_repo / ".claude" / "skills" / _SKILL / path
    assert emitted.read_bytes() == (core_skill_root(_SKILL) / path).read_bytes()


def test_reference_probe_ships_no_domino_agents_reference(reference_probe_repo: Path) -> None:
    assert not (reference_probe_repo / ".claude" / "skills" / _SKILL).exists()


@pytest.mark.parametrize("path", list(_OPEN_WHEN))
def test_guide_names_rule_ids_without_backticks(path: str) -> None:
    text = (core_skill_root(_SKILL) / path).read_text(encoding="utf-8")
    assert not _BACKTICKED_RULE_ID.search(text), f"{path} backticks a rule id"


@pytest.mark.parametrize("path", list(_ROUTES))
def test_guide_routes_to_its_mapped_rules(path: str) -> None:
    text = (core_skill_root(_SKILL) / path).read_text(encoding="utf-8")
    rules = core_skill_root(_SKILL) / "rules"
    for rule_id in _ROUTES[path]:
        assert (rules / f"{rule_id}.md").is_file(), rule_id
        assert names_rule_id(text, rule_id), f"{path} never names {rule_id}"


@pytest.mark.parametrize("path", list(_OPEN_WHEN))
def test_every_rule_id_a_guide_names_exists_or_is_pending(path: str) -> None:
    text = (core_skill_root(_SKILL) / path).read_text(encoding="utf-8")
    named = set(_RULE_ID_LIKE.findall(text)) - _NOT_RULE_IDS
    unknown = named - set(core_rules()) - _PENDING_DOMINO_JOBS_IDS
    assert not unknown, f"{path} names rule ids no skill ships or plans: {sorted(unknown)}"


def test_guides_are_engine_written_in_attributions() -> None:
    engine_written = load_core_attributions().engine_written[_SKILL]
    assert set(_OPEN_WHEN) <= set(engine_written)
