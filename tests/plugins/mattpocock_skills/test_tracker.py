"""T03: setup-matt-pocock-skills, to-spec, to-tickets and the plugin always rule.

specs/prT-mattpocock-skills.md appendix A.T03, sections 5.5, 6 and 9.4. Each new
text of A.T03 is asserted as an exact substring of its file, and each upstream
text it replaces as absent, so a later tag upgrade (D5) that replays upstream
bytes over the changes fails here. The shared gate (``test_gates.py``) covers
URLs, imposed tools, the guard line, layout and licences.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.sources.filesystem import FileSystemArtifactSource
from coding_agent_playbook.types import Rule, split_frontmatter
from tests.plugins.mattpocock_skills._expectations import (
    PLUGIN_NAME,
    PLUGIN_ROOT,
    RULE_FILE_NAME,
    RULES_ROOT,
    SKILLS_ROOT,
)
from tests.plugins.mattpocock_skills.conftest import init_probe
from tests.plugins.superpowers_expectations import SKILL_ADAPTERS

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

SETUP: Final = "setup-matt-pocock-skills"
RULE_ID: Final = "mattpocock-skills-tracker"
RULE_HEADING: Final = "## Issue tracker and domain docs"
#: The three files setup writes into the consumer repo, and nothing else (D14).
SETUP_OUTPUTS: Final = frozenset(
    {"docs/agents/issue-tracker.md", "docs/agents/triage-labels.md", "docs/agents/domain.md"}
)
#: Upstream v1.3.1 ``triage-labels.md``, vendored byte for byte (change 41).
TRIAGE_LABELS_SHA256: Final = "4f53c9b40ce2651e3611aa090eaedbd6dbc9b71ef8c5f7e65eac0d8263190d0d"
TRIAGE_ROLES: Final = (
    "needs-triage",
    "needs-info",
    "ready-for-agent",
    "ready-for-human",
    "wontfix",
)
_SETUP_SLASH_POINTER: Final = "tell the user to run `/setup-matt-pocock-skills`"
_CF: Final = " (or `CONTEXT.md` if the repo already has one)"
_CMF: Final = " (or `CONTEXT-MAP.md` if the repo already has one)"
_RULE_BODY: Final = (
    "When present, `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` and "
    "`docs/agents/domain.md` describe this repo's issue tracker, triage labels and domain docs: "
    "read the one a skill needs. If a skill needs one that is missing, tell the user to run "
    "`/setup-matt-pocock-skills`. `.scratch/` is untracked working state: never stage or "
    "commit it.\n"
)

#: (skill id, path inside the skill, new text of A.T03): each must occur exactly once.
NEW_TEXTS: Final[tuple[tuple[str, str, str], ...]] = (
    # setup SKILL.md, changes 3-24
    (
        SETUP,
        "SKILL.md",
        "- **Issue tracker**: where issues live (local markdown by default; any other tracker "
        "works once the user describes it)\n",
    ),
    (
        SETUP,
        "SKILL.md",
        f"- **Domain docs**: where `GLOSSARY.md`{_CF} and ADRs live, and the consumer rules for "
        "reading them\n",
    ),
    (
        SETUP,
        "SKILL.md",
        "- `AGENTS.md` and `CLAUDE.md` at the repo root: is there an old `## Agent skills` section "
        "in either? Read them only to answer that: this skill never edits or creates either file "
        "(step 5 says what to tell the user).\n",
    ),
    (SETUP, "SKILL.md", f"- `GLOSSARY.md`{_CF} and `GLOSSARY-MAP.md`{_CMF} at the repo root\n"),
    (
        SETUP,
        "SKILL.md",
        "skip the section entirely when exploration already settled it (Section C when there's no "
        "monorepo). Section B is written without asking.\n",
    ),
    (
        SETUP,
        "SKILL.md",
        '> Explainer: The "issue tracker" is where issues live for this repo. Skills like '
        "`to-tickets` and `to-spec` read from and write to it. They need to know whether to write a "
        "markdown file under `.scratch/` or follow some other workflow you describe. Pick the place "
        "you actually track work for this repo.\n",
    ),
    (
        SETUP,
        "SKILL.md",
        "Default posture: propose local markdown, even when a `git remote` points at a forge; a user "
        "who tracks work in that forge's issues, or anywhere else, picks **Other**. Offer:\n",
    ),
    (
        SETUP,
        "SKILL.md",
        "- **Local markdown**: issues live as files under `.scratch/<feature>/` in this repo (the "
        "default; needs no remote or CLI)\n",
    ),
    (
        SETUP,
        "SKILL.md",
        "- **Other** (Jira, Linear, etc.): ask the user to describe the workflow for each section of "
        "[issue-tracker-local.md](./references/issue-tracker-local.md) after its Conventions: "
        "publish, fetch, close, blocking (default: a plain `Blocked by:` line near the top of each "
        "ticket) and the Wayfinding operations; the skill will record each answer under that "
        "section's heading\n",
    ),
    (SETUP, "SKILL.md", "\nRecord the choice in `docs/agents/issue-tracker.md`.\n\n"),
    (
        SETUP,
        "SKILL.md",
        "**Section B: Triage label vocabulary.** Always written, without asking: `to-spec` and "
        "`to-tickets` apply these labels.\n\nThe defaults are the five canonical roles, each label "
        "string equal to its name: `needs-triage`, `needs-info`, `ready-for-agent`, "
        "`ready-for-human`, `wontfix`. Write them as-is. If the user's tracker already uses other "
        "names (e.g. `bug:triage` for `needs-triage`), they change the right-hand column in the "
        "step 3 draft, so the skills apply existing labels instead of creating duplicates.\n",
    ),
    (
        SETUP,
        "SKILL.md",
        f"**Section C: Domain docs.** Default to **single-context** (one `GLOSSARY.md`{_CF} + "
        "`docs/adr/` at the repo root). This fits almost every repo; write it without asking.\n",
    ),
    (
        SETUP,
        "SKILL.md",
        f"Offer **multi-context** (a root `GLOSSARY-MAP.md`{_CMF} pointing to per-context "
        f"`GLOSSARY.md`{_CF} files) only when exploration found monorepo signals.",
    ),
    (
        SETUP,
        "SKILL.md",
        "\n- The contents of `docs/agents/issue-tracker.md`, `docs/agents/domain.md`, and "
        "`docs/agents/triage-labels.md`\n\nLet them edit before writing.\n",
    ),
    (
        SETUP,
        "SKILL.md",
        "### 4. Write\n\nWrite only `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` "
        "and `docs/agents/domain.md`. Never edit or create `CLAUDE.md` or `AGENTS.md`: the always "
        "rule this plugin ships (`mattpocock-skills-tracker`) already points every session at these "
        "files.\n\nWrite the docs files using the seed templates in this skill folder as a starting "
        "point:\n\n",
    ),
    (
        SETUP,
        "SKILL.md",
        ":\n\n- [issue-tracker-local.md](./references/issue-tracker-local.md): local-markdown issue "
        "tracker\n- [triage-labels.md](./references/triage-labels.md): label mapping\n"
        "- [domain.md](./references/domain.md): domain doc consumer rules + layout\n\n",
    ),
    (
        SETUP,
        "SKILL.md",
        'For "other" issue trackers, write `docs/agents/issue-tracker.md` from scratch using the '
        "user's description, under the same `##` headings as "
        "[issue-tracker-local.md](./references/issue-tracker-local.md) after its Conventions; keep "
        "the `## Wayfinding operations` heading verbatim, since `wayfinder` looks it up by name.\n",
    ),
    (
        SETUP,
        "SKILL.md",
        "restart from scratch. If exploration found an old `## Agent skills` section in a root "
        "`CLAUDE.md` or `AGENTS.md`, tell them the always rule this plugin ships "
        "(`mattpocock-skills-tracker`) supersedes it and that they may delete it; don't edit the "
        "file yourself.\n",
    ),
    # references/domain.md, changes 26-31
    (SETUP, "references/domain.md", f"- **`GLOSSARY.md`**{_CF} at the repo root, or\n"),
    (
        SETUP,
        "references/domain.md",
        f"- **`GLOSSARY-MAP.md`**{_CMF} at the repo root if it exists: it points at one "
        f"`GLOSSARY.md`{_CF} per context. Read each one relevant to the topic.\n",
    ),
    (
        SETUP,
        "references/domain.md",
        "The `domain-modeling` skill (reached via `grill-with-docs` and "
        "`improve-codebase-architecture`) creates them lazily when terms or decisions actually get "
        "resolved.\n",
    ),
    (
        SETUP,
        "references/domain.md",
        f"Multi-context repo (presence of `GLOSSARY-MAP.md`{_CMF} at the root):\n",
    ),
    (
        SETUP,
        "references/domain.md",
        f"use the term as defined in `GLOSSARY.md`{_CF}. Don't drift to synonyms the glossary "
        "explicitly avoids.\n",
    ),
    (SETUP, "references/domain.md", "(note it for `domain-modeling`).\n"),
    # references/issue-tracker-local.md, changes 33-40
    (
        SETUP,
        "references/issue-tracker-local.md",
        "never a single combined tickets file\n- Every issue file (the spec, each ticket) and every "
        "map opens with a `# <title>` heading: its name\n- Triage state",
    ),
    (
        SETUP,
        "references/issue-tracker-local.md",
        "under a `## Comments` heading\n- `.scratch/` is untracked working state: never stage it in "
        "a commit\n- Worktrees do not contain untracked files: when you point a subagent or a "
        "worktree at a spec, ticket or map, give its absolute path in the main checkout\n\n",
    ),
    (
        SETUP,
        "references/issue-tracker-local.md",
        '## When a skill says "close" or "resolve" a ticket\n\nSet the file\'s `Status:` line, '
        "in place, to a terminal status: `resolved` (answered or done) or `out-of-scope` (ruled "
        "out). A ticket is **closed** when its status is either one; any other status is open. Set "
        "an implementation ticket `resolved` once its work is merged. A ticket written by "
        "`to-tickets` has the bold form `**Status:** ready-for-agent`: rewrite that line in place, "
        "never add a second status line.\n\n",
    ),
    (
        SETUP,
        "references/issue-tracker-local.md",
        "## Blocking\n\nA ticket's blockers go on a `Blocked by:` line near the top (bold, "
        "`**Blocked by:**`, in a ticket written by `to-tickets`), listing the numbers of the "
        "tickets that gate it (titles may follow), or `None (can start immediately)`. A ticket is "
        "unblocked when every ticket it lists is closed.\n\n",
    ),
    (
        SETUP,
        "references/issue-tracker-local.md",
        "Used by `wayfinder`. The **map** is a file with one **child** file per ticket.\n",
    ),
    (
        SETUP,
        "references/issue-tracker-local.md",
        "a `Status:` line records `claimed`/`resolved`/`out-of-scope`.\n",
    ),
    (
        SETUP,
        "references/issue-tracker-local.md",
        "A ticket is unblocked when every file it lists is closed (`resolved` or `out-of-scope`).\n",
    ),
    (
        SETUP,
        "references/issue-tracker-local.md",
        "to the map's Decisions-so-far in `map.md`. Only the session driving the map appends to "
        "`map.md`; a research subagent writes only its own ticket file.\n",
    ),
    # to-tickets SKILL.md, change 3
    (
        "to-tickets",
        "SKILL.md",
        "Publish the approved tickets. **How** depends on the tracker `setup-matt-pocock-skills` "
        "configured; the tickets are the same either way, only the shape of the blocking edges "
        "changes:\n",
    ),
)

#: Upstream v1.3.1 texts of setup's ``SKILL.md`` that a change replaced or removed.
_SETUP_REPLACED: Final = (
    "GitHub by default; local markdown is also supported out of the box",
    "where `GLOSSARY.md` and ADRs live",
    "does either exist? Is there already an `## Agent skills` section in either?",
    "- `GLOSSARY.md` and `GLOSSARY-MAP.md` at the repo root",
    "Is the `triage` skill installed?",
    "This decides whether Section B runs at all.",
    "(Section B when `triage` isn't installed, Section C when there's no monorepo)",
    "Skills like `to-tickets`, `triage`, and `to-spec`",
    "`gh issue create`",
    "these skills were designed for GitHub",
    "`gitlab.com`",
    "(uses the `gh` CLI)",
    "GitLab Issues",
    "(good for solo projects or repos without a remote)",
    "describe the workflow in one paragraph; the skill will record it as freeform prose",
    "PRs as a request surface",
    "a user who wants external PRs in the triage queue",
    "Skip this section entirely if the `triage` skill isn't installed",
    "If it is installed, ask exactly one question:",
    "Do you want to keep the default triage labels?",
    "On **yes**, write them as-is. Only if the user says no",
    "collect the overrides so `triage` applies existing labels",
    "(one `GLOSSARY.md` + `docs/adr/`",
    "(a root `GLOSSARY-MAP.md` pointing to per-context `GLOSSARY.md` files)",
    "The `## Agent skills` block to add",
    "(the last only when `triage` is installed)",
    "**Pick the file to edit:**",
    "If `CLAUDE.md` exists, edit it.",
    "Else if `AGENTS.md` exists, edit it.",
    "ask the user which one to create",
    "Never create `AGENTS.md` when `CLAUDE.md` already exists",
    "update its contents in-place rather than appending a duplicate",
    "The block:",
    "### Triage labels",
    "[one-line summary of",
    "Include the `### Triage labels` sub-block",
    "Then write the docs files",
    "issue-tracker-github.md",
    "issue-tracker-gitlab.md",
    "](./issue-tracker-local.md)",
    "](./triage-labels.md)",
    "](./domain.md)",
    "(only if `triage` is installed)",
    "from scratch using the user's description.\n",
    "or restart from scratch.\n",
)
#: (skill id, path inside the skill, upstream v1.3.1 text a change replaced or removed).
REPLACED_TEXTS: Final[tuple[tuple[str, str, str], ...]] = (
    *((SETUP, "SKILL.md", text) for text in _SETUP_REPLACED),
    (SETUP, "references/domain.md", "- **`GLOSSARY.md`** at the repo root, or"),
    (SETUP, "references/domain.md", "- **`GLOSSARY-MAP.md`** at the repo root if it exists"),
    (SETUP, "references/domain.md", "`/domain-modeling`"),
    (SETUP, "references/domain.md", "`/grill-with-docs`"),
    (SETUP, "references/domain.md", "`/improve-codebase-architecture`"),
    (SETUP, "references/domain.md", "(presence of `GLOSSARY-MAP.md` at the root)"),
    (SETUP, "references/domain.md", "as defined in `GLOSSARY.md`. Don't drift"),
    (SETUP, "references/issue-tracker-local.md", "Used by `/wayfinder`."),
    (SETUP, "references/issue-tracker-local.md", "records `claimed`/`resolved`.\n"),
    (SETUP, "references/issue-tracker-local.md", "every file it lists is `resolved`."),
    (SETUP, "references/issue-tracker-local.md", "Decisions-so-far in `map.md`.\n"),
    ("to-tickets", "SKILL.md", "the tracker `/setup-matt-pocock-skills` configured"),
)

#: (skill id, path, line count): the A.T03 results, which keep upstream's LF and final newline.
LINE_COUNTS: Final = (
    (SETUP, "SKILL.md", 81),
    (SETUP, "references/domain.md", 51),
    (SETUP, "references/issue-tracker-local.md", 41),
    (SETUP, "references/triage-labels.md", 15),
    ("to-spec", "SKILL.md", 78),
    ("to-tickets", "SKILL.md", 108),
)
#: Non-ASCII characters upstream wrote, which the copies keep (A.T03 conventions).
KEPT_NON_ASCII: Final = (
    # Box drawing, U+2190 arrow and U+2026 ellipsis (domain.md L19-L38, L51).
    (SETUP, "references/domain.md", tuple(map(chr, (0x251C, 0x2502, 0x2514, 0x2190, 0x2026)))),
    # U+2013 en dash (L40), U+2192 arrows (L62-L63), U+2026 ellipsis (L63).
    ("to-tickets", "SKILL.md", tuple(map(chr, (0x2013, 0x2192, 0x2026)))),
)


def _text(skill_id: str, rel: str) -> str:
    return (SKILLS_ROOT / skill_id / rel).read_text(encoding="utf-8")


def _rule_path() -> Path:
    return RULES_ROOT / RULE_FILE_NAME


def _ids(case: tuple[str, str, object]) -> str:
    return f"{case[0]}/{case[1]}"


# --- A.T03 texts: new present, replaced absent ----------------------------------


@pytest.mark.parametrize("case", NEW_TEXTS, ids=_ids)
def test_new_text_of_a_t03_occurs_exactly_once(case: tuple[str, str, str]) -> None:
    skill_id, rel, expected = case
    count = _text(skill_id, rel).count(expected)
    assert count == 1, f"skills/{skill_id}/{rel}: {expected!r} occurs {count} times, expected 1"


@pytest.mark.parametrize("case", REPLACED_TEXTS, ids=_ids)
def test_replaced_upstream_text_is_absent(case: tuple[str, str, str]) -> None:
    skill_id, rel, upstream = case
    assert upstream not in _text(skill_id, rel), f"skills/{skill_id}/{rel}: {upstream!r} is back"


@pytest.mark.parametrize("case", LINE_COUNTS, ids=_ids)
def test_vendored_file_keeps_lf_one_final_newline_and_its_line_count(
    case: tuple[str, str, int],
) -> None:
    skill_id, rel, lines = case
    data = (SKILLS_ROOT / skill_id / rel).read_bytes()
    newlines = data.count(b"\n")
    assert b"\r" not in data and data.endswith(b"\n") and not data.endswith(b"\n\n")
    assert newlines == lines, f"skills/{skill_id}/{rel}: {newlines} lines, expected {lines}"
    trailing = [n for n, line in enumerate(data.split(b"\n"), 1) if line != line.rstrip()]
    assert trailing == [], f"skills/{skill_id}/{rel}: trailing whitespace on lines {trailing}"


@pytest.mark.parametrize("case", KEPT_NON_ASCII, ids=_ids)
def test_upstream_non_ascii_characters_are_kept(case: tuple[str, str, tuple[str, ...]]) -> None:
    skill_id, rel, characters = case
    text = _text(skill_id, rel)
    assert [c for c in characters if c not in text] == []


def test_frontmatter_keeps_upstream_keys_with_id_first() -> None:
    expected = {
        SETUP: '"Configure this repo for the engineering skills: set up its issue tracker, triage '
        "label vocabulary, and domain doc layout. Run once before first use of the other "
        'engineering skills."',
        "to-spec": '"Turn the current conversation into a spec and publish it to the project issue '
        "tracker: no interview, just synthesis of what you've already discussed.\"",
        "to-tickets": "Break a plan, spec, or the current conversation into a set of tracer-bullet "
        "tickets, each declaring its blocking edges, published to the configured tracker (edges "
        "as text in one file per ticket locally, or native blocking links on a real tracker).",
    }
    for skill_id, description in expected.items():
        head = _text(skill_id, "SKILL.md").split("\n")[:6]
        assert head == [
            "---",
            f"id: {skill_id}",
            f"name: {skill_id}",
            f"description: {description}",
            "disable-model-invocation: true",
            "---",
        ], skill_id


# --- setup-matt-pocock-skills (A.T03.1 skill-specific tests) --------------------


def test_setup_writes_exactly_the_three_docs_agents_files() -> None:
    named = set(re.findall(r"docs/agents/[\w.-]+\.md", _text(SETUP, "SKILL.md")))
    assert named == SETUP_OUTPUTS, "setup writes only the three docs/agents/ files (D14)"


def test_setup_references_inventory() -> None:
    references = SKILLS_ROOT / SETUP / "references"
    assert sorted(p.name for p in references.iterdir()) == [
        "LICENSE",
        "domain.md",
        "issue-tracker-local.md",
        "triage-labels.md",
    ]
    forge_seeds = [
        p.relative_to(PLUGIN_ROOT).as_posix() for p in PLUGIN_ROOT.rglob("issue-tracker-git*.md")
    ]
    assert forge_seeds == [], "the GitHub and GitLab seeds are not shipped (D14)"


def test_local_tracker_headings() -> None:
    text = _text(SETUP, "references/issue-tracker-local.md")
    assert text.split("\n", 1)[0] == "# Issue tracker: Local Markdown"
    assert re.findall(r"^## (.+)$", text, flags=re.MULTILINE) == [
        "Conventions",
        'When a skill says "publish to the issue tracker"',
        'When a skill says "fetch the relevant ticket"',
        'When a skill says "close" or "resolve" a ticket',
        "Blocking",
        "Wayfinding operations",
    ]


def test_local_tracker_close_contract() -> None:
    seed = _text(SETUP, "references/issue-tracker-local.md")
    for needle in (
        "`out-of-scope`",
        "**Status:**",
        "**Blocked by:**",
        "`Blocked by: NN, NN`",
        "absolute path in the main checkout",
    ):
        assert needle in seed, needle
    tickets = _text("to-tickets", "SKILL.md")
    assert "**Status:** ready-for-agent" in tickets
    assert "**Blocked by:**" in tickets


def test_triage_labels_seed() -> None:
    data = (SKILLS_ROOT / SETUP / "references" / "triage-labels.md").read_bytes()
    assert hashlib.sha256(data).hexdigest() == TRIAGE_LABELS_SHA256, "byte-identical (change 41)"
    text = data.decode("utf-8")
    assert "| Label in mattpocock/skills |" in text
    for role in TRIAGE_ROLES:
        assert re.search(rf"^\| `{role}` +\| `{role}` +\|", text, flags=re.MULTILINE), role


def test_setup_replay_guard() -> None:
    text = _text(SETUP, "SKILL.md")
    for removed in (
        "issue-tracker-github",
        "issue-tracker-gitlab",
        "Pick the file to edit",
        "PRs as a request surface",
        "the `triage` skill installed",
        "gh issue",
    ):
        assert removed not in text, removed
    assert "(the default; needs no remote or CLI)" in text
    assert "never edits or creates either file" in text


@pytest.mark.parametrize("rel", ["SKILL.md", "references/domain.md"])
def test_glossary_prose_lines_carry_the_context_fallback(rel: str) -> None:
    """D21 per prose line; fenced trees stay verbatim (A.T03 ambiguity 2)."""
    missing: list[str] = []
    fenced = False
    for number, line in enumerate(_text(SETUP, rel).split("\n"), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if "GLOSSARY.md" in line and line.count("GLOSSARY.md") != line.count(_CF.strip()):
            missing.append(f"{number}: GLOSSARY.md")
        if "GLOSSARY-MAP.md" in line and line.count("GLOSSARY-MAP.md") != line.count(_CMF.strip()):
            missing.append(f"{number}: GLOSSARY-MAP.md")
    assert missing == [], f"skills/{SETUP}/{rel}: a mention without its fallback"


# --- to-spec and to-tickets (A.T03.2, A.T03.3) ----------------------------------


def test_setup_pointer_slash_forms() -> None:
    for skill_id in ("to-spec", "to-tickets"):
        assert _SETUP_SLASH_POINTER in _text(skill_id, "SKILL.md"), skill_id
    tickets = _text("to-tickets", "SKILL.md")
    assert "the tracker `setup-matt-pocock-skills` configured" in tickets
    assert "the tracker `/setup-matt-pocock-skills`" not in tickets


@pytest.mark.parametrize("skill_id", ["to-spec", "to-tickets"])
def test_to_spec_and_to_tickets_ship_only_skill_md_and_the_licence(skill_id: str) -> None:
    files = sorted(
        p.relative_to(SKILLS_ROOT / skill_id).as_posix()
        for p in (SKILLS_ROOT / skill_id).rglob("*")
        if p.is_file()
    )
    assert files == ["SKILL.md", "references/LICENSE"]


# --- the plugin always rule (A.T03 "T03 plugin always rule", section 5.5) -------


def test_plugin_adds_exactly_the_tracker_rule(tmp_path: Path) -> None:
    plain = FileSystemArtifactSource(repo_root=tmp_path)
    with_plugin = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=[PLUGIN_NAME])
    before = {r.frontmatter.id for r in plain.list_rules()}
    extra = [r for r in with_plugin.list_rules() if r.frontmatter.id not in before]
    assert [r.frontmatter.id for r in extra] == [RULE_ID]
    (rule,) = extra
    assert rule.frontmatter.scope == "always"
    assert rule.frontmatter.skill is None
    assert rule.frontmatter.applies_if == {}
    assert rule.frontmatter.globs == []
    assert rule.source_path is not None and rule.source_path.name == RULE_FILE_NAME
    assert rule.source_package == PLUGIN_NAME
    assert len(with_plugin.list_prompts()) == len(plain.list_prompts())
    core_always = [
        r.frontmatter.priority for r in plain.list_rules() if r.frontmatter.scope == "always"
    ]
    assert all(rule.frontmatter.priority > p for p in core_always), "renders after core rules"


def test_tracker_rule_file_is_exactly_the_a_t03_text() -> None:
    expected = (
        "---\n"
        f"id: {RULE_ID}\n"
        "name: Issue tracker and domain docs\n"
        "description: Where this repo's issue tracker, triage label and domain doc config lives, "
        "and that .scratch/ is never staged.\n"
        "version: 1\n"
        "scope: always\n"
        "priority: 50\n"
        "tags: [always, tracker]\n"
        "---\n"
        "\n" + _RULE_BODY
    )
    assert _rule_path().read_text(encoding="utf-8") == expected
    rule = Rule.from_markdown(_rule_path(), PLUGIN_NAME)
    assert (rule.frontmatter.id, rule.frontmatter.scope, rule.is_templated) == (
        RULE_ID,
        "always",
        False,
    )


def test_tracker_rule_body_contract() -> None:
    _, body = split_frontmatter(_rule_path().read_text(encoding="utf-8"))
    assert len(body.split()) <= 60, f"{len(body.split())} words; D15 allows 60"
    for needle in (*sorted(SETUP_OUTPUTS), "`/setup-matt-pocock-skills`", "`.scratch/`"):
        assert needle in body, needle
    assert "references/" not in body and "scripts/" not in body
    assert "](" not in body, "the rule has no link to resolve"
    assert (SKILLS_ROOT / SETUP / "SKILL.md").is_file(), "the pointer names a shipped skill"


def _rule_targets(repo: Path) -> dict[str, str]:
    """The files a synced always rule lands in, with their text ('' when absent)."""
    targets = [repo / "AGENTS.md", repo / ".claude" / "rules" / "coding-agent-playbook.md"]
    return {
        p.relative_to(repo).as_posix(): p.read_text(encoding="utf-8") if p.is_file() else ""
        for p in targets
    }


def _continue_rule_files(repo: Path) -> list[str]:
    rules = repo / ".continue" / "rules"
    return sorted(p.name for p in rules.glob(f"*{RULE_ID}*")) if rules.is_dir() else []


def test_tracker_rule_renders_once_with_the_plugin_on(synced_repo: Path) -> None:
    for rel, text in _rule_targets(synced_repo).items():
        assert text.count(RULE_HEADING) == 1, f"{rel}: {RULE_HEADING!r} x{text.count(RULE_HEADING)}"
        assert _RULE_BODY.strip() in text, f"{rel}: the rule body is missing"
    (name,) = _continue_rule_files(synced_repo)
    continue_text = (synced_repo / ".continue" / "rules" / name).read_text(encoding="utf-8")
    assert "alwaysApply: true" in continue_text and _RULE_BODY.strip() in continue_text


@pytest.mark.usefixtures("hermetic_git_env")
def test_tracker_rule_is_absent_with_the_plugin_off(tmp_path: Path) -> None:
    repo = init_probe(tmp_path, overlays=None, adapters=",".join(SKILL_ADAPTERS))
    for rel, text in _rule_targets(repo).items():
        assert RULE_HEADING not in text and RULE_ID not in text, rel
    assert _continue_rule_files(repo) == []
