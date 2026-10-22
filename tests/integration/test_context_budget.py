"""The D5 context budget, enforced on the reference probe (specs/prS-skills-context.md 6.8.11).

prU raises the description caps (D18 as amended by D54), gives the Domino probe
of ``tests/_budget_probe.py`` its own caps (D59) and measures the worst-case
"Where guidance lives" map with every core skill (D35).

Always-loaded context costs tokens on every turn, so CI caps it on the probe of
``tests/_budget_probe.py``: the rendered always rules plus the generated
"Where guidance lives" map, the whole ``AGENTS.md``, each core skill description
and the skill listing. Words are ``len(text.split())`` (what ``wc -w`` counts);
characters are ``len(description)``. The listing budget counts every bundled
plugin: the D13 description lint exempts plugin skills (D24), but their
descriptions still ride every turn.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.adapters.claude_code.hooks import CLAUDE_HEARTBEAT_LINE
from coding_agent_playbook.adapters.claude_code.paths import CLAUDE_MD_PATH, CLAUDE_RULES_PATH
from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.rendering.formats import render_for
from coding_agent_playbook.skills.document import where_entry, where_guidance_section
from coding_agent_playbook.sync.render import render_artifacts
from coding_agent_playbook.validation.context import SyncContext
from tests._budget_probe import (
    CORE_DESCRIPTION_MAX_CHARS,
    CORE_DESCRIPTIONS_MAX_CHARS,
    DOMINO_CORE_DESCRIPTIONS_MAX_CHARS,
    DOMINO_LISTING_MAX_CHARS,
    LISTING_MAX_CHARS,
    every_core_where_entry,
)
from tests._catalog import core_rules, core_skill_ids
from tests.core_skill_pins import PROBE_KINDS, ProbeKind, skills_off_probe
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from collections.abc import Mapping

pytestmark = pytest.mark.catalog

ALWAYS_RULES_MAX_WORDS: Final = 800
#: The always sections alone (spec 6.10 item 3): 240 after the D17 rewrite, raised to 450 by
#: prU D73 for the code-legibility and document-layout rules (D61); the 800 and 1,500 stay.
ALWAYS_SECTIONS_MAX_WORDS: Final = 450
ALWAYS_HEADINGS: Final = [
    "## Code legibility",
    "## Document layout",
    "## Project context",
    "## Python house style",
]
AGENTS_MD_MAX_WORDS: Final = 1500
#: Probe kind -> (core descriptions cap, core plus plugin listing cap): the standard
#: caps (D18 as amended by D54), the Domino probe's own (D59), and the standard ones
#: again on the authoring probe, with room left for forge (D78(19)).
PROBE_DESCRIPTION_CAPS: Final[Mapping[ProbeKind, tuple[int, int]]] = {
    "reference": (CORE_DESCRIPTIONS_MAX_CHARS, LISTING_MAX_CHARS),
    "domino": (DOMINO_CORE_DESCRIPTIONS_MAX_CHARS, DOMINO_LISTING_MAX_CHARS),
    "authoring": (CORE_DESCRIPTIONS_MAX_CHARS, LISTING_MAX_CHARS),
}
_GUARDRAILS_HEADING: Final = "## Guardrails"


def _words(text: str) -> int:
    return len(text.split())


def _agents_md(repo: Path) -> str:
    return (repo / "AGENTS.md").read_text(encoding="utf-8")


def _emitted_descriptions(repo: Path) -> dict[str, str]:
    """Every emitted skill description in the probe's skill roots, deduplicated by id."""
    descriptions: dict[str, str] = {}
    for root in NATIVE_SKILL_ROOTS:
        for skill_md in sorted((repo / root).glob("*/SKILL.md")):
            frontmatter, _ = split_frontmatter(skill_md.read_text(encoding="utf-8"))
            descriptions.setdefault(skill_md.parent.name, str(frontmatter["description"]))
    return descriptions


def _core_descriptions(repo: Path, probe: ProbeKind = "reference") -> dict[str, str]:
    """The emitted descriptions of the core skills ``repo``'s ``probe`` must activate.

    The Domino skills gate on ``domino_project`` (prU D63) and ``playbook-creator`` on
    ``playbook_layer`` (D70): the reference probe emits neither, the Domino and
    authoring probes each add their own.
    """
    core_ids = core_skill_ids() - skills_off_probe(probe)
    emitted = _emitted_descriptions(repo)
    assert core_ids <= set(emitted), (
        f"the probe lacks core skills {sorted(core_ids - set(emitted))}"
    )
    return {skill_id: emitted[skill_id] for skill_id in sorted(core_ids)}


def _always_text(repo: Path, fmt: str) -> tuple[list[str], str]:
    """The always sections in ``fmt``, by ``(priority, id)``, and the Where section, as sync renders."""
    rendered = render_artifacts(SyncContext.from_repo(repo))
    always = [rule for rule in rendered.rules if rule.frontmatter.scope == "always"]
    always.sort(key=lambda rule: (rule.frontmatter.priority, rule.frontmatter.id))
    sections = [
        render_for(
            r.source_path or Path(r.frontmatter.id), r.body, fmt, frontmatter=r.frontmatter.__dict__
        )
        for r in always
    ]
    entries = [entry for skill in rendered.skills if (entry := where_entry(skill)) is not None]
    return sections, where_guidance_section(entries)


def test_always_rules_within_800_words(reference_probe_repo: Path) -> None:
    """The always sections as AGENTS.md renders them (heading and ``---`` included), plus the map."""
    sections, where = _always_text(reference_probe_repo, "agents_md_section")
    assert len(sections) == len(ALWAYS_HEADINGS) and where, "the always rules and the map"
    total = sum(map(_words, sections)) + _words(where)
    assert total <= ALWAYS_RULES_MAX_WORDS, (
        f"always rules plus the Where section are {total} words; D5 allows {ALWAYS_RULES_MAX_WORDS}"
    )


def test_where_map_with_every_core_skill_within_800_words(reference_probe_repo: Path) -> None:
    """prU D35 worst case: the always sections plus a map line for EVERY core skill.

    The map is composed from every core skill that declares ``playbook.files``,
    whichever members the probe activates, so it keeps measuring as lanes add skills.
    """
    sections, _ = _always_text(reference_probe_repo, "agents_md_section")
    entries = every_core_where_entry()
    assert len(entries) >= 4, f"expected a map line per core skill, got {entries}"
    total = sum(map(_words, sections)) + _words(where_guidance_section(entries))
    assert total <= ALWAYS_RULES_MAX_WORDS, (
        f"always sections plus the {len(entries)}-line worst-case map are {total} words; "
        f"prU D35 keeps the cap at {ALWAYS_RULES_MAX_WORDS}: shorten the playbook.files phrases"
    )


def test_every_core_where_entry_reads_templated_skill_md(tmp_path: Path) -> None:
    """A skill shipped as ``SKILL.md.j2`` joins the worst-case map, as sync would list it."""
    for name, filename in (("plain", "SKILL.md"), ("templated", "SKILL.md.j2")):
        skill_dir = tmp_path / name
        skill_dir.mkdir()
        (skill_dir / filename).write_text(
            f"---\nid: {name}\nname: {name}\ndescription: d\n"
            f'playbook:\n  use_when: "w"\n  files: "{name} files"\n---\n\n# {name}\n',
            encoding="utf-8",
        )
    entries = every_core_where_entry(tmp_path)
    assert [(e.skill_id, e.files) for e in entries] == [
        ("plain", "plain files"),
        ("templated", "templated files"),
    ]


def test_always_sections_within_450_words(reference_probe_repo: Path) -> None:
    """The four always sections, without the map (D17, as amended by prU D73)."""
    sections, _ = _always_text(reference_probe_repo, "agents_md_section")
    headings = sorted(section.splitlines()[0] for section in sections)
    assert headings == ALWAYS_HEADINGS, headings
    total = sum(map(_words, sections))
    assert total <= ALWAYS_SECTIONS_MAX_WORDS, (
        f"the always sections are {total} words; prU D73 allows {ALWAYS_SECTIONS_MAX_WORDS}"
    )


def test_rules_file_holds_only_always_rules_the_where_section_and_the_heartbeat(
    reference_probe_repo: Path,
) -> None:
    """Every hook of the probe runs natively on Claude Code, so no guardrail section is due."""
    sections, where = _always_text(reference_probe_repo, "claude_md_section")
    rules_file = (reference_probe_repo / CLAUDE_RULES_PATH).read_text(encoding="utf-8")
    composed = "\n".join([*sections, where]) + "\n" + CLAUDE_HEARTBEAT_LINE + "\n"
    assert rules_file.endswith(composed)
    header = rules_file.removesuffix(composed)
    assert "## " not in header and header.count("\n") == 5, header
    stub = (reference_probe_repo / CLAUDE_MD_PATH).read_text(encoding="utf-8")
    assert stub.count("\n") == 4 and "# CLAUDE.md" in stub, stub


def test_agents_md_without_guardrails_within_1500_words(reference_probe_repo: Path) -> None:
    text = _agents_md(reference_probe_repo)
    assert _GUARDRAILS_HEADING in text, "the probe syncs with hooks on"
    words = _words(text.partition(_GUARDRAILS_HEADING)[0])
    assert words <= AGENTS_MD_MAX_WORDS, f"AGENTS.md before Guardrails is {words} words"


def test_agents_md_within_1500_words(reference_probe_repo: Path) -> None:
    """The whole file, hooks on: the Guardrails section is one line per hook (D6, E13)."""
    words = _words(_agents_md(reference_probe_repo))
    assert words <= AGENTS_MD_MAX_WORDS, f"AGENTS.md is {words} words"


def test_agents_md_guardrails_are_one_line_per_hook_with_an_advisory(
    reference_probe_repo: Path,
) -> None:
    """D6 acceptance (spec 8.10 item 2): no ``###`` block, and the CI-parity line names its checks.

    Counted against Continue's ``30-guardrail-<id>.md`` files, which the probe
    writes for exactly the on hooks with an advisory.
    """
    guardrails = _agents_md(reference_probe_repo).partition(_GUARDRAILS_HEADING)[2]
    lines = [line for line in guardrails.splitlines() if line.startswith("- `")]
    rules = reference_probe_repo / ".continue" / "rules"
    advised = sorted(
        p.name.removeprefix("30-guardrail-")[:-3] for p in rules.glob("30-guardrail-*")
    )
    assert [line[3 : line.index("`", 3)] for line in lines] == advised
    assert "\n### " not in guardrails
    [ci_line] = [line for line in lines if line.startswith("- `stop-ci-parity-gate`: ")]
    for check in ("`ruff check .`", "`ruff format --check .`", "the type checker", "the tests"):
        assert check in ci_line, ci_line


def _over_per_skill_cap(repo: Path, probe: ProbeKind = "reference") -> dict[str, int]:
    """The core skills of ``repo`` whose description exceeds the per-skill cap, with lengths."""
    lengths = {sid: len(text) for sid, text in _core_descriptions(repo, probe).items()}
    return {sid: n for sid, n in lengths.items() if n > CORE_DESCRIPTION_MAX_CHARS}


@pytest.mark.parametrize("probe", PROBE_KINDS)
def test_each_core_description_within_300_chars(probe: ProbeKind, probe_repo: Path) -> None:
    over = _over_per_skill_cap(probe_repo, probe)
    assert not over, f"core descriptions over {CORE_DESCRIPTION_MAX_CHARS} chars: {over}"


@pytest.mark.parametrize("probe", PROBE_KINDS)
def test_core_descriptions_total_within_the_probe_cap(probe: ProbeKind, probe_repo: Path) -> None:
    """prU D18/D54 on the standard and authoring probes, D59's own cap on the Domino probe."""
    cap = PROBE_DESCRIPTION_CAPS[probe][0]
    total = sum(map(len, _core_descriptions(probe_repo, probe).values()))
    assert total <= cap, f"core descriptions total {total} chars on the {probe} probe; cap {cap}"


@pytest.mark.parametrize("probe", PROBE_KINDS)
def test_core_and_plugin_descriptions_total_within_the_probe_listing_cap(
    probe: ProbeKind, probe_repo: Path
) -> None:
    """Every bundled plugin counts: the D24 lint exemption does not shrink the listing."""
    cap = PROBE_DESCRIPTION_CAPS[probe][1]
    descriptions = _emitted_descriptions(probe_repo)
    total = sum(map(len, descriptions.values()))
    assert total <= cap, (
        f"{len(descriptions)} skill descriptions total {total} on the {probe} probe; cap {cap}"
    )


def test_rules_file_and_agents_md_carry_no_member_rule_heading(reference_probe_repo: Path) -> None:
    members = [rule for rule in core_rules().values() if rule.frontmatter.skill is not None]
    for relative in ("AGENTS.md", CLAUDE_RULES_PATH):
        text = (reference_probe_repo / relative).read_text(encoding="utf-8")
        for rule in members:
            title = rule.body.lstrip().splitlines()[0]
            assert f"## {rule.frontmatter.name}\n" not in text, f"{relative}: {rule.frontmatter.id}"
            assert f"\n{title}\n" not in text, f"{relative} carries {rule.frontmatter.id}'s body"
