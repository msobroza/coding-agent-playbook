"""The ask-matt router of the ``mattpocock_skills`` bundled plugin (T09, A.T09).

specs/prT-mattpocock-skills.md section 7.1 and appendix A.T09. Every new text of
A.T09 is asserted as an exact substring and every replaced upstream text as
absent, so a future tag upgrade (D5) that replays upstream text fails here. The
labels are checked against the D9 ids (``FINAL_IDS``), not against the skills
present: whether each label names a shipped skill is T10's inventory pin.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest

from tests.plugins.mattpocock_skills._expectations import (
    FINAL_IDS,
    LICENSE_FILE_NAMES,
    SKILLS_ROOT,
    USER_INVOKED_IDS,
    split_skill,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SKILL_DIR: Final = SKILLS_ROOT / "ask-matt"
_SKILL_MD: Final = _SKILL_DIR / "SKILL.md"
_PHASES_MD: Final = _SKILL_DIR / "references" / "PHASE-BOUNDARIES.md"
#: A code span holding exactly one slash label (A.T09 test 1).
_LABEL_RE: Final = re.compile(r"`/([a-z0-9]+(?:-[a-z0-9]+)*)`")
_FALLBACK: Final = " (or `CONTEXT.md` if the repo already has one)"

#: (A.T09 change, exact new text) in SKILL.md, in line order.
SKILL_NEW_TEXTS: Final[tuple[tuple[str, str], ...]] = (
    ("1", "---\nid: ask-matt\nname: ask-matt\n"),
    (
        "2",
        "---\n\nRun this only when the user asked for it by name; otherwise stop.\n\n# Ask Matt\n",
    ),
    (
        "3",
        "retaining what it learns in `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) and ADRs.",
    ),
    ("4", "   - **`/throwaway-prototype`** to answer the question with throwaway code,\n"),
    (
        "5",
        "     - **`/implement`** per ticket, **starting a fresh context between each one**. On a local",
    ),
    (
        "6",
        "runs implementer subagents across the ready **frontier** in parallel (one ticket at a time"
        " where your harness cannot run subagents), and lands everything",
    ),
    (
        "7",
        "closes out with **`/two-axis-review`**, a two-axis review (Standards + Spec) of the diff."
        " `/implement` runs both per ticket; `/implement-spec`'s implementers each drive `/tdd`, and"
        " it runs one `/two-axis-review` over the integration branch. Reach for **`/tdd`** on its own"
        " when you just want to build a concrete behaviour test-first without a full spec, and"
        " **`/two-axis-review`** on its own whenever",
    ),
    ("8", "   When the work goes up as a pull request, **`/pr-body`** shapes the body:"),
    ("9", "the coding standards `/two-axis-review` enforces, steering files, tooling."),
    (
        "10+11",
        "The limit on this is the **smart zone**: the window (~150k tokens on state-of-the-art models)"
        " within which the model still reasons sharply. If a session approaches it before"
        " `/to-tickets`, don't push on degraded; summarise and start a fresh context at the nearest"
        " phase boundary and carry on (see Phase boundaries).\n",
    ),
    (
        "12",
        "A starting situation that generates work, then merges onto the main flow.\n\n"
        "- **Something's broken** → **`/diagnosing-bugs`**.",
    ),
    (
        "13",
        "It's the active discipline `/grill-with-docs` drives to keep `GLOSSARY.md` (or `CONTEXT.md`"
        " if the repo already has one) a clean glossary.\n",
    ),
    (
        "14",
        "- **Clear** (start a fresh context): empty the window, when nothing here matters to what's"
        " next.\n",
    ),
    (
        "15",
        "- **Subagent** (if your harness can run one): send a tightly-scoped task to its own window and"
        " get a report back.\n",
    ),
    (
        "16",
        "- **Compact** (summarise this context, then start a fresh context from the summary)"
        " compresses this context and seeds a fresh session with it. The **default**, at the bottom of"
        " the tree rather than the first reach.\n",
    ),
    (
        "17+18",
        "Read [PHASE-BOUNDARIES.md](references/PHASE-BOUNDARIES.md) for the ordered tree: the five"
        " questions, the reasoning behind each branch, and why the primary-source cost makes"
        " **Continue** the one to rule out first. Make the decision **at** a boundary; mid-phase,"
        " continue or, if your harness can run subagents, split the rest into subagents.\n",
    ),
    (
        "19",
        "it saves nothing locally and builds no `GLOSSARY.md` (or `CONTEXT.md` if the repo already"
        " has one). Reach for it",
    ),
    (
        "20",
        "`/grill-me` and `/grill-with-docs` are the two named ways in, and `/wayfinder` and"
        " `/improve-codebase-architecture` both run it internally. Reach for it directly",
    ),
    (
        "21",
        "- **`/throwaway-prototype`** is a small, throwaway program that answers one design question",
    ),
    (
        "22",
        "Keep working while it reads. If your harness cannot run a background agent, the agent hands"
        " the reading to a subagent, or does it itself in this session. The file it produces",
    ),
    (
        "23",
        "It generates an interactive Python script that opens each URL, captures each value, writes it"
        " into `.env`, and guides you through setting each GitHub secret or variable by hand, so the"
        " procedure stops",
    ),
    (
        "24",
        "in plain English, using the `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one)"
        " vocabulary.",
    ),
)
#: (A.T09 change, replaced upstream text) that SKILL.md must no longer hold.
SKILL_REMOVED_TEXTS: Final[tuple[tuple[str, str], ...]] = (
    ("4+21", "**`/prototype`**"),
    ("5", "**`/clear`ing context between each one**"),
    ("6", "in parallel, and lands everything"),
    ("7+9", "`/code-review`"),
    ("8", "**`/pr`**"),
    ("10", "**[smart zone]("),
    ("11", "`/compact` at the nearest phase boundary"),
    ("12", "- **Bugs and requests piling up**"),
    ("12", "Triage is only for issues **you didn't create**"),
    ("14", "- **`/clear`**:"),
    ("15", "- **Subagent**: send"),
    ("16", "- **`/compact`** compresses"),
    ("17", "[PHASE-BOUNDARIES.md](PHASE-BOUNDARIES.md)"),
    ("18", "mid-phase, continue or split the rest"),
    ("20", "`/triage`, `/wayfinder` and `/improve-codebase-architecture` all run it internally"),
    ("23", "interactive bash script"),
    ("23", "and writes it into `.env` and GitHub secrets"),
)
#: (A.T09 change, exact new text) in references/PHASE-BOUNDARIES.md, in line order.
PHASES_NEW_TEXTS: Final[tuple[tuple[str, str], ...]] = (
    (
        "26",
        "Mid-phase there is no decision to make: continue, or, if your harness can run subagents,"
        " split the work that's left into subagents. Compacting mid-phase makes the agent lose the"
        " thread.\n",
    ),
    (
        "27",
        "| **Clear** (start a fresh context) | Empty the context window and start from nothing."
        "                  |\n",
    ),
    (
        "28",
        "| **Subagent** (if your harness can run one) | Send the task to its own context window and"
        " get a report back.     |\n",
    ),
    (
        "29",
        "| **Compact** (summarise, then start a fresh context from the summary) | Compress this"
        " context and seed a fresh session with the summary.  |\n",
    ),
    ("30", "or you have enough smart zone left (~150k tokens) for the next phase to fit."),
    (
        "31",
        "If so, **clear** (start a fresh context). It is the cheapest move on the board: it takes no"
        " time and hands back the whole window. Clearing also isn't terminal: the old session stays"
        " resumable.\n",
    ),
    (
        "32",
        "Then, if your harness can run subagents, send it to a **subagent** and leave this session"
        " untouched; if it can't, go on to question 5. Automated review",
    ),
    (
        "33",
        "**5. Otherwise, compact (summarise, then start a fresh context from the summary).** Relevant"
        " context, same harness, same directory, and you need to stay in the loop: this is where the"
        " tree lands, and it lands here often. Pass it an instruction (`we're going to QA this area`)"
        " so the summary keeps what the next phase needs.\n",
    ),
    (
        "34",
        "\nStarting a fresh context from a summary is the **default, not the first reach**. It sits at"
        " the bottom",
    ),
    (
        "35",
        "| Secondary (fresh context from a summary, `/handoff`) | Lossy       | Less  | Lots         |\n",
    ),
)
#: (A.T09 change, replaced upstream text) that PHASE-BOUNDARIES.md must no longer hold.
PHASES_REMOVED_TEXTS: Final[tuple[tuple[str, str], ...]] = (
    ("26", "continue, or split the work"),
    ("27", "| **`/clear`** |"),
    ("28", "| **Subagent** | Send"),
    ("29", "| **`/compact`** |"),
    ("30", "[smart zone]("),
    ("31", "If so, **`/clear`**."),
    ("31", "`/clear` also isn't terminal"),
    ("32", "Then send it to a **subagent** and leave this session untouched."),
    ("33", "**5. Otherwise, `/compact`.**"),
    ("33", "(`/compact we're going to QA this area`)"),
    ("34", "`/compact` is the **default"),
    ("35", "| Secondary (`/compact`, `/handoff`) |"),
)
#: Skills the router calls model-invoked: pr-body (L30), wizard (L88), domain-modeling and
#: codebase-design (L62).
_CLAIMED_MODEL_INVOKED: Final = frozenset(
    {"pr-body", "wizard", "domain-modeling", "codebase-design"}
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _skill_body() -> str:
    return split_skill("ask-matt")[1]


@pytest.mark.parametrize(("change", "text"), SKILL_NEW_TEXTS, ids=[c for c, _ in SKILL_NEW_TEXTS])
def test_skill_md_holds_each_new_text(change: str, text: str) -> None:
    assert text in _text(_SKILL_MD), (
        f"skills/ask-matt/SKILL.md lacks A.T09 change {change}: {text!r}"
    )


@pytest.mark.parametrize(
    ("change", "text"),
    SKILL_REMOVED_TEXTS,
    ids=[f"{c}-{i}" for i, (c, _) in enumerate(SKILL_REMOVED_TEXTS)],
)
def test_skill_md_drops_each_replaced_upstream_text(change: str, text: str) -> None:
    assert text not in _text(_SKILL_MD), (
        f"skills/ask-matt/SKILL.md still holds the upstream text A.T09 change {change} replaces: {text!r}"
    )


@pytest.mark.parametrize(("change", "text"), PHASES_NEW_TEXTS, ids=[c for c, _ in PHASES_NEW_TEXTS])
def test_phase_boundaries_holds_each_new_text(change: str, text: str) -> None:
    assert text in _text(_PHASES_MD), (
        f"skills/ask-matt/references/PHASE-BOUNDARIES.md lacks A.T09 change {change}: {text!r}"
    )


@pytest.mark.parametrize(
    ("change", "text"),
    PHASES_REMOVED_TEXTS,
    ids=[f"{c}-{i}" for i, (c, _) in enumerate(PHASES_REMOVED_TEXTS)],
)
def test_phase_boundaries_drops_each_replaced_upstream_text(change: str, text: str) -> None:
    assert text not in _text(_PHASES_MD), (
        "skills/ask-matt/references/PHASE-BOUNDARIES.md still holds the upstream text A.T09"
        f" change {change} replaces: {text!r}"
    )


def test_frontmatter_is_upstream_plus_id() -> None:
    expected = (
        "---\nid: ask-matt\nname: ask-matt\ndescription: Ask which skill or flow fits your situation."
        " A router over the skills in this repo.\ndisable-model-invocation: true\n---\n"
    )
    assert _text(_SKILL_MD).startswith(expected), _text(_SKILL_MD)[: len(expected)]


def test_description_is_verbatim_d28() -> None:
    description = split_skill("ask-matt")[0]["description"]
    assert description == (
        "Ask which skill or flow fits your situation. A router over the skills in this repo."
    )
    assert len(str(description)) == 83


@pytest.mark.parametrize(
    ("path", "lines"), [(_SKILL_MD, 94), (_PHASES_MD, 55)], ids=["SKILL", "PHASES"]
)
def test_files_keep_upstream_shape(path: Path, lines: int) -> None:
    text = _text(path)
    assert text.endswith("\n") and not text.endswith("\n\n"), (
        f"{path}: not exactly one final newline"
    )
    assert "\r" not in text, f"{path}: CR found"
    assert all(line == line.rstrip() for line in text.split("\n")), f"{path}: trailing whitespace"
    assert text.count("\n") == lines, f"{path}: {text.count(chr(10))} lines, expected {lines}"


def test_router_labels_match_inventory() -> None:
    skill_labels = set(_LABEL_RE.findall(_skill_body()))
    assert skill_labels == FINAL_IDS - {"ask-matt"}, (
        f"missing {sorted(FINAL_IDS - {'ask-matt'} - skill_labels)},"
        f" unknown {sorted(skill_labels - FINAL_IDS)}"
    )
    assert set(_LABEL_RE.findall(_text(_PHASES_MD))) == {"handoff"}


@pytest.mark.parametrize("stale", ["`/triage`", "`/code-review`", "`/pr`", "`/prototype`"])
@pytest.mark.parametrize("path", [_SKILL_MD, _PHASES_MD], ids=["SKILL", "PHASES"])
def test_router_no_stale_routes(path: Path, stale: str) -> None:
    assert stale not in _text(path), f"{path} still routes to {stale}"


def test_on_ramps_section_has_exactly_two_bullets() -> None:
    section = _skill_body().split("## On-ramps\n", 1)[1].split("\n## ", 1)[0]
    bullets = [line for line in section.split("\n") if line.startswith("- **")]
    assert len(bullets) == 2, bullets
    assert "two **on-ramps** merge onto it" in _skill_body()
    assert "triage labels" in _skill_body(), "upstream L95's 'triage labels' must stay (A.T03)"


@pytest.mark.parametrize("skill_id", sorted(_CLAIMED_MODEL_INVOKED))
def test_router_invocation_claims(skill_id: str) -> None:
    assert skill_id in FINAL_IDS
    assert skill_id not in USER_INVOKED_IDS, f"the router calls {skill_id} model-invoked"


@pytest.mark.parametrize(
    "text",
    [
        "**starting a fresh context between each one**",
        "- **Clear** (start a fresh context):",
        "**Compact** (summarise this context, then start a fresh context from the summary)",
        "[PHASE-BOUNDARIES.md](references/PHASE-BOUNDARIES.md)",
        "**smart zone**",
        "interactive Python script",
    ],
)
def test_router_replay_guard_skill_md(text: str) -> None:
    assert text in _text(_SKILL_MD)


@pytest.mark.parametrize(
    "text",
    [
        "if it can't, go on to question 5",
        "**5. Otherwise, compact (summarise, then start a fresh context from the summary).**",
        "enough smart zone left",
    ],
)
def test_router_replay_guard_phase_boundaries(text: str) -> None:
    assert text in _text(_PHASES_MD)


@pytest.mark.parametrize("banned", ["aihero", "bash"])
@pytest.mark.parametrize("path", [_SKILL_MD, _PHASES_MD], ids=["SKILL", "PHASES"])
def test_router_replay_guard_banned_words(path: Path, banned: str) -> None:
    assert banned not in _text(path), f"{path} holds {banned!r}"


def test_router_references_inventory() -> None:
    references = {p.name for p in (_SKILL_DIR / "references").iterdir()}
    assert references == {"LICENSE", "PHASE-BOUNDARIES.md"}
    assert "LICENSE" in LICENSE_FILE_NAMES
    assert {p.name for p in _SKILL_DIR.iterdir()} == {"SKILL.md", "references"}


def test_glossary_mentions_carry_context_fallback() -> None:
    text = _text(_SKILL_MD)
    mentions = [m.end() for m in re.finditer(r"`GLOSSARY\.md`", text)]
    assert len(mentions) == 4, mentions
    for end in mentions:
        assert text[end:].startswith(_FALLBACK), text[end : end + 60]
    assert "GLOSSARY" not in _text(_PHASES_MD)


def test_non_ascii_characters_kept() -> None:
    skill, phases = _text(_SKILL_MD), _text(_PHASES_MD)
    assert skill.count("→") == 5, "U+2192 at upstream L13, L23, L26, L48, L50"
    assert "steps 1\u20133" in skill
    assert phases.count("→") == 2, "U+2192 at upstream L21 and L29"
    assert "\u2014" not in skill + phases, "the added prose has no em-dashes"
