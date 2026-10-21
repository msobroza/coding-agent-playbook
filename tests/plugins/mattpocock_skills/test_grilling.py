"""T02's skill-specific tests: grilling, grill-me, grill-with-docs and domain-modeling.

specs/prT-mattpocock-skills.md sections 7.1 and 9.3 and appendix A.T02. ``test_gates.py``
already gates every present skill; this file pins what only these four have: each new text
as an exact substring, each replaced upstream text gone, and Matt's remaining text byte for
byte (D4). The upstream tree is not needed: reversing the listed edits on a shipped file
must give the bytes whose SHA-256 is pinned below, so an unlisted change fails here, and a
re-pin (D5) that alters one of these files fails loudly, as ``LICENSE_SHA256`` does for the
licence.

Appendix A.T02 names ``test_skill_loads.py`` and ``test_glossary_fallback.py``; section 7.1
puts those assertions in the lane's own file, so no two lanes edit one test file. They are
``test_skill_loads_name_model_invoked_skills`` and
``test_glossary_mentions_carry_context_fallback`` below.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import pytest

from tests.plugins.mattpocock_skills._expectations import (
    FINAL_IDS,
    GUARD_LINE,
    LOAD_RE,
    PLUGIN_ROOT,
    SKILLS_ROOT,
    USER_INVOKED_IDS,
    skill_files,
    split_skill,
    vendored_text,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.catalog

_SKILL_IDS: Final = ("domain-modeling", "grill-me", "grill-with-docs", "grilling")
#: D21's clause, once for a code-formatted mention, once for the map, once for the
#: description, which has no code spans.
_CONTEXT: Final = " (or `CONTEXT.md` if the repo already has one)"
_CONTEXT_MAP: Final = " (or `CONTEXT-MAP.md` if the repo already has one)"
_CONTEXT_PLAIN: Final = " (or CONTEXT.md if the repo already has one)"


@dataclass(frozen=True)
class Edit:
    """One listed change of appendix A.T02: an upstream excerpt and the text that replaces it.

    ``before`` is empty for a pure insertion. Example: ``Edit("Change 3", "old", "new")``.
    """

    label: str
    before: str
    after: str


@dataclass(frozen=True)
class VendoredFile:
    """A shipped file, the SHA-256 of its upstream v1.3.1 bytes and the edits made to it."""

    skill_id: str
    path: str
    upstream_sha256: str
    edits: tuple[Edit, ...] = ()

    @property
    def case_id(self) -> str:
        return f"{self.skill_id}/{self.path}"


def _id_edit(skill_id: str) -> Edit:
    """Change 1 of every skill (D11): ``id`` becomes the first frontmatter key."""
    before = f"---\nname: {skill_id}\n"
    return Edit("Change 1: id first (D11)", before, f"---\nid: {skill_id}\nname: {skill_id}\n")


def _fallback(label: str, anchor: str, tail: str, clause: str = _CONTEXT) -> Edit:
    """A D21 insertion: ``clause`` goes between ``anchor`` and the upstream words after it."""
    return Edit(f"{label} (D21)", anchor + tail, anchor + clause + tail)


_GUARD: Final = Edit("Change 2: guard line (D19)", "", f"{GUARD_LINE}\n\n")
_VENDORED: Final = (
    VendoredFile(
        "grill-with-docs",
        "SKILL.md",
        "7de372c13488f1ee96cc11cd8907b56b6809cc93eef776eeddd37de6b6cbe3fe",
        (
            _id_edit("grill-with-docs"),
            _GUARD,
            Edit(
                "Change 3: two separate loads (D17, D18.1)",
                'Call the Skill tool twice, for "grilling" and "domain-modeling".',
                "Load the `grilling` skill, and load the `domain-modeling` skill.",
            ),
        ),
    ),
    VendoredFile(
        "grill-me",
        "SKILL.md",
        "caaf8b8de1684f96e26b28f3c29189db5c89cce4b73e1c93d86164f66ef88637",
        (
            _id_edit("grill-me"),
            _GUARD,
            Edit(
                "Change 3: load grilling (D17)",
                'Call the Skill tool with "grilling".',
                "Load the `grilling` skill.",
            ),
        ),
    ),
    VendoredFile(
        "grilling",
        "SKILL.md",
        "10ff989e7498b23b5acb49d5048f11dcd906757d2f79c5cdf8a00001381296f2",
        (
            _id_edit("grilling"),
            Edit(
                "Change 2: L26 background agent only (D18.2)",
                "dispatch a sub-agent to find it; don't ask the user",
                "dispatch a background agent to find it if your harness can run one; otherwise "
                "look the fact up yourself before you send the round. Don't ask the user",
            ),
            Edit(
                "Change 2: L26 block only after a dispatch (D18.2)",
                "Don't block on it:",
                "If you dispatched a background agent, don't block on it:",
            ),
            Edit(
                "Change 2: L26 wait for the background agent (D18.2)",
                "wait for the sub-agent to report",
                "wait for the background agent to report",
            ),
        ),
    ),
    VendoredFile(
        "domain-modeling",
        "SKILL.md",
        "7b925d7b1e341a2eeae33ad68a8a8c0ab889a38ddd22a7598e4c240e5a7556a3",
        (
            _id_edit("domain-modeling"),
            _fallback("L3", "a GLOSSARY.md", ", or recording or editing an ADR.", _CONTEXT_PLAIN),
            _fallback("L8", "`GLOSSARY.md`", " for vocabulary is not this skill:"),
            _fallback(
                "L24", "`GLOSSARY-MAP.md`", " exists at the root, the repo has", _CONTEXT_MAP
            ),
            _fallback("L40", "If no `GLOSSARY.md`", " exists, create one when the first term is"),
            _fallback("L46", "existing language in `GLOSSARY.md`", ", call it out immediately."),
            _fallback("L62", "update `GLOSSARY.md`", " right there."),
            Edit(
                "Change 4: L62 link (D10)",
                "(./GLOSSARY-FORMAT.md)",
                "(references/GLOSSARY-FORMAT.md)",
            ),
            _fallback(
                "L64", "`GLOSSARY.md`", " should be totally devoid of implementation details."
            ),
            Edit("Change 5: L74 link (D10)", "(./ADR-FORMAT.md)", "(references/ADR-FORMAT.md)"),
        ),
    ),
    VendoredFile(
        "domain-modeling",
        "references/GLOSSARY-FORMAT.md",
        "21dcc40cdec8e151a829b98ab1517c1867bc444e3665134a98c6983411996801",
        (
            _fallback("L34", "One `GLOSSARY.md`", " at the repo root."),
            _fallback("L36", "A `GLOSSARY-MAP.md`", " at the repo root lists the", _CONTEXT_MAP),
            _fallback("L56", "- If `GLOSSARY-MAP.md`", " exists, read it to find", _CONTEXT_MAP),
            _fallback("L57", "- If only a root `GLOSSARY.md`", " exists, single context"),
        ),
    ),
    VendoredFile(
        "domain-modeling",
        "references/ADR-FORMAT.md",
        "944c92aa790e8fbdc9199640b170979abb8a34ba8d0fe18c2a01a63bce140ca0",
    ),
)
_EDIT_CASES: Final = [(vendored, edit) for vendored in _VENDORED for edit in vendored.edits]
_REPLACING: Final = [(vendored, edit) for vendored, edit in _EDIT_CASES if edit.before]


def _case_ids(cases: list[tuple[VendoredFile, Edit]]) -> list[str]:
    return [f"{vendored.case_id}: {edit.label}" for vendored, edit in cases]


def _shipped(vendored: VendoredFile) -> str:
    """The shipped text of ``vendored``, read as bytes so a newline change shows."""
    return vendored_text(vendored.skill_id, vendored.path)


# --- The listed edits and nothing else (D4, section 9.1 common acceptance) -------


@pytest.mark.parametrize(("vendored", "edit"), _EDIT_CASES, ids=_case_ids(_EDIT_CASES))
def test_every_listed_new_text_is_present_exactly_once(vendored: VendoredFile, edit: Edit) -> None:
    found = _shipped(vendored).count(edit.after)
    assert found == 1, f"{vendored.case_id}: {edit.label}: {edit.after!r} occurs {found} times"


@pytest.mark.parametrize(("vendored", "edit"), _REPLACING, ids=_case_ids(_REPLACING))
def test_every_replaced_upstream_text_is_gone(vendored: VendoredFile, edit: Edit) -> None:
    assert edit.before not in _shipped(vendored), (
        f"{vendored.case_id}: {edit.label}: upstream text {edit.before!r} is still there"
    )


@pytest.mark.parametrize("vendored", _VENDORED, ids=[v.case_id for v in _VENDORED])
def test_the_rest_of_each_file_is_upstream_v1_3_1_byte_for_byte(vendored: VendoredFile) -> None:
    text = _shipped(vendored)
    for edit in vendored.edits:
        text = text.replace(edit.after, edit.before)
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == vendored.upstream_sha256, (
        f"{vendored.case_id} differs from upstream v1.3.1 by more than the listed edits"
    )


# --- Layout and frontmatter (D10, D11, D19, D21) ---------------------------------

_REFERENCES: Final = {
    "domain-modeling": ["ADR-FORMAT.md", "GLOSSARY-FORMAT.md", "LICENSE"],
    "grill-me": ["LICENSE"],
    "grill-with-docs": ["LICENSE"],
    "grilling": ["LICENSE"],
}


@pytest.mark.parametrize("skill_id", _SKILL_IDS)
def test_skill_directory_holds_skill_md_and_the_expected_references(skill_id: str) -> None:
    skill = SKILLS_ROOT / skill_id
    assert sorted(p.name for p in skill.iterdir()) == ["SKILL.md", "references"], (
        "agents/openai.yaml is not shipped (D10) and no format file stays at the skill root"
    )
    assert sorted(p.name for p in (skill / "references").iterdir()) == _REFERENCES[skill_id]


@pytest.mark.parametrize("skill_id", _SKILL_IDS)
def test_no_skill_tool_text_remains(skill_id: str) -> None:
    files = skill_files(skill_id)
    assert files, f"skills/{skill_id}/ is missing"
    holding = [p.name for p in files if "Skill tool" in p.read_text("utf-8")]
    assert holding == [], "a Claude Code tool name is replaced by a capability sentence (D17)"


@pytest.mark.parametrize("skill_id", _SKILL_IDS)
def test_frontmatter_is_id_name_description_and_the_user_invoked_marker(skill_id: str) -> None:
    frontmatter, _ = split_skill(skill_id)
    marker = ["disable-model-invocation"] if skill_id in USER_INVOKED_IDS else []
    assert list(frontmatter) == ["id", "name", "description", *marker]
    assert all(frontmatter[key] is True for key in marker)


def test_domain_modelings_description_grows_by_the_d21_clause_only() -> None:
    frontmatter, _ = split_skill("domain-modeling")
    assert len(str(frontmatter["description"])) == 151 + len(_CONTEXT_PLAIN) == 195


# --- grill-me and grill-with-docs: the guard (D19) and the loads (D17, D18.1) -----

_PAIR_LOADS: Final = {
    "grill-me": "Load the `grilling` skill.",
    "grill-with-docs": "Load the `grilling` skill, and load the `domain-modeling` skill.",
}
_EXPECTED_LOADS: Final = {
    "domain-modeling": [],
    "grill-me": ["grilling"],
    "grill-with-docs": ["grilling", "domain-modeling"],
    "grilling": [],
}


@pytest.mark.parametrize(("skill_id", "loads"), _PAIR_LOADS.items())
def test_user_invoked_pair_body_is_the_guard_line_then_the_loads(skill_id: str, loads: str) -> None:
    _, body = split_skill(skill_id)
    assert body == f"\n{GUARD_LINE}\n\n{loads}\n"


def test_grill_with_docs_loads_two_skills_in_two_separate_loads_with_no_order_implied() -> None:
    _, body = split_skill("grill-with-docs")
    sentences = [line for line in body.split("\n") if LOAD_RE.search(line)]
    assert sentences == [_PAIR_LOADS["grill-with-docs"]]
    assert len(LOAD_RE.findall(sentences[0])) == 2, "two separate loads in one sentence"
    ordering = re.search(r"\b(?:then|first|second|next|after|before)\b", sentences[0], re.I)
    assert ordering is None, "upstream names no order: its 'twice' only means one skill per call"


@pytest.mark.parametrize("skill_id", _SKILL_IDS)
def test_skill_loads_name_model_invoked_skills(skill_id: str) -> None:
    """Upstream's invariant: no skill loads a user-invoked one. Targets are checked against
    the D9 ids, not against the directories present, so no other lane waits for T02."""
    text = (SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8")
    targets = LOAD_RE.findall(text)
    assert targets == _EXPECTED_LOADS[skill_id]
    assert set(targets) <= FINAL_IDS - USER_INVOKED_IDS


@pytest.mark.parametrize("target", ["domain-modeling", "grilling"])
def test_the_pairs_load_targets_ship_in_this_plugin_and_are_model_invoked(target: str) -> None:
    frontmatter, _ = split_skill(target)
    assert "disable-model-invocation" not in frontmatter


# --- grilling: fact-finding through a background agent only (D18.2) ---------------


def test_grilling_fact_lookup_is_capability_gated() -> None:
    _, body = split_skill("grilling")
    assert (
        "dispatch a background agent to find it if your harness can run one; "
        "otherwise look the fact up yourself before you send the round"
    ) in body
    assert "If you dispatched a background agent, don't block on it" in body
    assert "sub-agent" not in body
    assert "subagent" not in body.lower()


def test_grilling_blocks_on_nothing_unless_a_background_agent_was_dispatched() -> None:
    _, body = split_skill("grilling")
    assert body.count("block on it") == 1, "'Don't block on it' lives on the background path only"
    assert "Don't block on it" not in body


def test_grilling_keeps_its_round_template_and_open_round_wording() -> None:
    _, body = split_skill("grilling")
    assert "❓ **Q1** - **<question title>**" in body  # U+2753, as upstream has it
    assert "➡️ <your recommended answer>" in body  # U+27A1 U+FE0F
    assert "depends on another question still open in this round" in body


# --- domain-modeling: the D21 fallback and the moved references (D10, D21) --------

#: The line of the two D21 files whose wording already covers both names: after L56-L57,
#: "neither" means neither name, and the file created is still GLOSSARY.md (A.T02.2 Change 8).
_FALLBACK_EXEMPT: Final = frozenset(
    {
        (
            "references/GLOSSARY-FORMAT.md",
            "- If neither exists, create a root `GLOSSARY.md` lazily when the first term is resolved",
        )
    }
)
_MENTIONS: Final = (
    (re.compile(r"(?<![\w-])GLOSSARY\.md"), "CONTEXT.md"),
    (re.compile(r"(?<![\w-])GLOSSARY-MAP\.md"), "CONTEXT-MAP.md"),
)
_ATX_HEADING_RE: Final = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")


def _lines_outside_fences(text: str) -> Iterator[tuple[int, str]]:
    """``(1-based number, line)`` of every line outside a fenced block, fences excluded.

    The fence rule of ``links.py``: a line starting (left-stripped) with three backticks or
    three tildes opens a block, and a line starting with the same three characters closes it.
    """
    fence = ""
    for number, line in enumerate(text.split("\n"), 1):
        head = line.lstrip()
        if fence:
            fence = "" if head.startswith(fence) else fence
        elif head.startswith(("```", "~~~")):
            fence = head[:3]
        else:
            yield number, line


@pytest.mark.parametrize(
    ("skill_id", "relative_file"),
    [
        pytest.param("domain-modeling", "SKILL.md", id="SKILL.md"),
        pytest.param("domain-modeling", "references/GLOSSARY-FORMAT.md", id="GLOSSARY-FORMAT.md"),
    ],
)
def test_glossary_mentions_carry_context_fallback(skill_id: str, relative_file: str) -> None:
    text = (SKILLS_ROOT / skill_id / relative_file).read_text(encoding="utf-8")
    bare: list[str] = []
    exempted: set[str] = set()
    for number, line in _lines_outside_fences(text):
        for pattern, fallback in _MENTIONS:
            if _ATX_HEADING_RE.match(line) or not pattern.search(line) or fallback in line:
                continue
            if (relative_file, line) in _FALLBACK_EXEMPT:
                exempted.add(line)
            else:
                bare.append(f"{relative_file}:{number}: no {fallback} on {line!r}")
    assert bare == [], "D21: a mention of the glossary file names the CONTEXT.md fallback too"
    expected = {line for name, line in _FALLBACK_EXEMPT if name == relative_file}
    assert exempted == expected, "an exemption that matches no line is stale (two-way check)"


#: Text the spec keeps as upstream has it on purpose (A.T02.1, A.T02.2 Change 8).
_UNCHANGED: Final = (
    ("grill-with-docs", "SKILL.md", "creates docs (ADR's and glossary) as we go."),
    ("domain-modeling", "SKILL.md", "### Update GLOSSARY.md inline"),
    ("domain-modeling", "SKILL.md", "Do not treat `GLOSSARY.md` as a spec, a scratch pad"),
    ("domain-modeling", "references/GLOSSARY-FORMAT.md", "# GLOSSARY.md Format"),
    ("domain-modeling", "references/GLOSSARY-FORMAT.md", "[Ordering](./src/ordering/GLOSSARY.md)"),
    ("domain-modeling", "references/GLOSSARY-FORMAT.md", "[Billing](./src/billing/GLOSSARY.md)"),
    (
        "domain-modeling",
        "references/GLOSSARY-FORMAT.md",
        "[Fulfillment](./src/fulfillment/GLOSSARY.md)",
    ),
)


@pytest.mark.parametrize(("skill_id", "relative_file", "excerpt"), _UNCHANGED)
def test_text_kept_as_upstream_has_it_on_purpose(
    skill_id: str, relative_file: str, excerpt: str
) -> None:
    text = (SKILLS_ROOT / skill_id / relative_file).read_text(encoding="utf-8")
    assert excerpt in text, f"{skill_id}/{relative_file} lost {excerpt!r}, kept on purpose"


def test_domain_modelings_links_point_into_references_and_keep_their_text() -> None:
    skill = SKILLS_ROOT / "domain-modeling"
    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", (skill / "SKILL.md").read_text("utf-8"))
    assert links == [
        ("GLOSSARY-FORMAT.md", "references/GLOSSARY-FORMAT.md"),
        ("ADR-FORMAT.md", "references/ADR-FORMAT.md"),
    ]
    assert all((skill / target).is_file() for _, target in links)


# --- ATTRIBUTIONS.md: each section lists its changes (section 9.1) ----------------


def _attribution_section(skill_id: str) -> str:
    """The text of ``### <skill_id>`` in ``ATTRIBUTIONS.md``, whitespace-normalised."""
    text = (PLUGIN_ROOT / "ATTRIBUTIONS.md").read_text(encoding="utf-8")
    found = re.search(rf"^### {re.escape(skill_id)}\n(.*?)(?=^### |\Z)", text, re.M | re.S)
    assert found, f"no '### {skill_id}' section in ATTRIBUTIONS.md"
    return " ".join(found.group(1).split())


def _origin(skill_id: str, group: str) -> str:
    return f"Upstream `skills/{group}/{skill_id}/`; synced as `.agents/skills/{skill_id}/`."


def _cites(file: str, *lines: int) -> tuple[str, ...]:
    """How a section cites an upstream line: ```SKILL.md` L7 (v1.3.1)``."""
    return tuple(f"`{file}` L{n} (v1.3.1)" for n in lines)


_ALWAYS_RECORDED: Final = ("`references/LICENSE`: added", "`agents/openai.yaml`: not shipped")
_USER_ONLY_POLICY: Final = "policy.allow_implicit_invocation: false"
_ATTRIBUTION_FACTS: Final = {
    "domain-modeling": (
        _origin("domain-modeling", "engineering"),
        *_cites("SKILL.md", 2, 3, 8, 24, 40, 46, 62, 64, 74),
        *_cites("references/GLOSSARY-FORMAT.md", 34, 36, 56, 57),
        "from 151 to 195 characters",
        "`references/ADR-FORMAT.md`: moved",
    ),
    "grill-me": (
        _origin("grill-me", "productivity"),
        *_cites("SKILL.md", 2, 6, 7),
        GUARD_LINE,
        _USER_ONLY_POLICY,
    ),
    "grill-with-docs": (
        _origin("grill-with-docs", "engineering"),
        *_cites("SKILL.md", 2, 6, 7),
        GUARD_LINE,
        "two separate loads with no order implied",
        _USER_ONLY_POLICY,
    ),
    "grilling": (_origin("grilling", "productivity"), *_cites("SKILL.md", 2, 26)),
}


@pytest.mark.parametrize("skill_id", _SKILL_IDS)
def test_attributions_section_lists_every_change_of_the_skill(skill_id: str) -> None:
    facts = (*_ATTRIBUTION_FACTS[skill_id], *_ALWAYS_RECORDED, "Continue:")
    section = _attribution_section(skill_id)
    assert [fact for fact in facts if fact not in section] == [], (
        f"### {skill_id} in ATTRIBUTIONS.md does not record these"
    )
    banned = re.findall(r"\b(?:packs?|ported|porting)\b", section, re.I)
    assert banned == [], f"### {skill_id}: CONTEXT.md says 'vendored content', never {banned}"
