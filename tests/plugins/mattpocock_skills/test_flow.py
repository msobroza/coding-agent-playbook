"""T04's gate: wayfinder, implement and implement-spec as vendored content.

specs/prT-mattpocock-skills.md appendix A.T04 and section 9.5. Each change of
A.T04 is written here once, as data: the upstream text it replaces and the
plugin text it becomes. The tests assert every new text as an exact substring,
the absence of every replaced upstream text, and, by undoing the listed changes,
that every other byte is still upstream v1.3.1's (the pinned SHA-256 of each
upstream ``SKILL.md``). The shared gate (``test_gates.py``) already covers URLs,
imposed tools, Claude-only names, layout, licence copies and the guard line.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Final

import pytest

from tests.plugins.mattpocock_skills._expectations import (
    FINAL_IDS,
    GUARD_LINE,
    LOAD_RE,
    PLUGIN_ROOT,
    SKILLS_ROOT,
    USER_INVOKED_IDS,
    split_skill,
)

pytestmark = pytest.mark.catalog

_MODEL_INVOKED_IDS: Final = FINAL_IDS - USER_INVOKED_IDS
_SETUP_LINE: Final = "tell the user to run `/setup-matt-pocock-skills`"


@dataclass(frozen=True)
class LineChange:
    """One upstream line replaced whole by its plugin line (an A.T04 change)."""

    where: str
    upstream: str
    plugin: str


@dataclass(frozen=True)
class Insertion:
    """Text added between ``before`` and ``after``; upstream has ``before + after``."""

    where: str
    before: str
    inserted: str
    after: str


@dataclass(frozen=True)
class VendoredSkill:
    """One T04 skill: its upstream digest and the changes A.T04 lists for it."""

    skill_id: str
    upstream_sha256: str
    frontmatter: str
    insertions: tuple[Insertion, ...]
    line_changes: tuple[LineChange, ...]
    load_targets: frozenset[str]


def _id_and_guard(skill_id: str, first_body_text: str) -> tuple[Insertion, Insertion]:
    """Changes 1 and 2 of every T04 skill: ``id`` first (D11), then the guard line (D19)."""
    return (
        Insertion("SKILL.md L2 (D11)", "---\n", f"id: {skill_id}\n", f"name: {skill_id}\n"),
        Insertion("SKILL.md before L7 (D19)", "---\n\n", f"{GUARD_LINE}\n\n", first_body_text),
    )


WAYFINDER: Final = VendoredSkill(
    skill_id="wayfinder",
    upstream_sha256="fee6e1d0c50f0e736b4ef8a599060c959afae904c9a97d82c97f049fcc3aa0f1",
    frontmatter=(
        "---\n"
        "id: wayfinder\n"
        "name: wayfinder\n"
        "description: Plan a huge chunk of work (more than one agent session can hold) as a"
        " shared map of decision tickets on your issue tracker, and resolve them one at a time"
        " until the way to the destination is clear.\n"
        "disable-model-invocation: true\n"
        "---\n"
    ),
    insertions=_id_and_guard(
        "wayfinder", "A loose idea has arrived, too big for one agent session"
    ),
    line_changes=(
        LineChange(
            "SKILL.md L77 (D17, D18.4)",
            "- **Research** (AFK): Reading documentation, third-party APIs, or local resources"
            " like knowledge bases to surface a fact a decision waits on. Resolved by a subagent"
            ' that calls the Skill tool with "research". Use when knowledge outside the current'
            " working directory is required.",
            "- **Research** (AFK): Reading documentation, third-party APIs, or local resources"
            " like knowledge bases to surface a fact a decision waits on. Resolved by a subagent"
            " that loads the `research` skill; if your harness cannot run subagents, the session"
            " working through the map loads the `research` skill itself (charting leaves the"
            " ticket on the frontier). Use when knowledge outside the current working directory"
            " is required.",
        ),
        LineChange(
            "SKILL.md L78 (D8, D17)",
            "- **Prototype** (HITL): Raise the fidelity of the discussion by making a cheap,"
            " rough, concrete artifact to react to (an outline, a rough take, a stub, or UI/logic"
            ' code) by calling the Skill tool with "prototype". Links the prototype as an asset.'
            ' Use when "how should it look" or "how should it behave" is the key question.',
            "- **Prototype** (HITL): Raise the fidelity of the discussion by making a cheap,"
            " rough, concrete artifact to react to (an outline, a rough take, a stub, or UI/logic"
            " code) by loading the `throwaway-prototype` skill. Links the prototype as an asset."
            ' Use when "how should it look" or "how should it behave" is the key question.',
        ),
        LineChange(
            "SKILL.md L79 (D17, D18.1)",
            "- **Grilling** (HITL): Conversation. The default case. Always call the Skill tool"
            ' twice, for "grilling" and "domain-modeling".',
            "- **Grilling** (HITL): Conversation. The default case. Always load the `grilling`"
            " skill, and load the `domain-modeling` skill.",
        ),
        LineChange(
            "SKILL.md L111 (D17, D18.1)",
            '1. **Name the destination.** Call the Skill tool twice, for "grilling" and'
            ' "domain-modeling", to pin down what this map is finding its way to: the spec,'
            " decision, or change. The destination fixes the scope, so it's settled first.",
            "1. **Name the destination.** Load the `grilling` skill, and load the"
            " `domain-modeling` skill, to pin down what this map is finding its way to: the spec,"
            " decision, or change. The destination fixes the scope, so it's settled first.",
        ),
        LineChange(
            "SKILL.md L115 (D17, D18.4)",
            "5. **Fire the research subagents.** For each `research` ticket you just created,"
            ' spin up a subagent that calls the Skill tool with "research" to resolve it in'
            " parallel, capturing its findings on a throwaway `research/<name>` branch with a"
            " context pointer from the ticket.",
            "5. **Fire the research subagents.** If your harness can run subagents, then for each"
            " `research` ticket you just created, spin up a subagent that loads the `research`"
            " skill to resolve it in parallel, capturing its findings on a throwaway"
            " `research/<name>` branch with a context pointer from the ticket. Otherwise, leave"
            " the research tickets on the frontier for a later session.",
        ),
        LineChange(
            "SKILL.md L120 (D13, D14)",
            "User invokes with a map (URL or number). A ticket is **optional**: without one, you"
            " pick the next decision, not the user.",
            "User invokes with a map (URL, number, or path). A ticket is **optional**: without"
            " one, you pick the next decision, not the user.",
        ),
        LineChange(
            "SKILL.md L124 (D17, D18.1)",
            "3. Resolve it. **Zoom as needed**: fetch the full body of any related or closed"
            " ticket on demand; call the Skill tool for whichever skills the `## Notes` block"
            ' names. If in doubt, call the Skill tool twice, for "grilling" and'
            ' "domain-modeling".',
            "3. Resolve it. **Zoom as needed**: fetch the full body of any related or closed"
            " ticket on demand; load each skill the `## Notes` block names. If in doubt, load the"
            " `grilling` skill, and load the `domain-modeling` skill.",
        ),
    ),
    load_targets=frozenset({"research", "throwaway-prototype", "grilling", "domain-modeling"}),
)

IMPLEMENT: Final = VendoredSkill(
    skill_id="implement",
    upstream_sha256="6d3fd9e83b8f36e5213854779db49b256a457a7ebb4a503e53fa7dcff696adc3",
    frontmatter=(
        "---\n"
        "id: implement\n"
        "name: implement\n"
        'description: "Implement a piece of work based on a spec or set of tickets."\n'
        "disable-model-invocation: true\n"
        "---\n"
    ),
    insertions=_id_and_guard("implement", "Implement the work described by the user"),
    line_changes=(
        LineChange(
            "SKILL.md L9 (D17)",
            "Use /tdd where possible, at pre-agreed seams.",
            "Load the `tdd` skill and use it where possible, at pre-agreed seams.",
        ),
        LineChange(
            "SKILL.md L13 (D8, D17)",
            "Once done, use /code-review to review the work.",
            "Once done, load the `two-axis-review` skill to review the work.",
        ),
    ),
    load_targets=frozenset({"tdd", "two-axis-review"}),
)

_IMPLEMENTER_LINE: Final = (
    "**Implementer subagents** should be run in the background where possible for maximum"
    " concurrency."
)
_SEQUENTIAL_FALLBACK: Final = (
    "If your harness cannot run subagents, do each subagent's job below yourself, one ticket at"
    " a time: build each frontier ticket on its own branch off the integration branch and merge"
    " it in before taking the next. Each merge is a stop-and-resume point: when your context is"
    " getting full, stop there and tell the user to start a fresh context and run"
    " `/implement-spec` again. A resumed run reuses the integration branch and skips the tickets"
    " already merged into it."
)

IMPLEMENT_SPEC: Final = VendoredSkill(
    skill_id="implement-spec",
    upstream_sha256="7a22dd2e60b8fcece478ced9d2533582adf3520d695acd3ab715341535c9e56d",
    frontmatter=(
        "---\n"
        "id: implement-spec\n"
        "name: implement-spec\n"
        'description: "Implement the result of /to-spec and /to-tickets in code."\n'
        "disable-model-invocation: true\n"
        "---\n"
    ),
    insertions=(
        *_id_and_guard("implement-spec", "You have been provided a spec."),
        Insertion(
            "SKILL.md after L17 (D17, D18.5)",
            f"{_IMPLEMENTER_LINE}\n\n",
            f"{_SEQUENTIAL_FALLBACK}\n\n",
            "## Steps\n",
        ),
    ),
    line_changes=(
        LineChange(
            "SKILL.md L25 (D18.5)",
            "3. Create the integration branch. If the issue tracker closes work through PRs, or"
            " the user asks for one, open a draft PR after the first merge in step 5 (a branch"
            " with no commits ahead of main can't open one), marked as closing the spec and"
            " tickets.",
            "3. Create the integration branch. If the issue tracker closes work through PRs, or"
            " the user asks for one, open a draft PR, as the issue tracker describes, after the"
            " first merge in step 5 (a branch with no commits ahead of main can't open one),"
            " marked as closing the spec and tickets.",
        ),
        LineChange(
            "SKILL.md L29 (D17)",
            "   - calls the Skill tool with `tdd` to build the ticket;",
            "   - loads the `tdd` skill to build the ticket;",
        ),
        LineChange(
            "SKILL.md L36 (D8, D17)",
            "7. Once all tickets are complete, call the Skill tool with `code-review` on the"
            " integration branch. Fix all issues raised by the code review in a single"
            " **implementer subagent**.",
            "7. Once all tickets are complete, load the `two-axis-review` skill and run it on the"
            " integration branch. Fix all issues raised by the code review in a single"
            " **implementer subagent**.",
        ),
    ),
    load_targets=frozenset({"tdd", "two-axis-review"}),
)

T04_SKILLS: Final[tuple[VendoredSkill, ...]] = (WAYFINDER, IMPLEMENT, IMPLEMENT_SPEC)

#: Tracker lines T04 keeps verbatim, relying on T03's local seed and the plugin
#: always rule for D16 (A.T04 notes, "Tracker text this ticket relies on").
TRACKER_LINES_KEPT: Final[dict[str, tuple[str, ...]]] = {
    "wayfinder": (
        "Every map and ticket is an issue, so it has a **name**: its title.",
        "The map is a single issue on this repo's issue tracker, labelled `wayfinder:map`, the"
        " canonical artifact. Its tickets are child issues of the map.",
        f"The issue tracker should have been provided to you. If not, {_SETUP_LINE}.",
        'Consult the tracker doc\'s "Wayfinding operations" section for how _this_ repo'
        " expresses them.",
        "- [<closed ticket title>](link): <one-line gist of the answer>",
        "A ticket is **unblocked** when every ticket blocking it is closed;",
        "3. **Create the map** (label `wayfinder:map`)",
        "4. Record the resolution: post the answer as a **resolution comment**, **close** the"
        " issue, and **append a context pointer** to the map's Decisions-so-far.",
        "The user may run unblocked tickets in parallel, so expect other sessions to be editing"
        " the tracker concurrently.",
    ),
    "implement-spec": (
        f"The issue tracker should have been provided to you. If not, {_SETUP_LINE}.",
        "The goal is the entire spec implemented on a single **integration branch**, with every"
        " ticket resolved the way the issue tracker closes work.",
        "Communicate primarily through **context pointers**: to the spec, tickets, research"
        " notes, and previous commits.",
        "8. If a draft PR exists, mark it ready for review. Otherwise, resolve each ticket the"
        " way the issue tracker closes work, and report the integration branch.",
    ),
    "implement": ("Commit your work to the current branch.",),
}

_IDS: Final = [skill.skill_id for skill in T04_SKILLS]


def _text(skill: VendoredSkill) -> str:
    return (SKILLS_ROOT / skill.skill_id / "SKILL.md").read_text(encoding="utf-8")


def _body(skill_id: str) -> str:
    return split_skill(skill_id)[1]


def revert_listed_changes(skill: VendoredSkill, text: str) -> str:
    """Undo each A.T04 change of ``skill`` in ``text``; each new text must occur once.

    Example: ``revert_listed_changes(IMPLEMENT, _text(IMPLEMENT))`` -> upstream's bytes.
    """
    for change in skill.line_changes:
        assert text.count(change.plugin) == 1, f"{skill.skill_id} {change.where}: not once"
        text = text.replace(change.plugin, change.upstream)
    for insertion in skill.insertions:
        whole = insertion.before + insertion.inserted + insertion.after
        assert text.count(whole) == 1, f"{skill.skill_id} {insertion.where}: not once"
        text = text.replace(whole, insertion.before + insertion.after)
    return text


def _new_texts() -> list[tuple[str, str]]:
    return [
        *((s.skill_id, c.plugin) for s in T04_SKILLS for c in s.line_changes),
        *((s.skill_id, i.inserted.strip()) for s in T04_SKILLS for i in s.insertions),
    ]


def _replaced_texts() -> list[tuple[str, str]]:
    return [(s.skill_id, c.upstream) for s in T04_SKILLS for c in s.line_changes]


# --- every change, and nothing else ----------------------------------------------


@pytest.mark.parametrize("skill", T04_SKILLS, ids=_IDS)
def test_frontmatter_is_id_then_the_upstream_keys(skill: VendoredSkill) -> None:
    assert _text(skill).startswith(skill.frontmatter + "\n"), "A.T04 frontmatter (D11)"


@pytest.mark.parametrize(("skill_id", "new_text"), _new_texts())
def test_each_new_text_is_present_once(skill_id: str, new_text: str) -> None:
    text = (SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8")
    assert text.count(new_text) == 1, f"skills/{skill_id}/SKILL.md lacks {new_text!r}"


@pytest.mark.parametrize(("skill_id", "upstream_text"), _replaced_texts())
def test_each_replaced_upstream_text_is_gone(skill_id: str, upstream_text: str) -> None:
    text = (SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8")
    assert upstream_text not in text, f"skills/{skill_id}/SKILL.md keeps {upstream_text!r}"


@pytest.mark.parametrize("skill", T04_SKILLS, ids=_IDS)
def test_undoing_the_listed_changes_gives_upstream_bytes(skill: VendoredSkill) -> None:
    upstream = revert_listed_changes(skill, _text(skill)).encode("utf-8")
    assert hashlib.sha256(upstream).hexdigest() == skill.upstream_sha256, (
        f"skills/{skill.skill_id}/SKILL.md changes Matt's text beyond A.T04's list"
    )


@pytest.mark.parametrize("skill", T04_SKILLS, ids=_IDS)
def test_no_sibling_file_moves_only_the_licence_is_added(skill: VendoredSkill) -> None:
    skill_dir = SKILLS_ROOT / skill.skill_id
    assert sorted(p.name for p in skill_dir.iterdir()) == ["SKILL.md", "references"]
    assert sorted(p.name for p in (skill_dir / "references").iterdir()) == ["LICENSE"]


# --- loads (D8, D17, D18.1) ------------------------------------------------------


@pytest.mark.parametrize("skill", T04_SKILLS, ids=_IDS)
def test_load_targets_are_exactly_the_listed_model_invoked_ids(skill: VendoredSkill) -> None:
    targets = set(LOAD_RE.findall(_body(skill.skill_id)))
    assert targets == skill.load_targets
    assert targets <= _MODEL_INVOKED_IDS, "a user-invoked skill loads only model-invoked ones"


@pytest.mark.parametrize("skill", T04_SKILLS, ids=_IDS)
def test_no_skill_tool_wording_remains(skill: VendoredSkill) -> None:
    assert "Skill tool" not in _text(skill)


def test_wayfinder_keeps_the_prototype_ticket_type_but_never_loads_prototype() -> None:
    body = _body("wayfinder")
    assert "prototype" not in LOAD_RE.findall(body)
    assert "one of `research`, `prototype`, `grilling`, `task`" in body
    assert "- **Prototype** (HITL):" in body and "Links the prototype as an asset." in body


def test_wayfinder_loads_grilling_and_domain_modeling_as_two_separate_loads() -> None:
    body = _body("wayfinder")
    pair = "load the `grilling` skill, and load the `domain-modeling` skill"
    assert len(re.findall(re.escape(pair), body, flags=re.IGNORECASE)) == 3
    assert "load each skill the `## Notes` block names" in body


def test_implement_names_no_slash_command_and_no_old_review_id() -> None:
    body = _body("implement")
    assert "/tdd" not in body and "/code-review" not in body
    assert "code-review" not in LOAD_RE.findall(body)


def test_implement_spec_keeps_its_human_facing_labels() -> None:
    frontmatter, body = split_skill("implement-spec")
    description = str(frontmatter["description"])
    assert "/to-spec" in description and "/to-tickets" in description
    assert "code-review" not in LOAD_RE.findall(body)


# --- fallbacks (D18.4, D18.5) and the tracker lines kept -------------------------


def test_wayfinder_without_subagents_leaves_research_on_the_frontier() -> None:
    body = _body("wayfinder")
    assert "leave the research tickets on the frontier" in body
    assert "If your harness can run subagents, then for each `research` ticket" in body
    assert "6. Stop: charting is one session's work; it hand-resolves nothing." in body


def test_implement_spec_hedges_the_draft_pr_through_the_tracker() -> None:
    body = _body("implement-spec")
    assert "open a draft PR, as the issue tracker describes, after the first merge" in body
    assert "open a draft PR after the first merge" not in body


def test_implement_spec_without_subagents_stops_and_resumes_at_merges() -> None:
    body = _body("implement-spec")
    assert "stop-and-resume point" in body and "run `/implement-spec` again" in body
    fallback = body.index(_SEQUENTIAL_FALLBACK)
    assert body.index(_IMPLEMENTER_LINE) < fallback < body.index("## Steps")


@pytest.mark.parametrize(
    ("skill_id", "line"),
    [(skill_id, line) for skill_id, lines in TRACKER_LINES_KEPT.items() for line in lines],
)
def test_tracker_lines_stay_verbatim(skill_id: str, line: str) -> None:
    assert line in _body(skill_id), f"skills/{skill_id}/SKILL.md lost a tracker line {line!r}"


# --- ATTRIBUTIONS.md sections ----------------------------------------------------


def _attribution_section(skill_id: str) -> str:
    """The ``### <skill_id>`` section of ``ATTRIBUTIONS.md``, whitespace folded to spaces."""
    text = (PLUGIN_ROOT / "ATTRIBUTIONS.md").read_text(encoding="utf-8")
    section = text.split(f"\n### {skill_id}\n", 1)[1].split("\n### ", 1)[0]
    return " ".join(section.split())


def _citation(where: str) -> str:
    """``"SKILL.md L77 (D17, D18.4)"`` -> ``"`SKILL.md` L77 (v1.3.1)"``, as section 5.3 cites."""
    file_name, _, anchor = where.split(" (")[0].partition(" ")
    return f"`{file_name}` {anchor} (v1.3.1)"


@pytest.mark.parametrize("skill", T04_SKILLS, ids=_IDS)
def test_attribution_section_lists_every_change_and_the_continue_loss(
    skill: VendoredSkill,
) -> None:
    section = _attribution_section(skill.skill_id)
    head = (
        f"Upstream `skills/engineering/{skill.skill_id}/`; synced as"
        f" `.agents/skills/{skill.skill_id}/`."
    )
    assert section.startswith(head)
    wheres = [i.where for i in skill.insertions] + [c.where for c in skill.line_changes]
    cited = [_citation(where) for where in wheres]
    missing = [citation for citation in cited if citation not in section]
    assert missing == [], f"### {skill.skill_id} does not cite {missing}"
    assert "`agents/openai.yaml`: not shipped" in section
    assert "`references/LICENSE`: added" in section
    assert f"Continue: `.continue/prompts/{skill.skill_id}.md`" in section
