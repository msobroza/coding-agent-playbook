"""The core v2 prompt set points to skills (D76, D74; prU C-prompts-v2).

Each ``catalog/core/prompts/v2/`` twin is its v1 prompt plus three parts: the core
skills to load before the task, what to do when something is unclear, and the
framework skills and decision guides that check the work. These tests sync a probe
repo with ``prompts = "v2"`` under no framework, mattpocock_skills and superpowers,
then read the rendered prompts, and check that every decision guide a twin cites
is one its skill's refs ticket adds.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest
import yaml

from coding_agent_playbook.commands import sync as sync_cmd
from coding_agent_playbook.sync.render import render_artifacts
from coding_agent_playbook.validation.context import SyncContext
from tests._catalog import CORE_SKILLS_ROOT, REPO_ROOT
from tests.conftest import _DEFAULT_CONFIG

if TYPE_CHECKING:
    from collections.abc import Callable

    SyntheticRepoFactory = Callable[..., Path]

pytestmark = pytest.mark.catalog

_CATALOG: Final = Path(__file__).resolve().parents[2] / "catalog"
_PROMPTS: Final = _CATALOG / "core" / "prompts"
_V2: Final = _PROMPTS / "v2"

#: The nine core prompts D76 gives a v2 twin.
_CORE_PROMPTS: Final = (
    "characterize",
    "explain",
    "find-injected-vulnerability",
    "generate-tests",
    "make-testable",
    "refactor",
    "review",
    "review-architecture",
    "security-review",
)

#: D76: the core skills each task loads first (python-architecture and
#: python-documentation are named only once a repo renders them).
_TASK_SKILLS: Final = {
    "refactor": ("python-coding", "design-patterns"),
    "review": ("python-coding", "design-patterns", "python-testing"),
    "review-architecture": ("python-architecture", "design-patterns"),
    "generate-tests": ("python-testing",),
    "characterize": ("python-testing",),
    "make-testable": ("python-architecture", "python-testing"),
    "security-review": ("web-application", "ml-data"),
    "find-injected-vulnerability": ("web-application", "ml-data"),
    "explain": ("python-documentation",),
}

#: Every core skill a v2 twin may name, shipped today or planned (D76).
_CORE_SKILLS: Final = frozenset(
    {
        *(p.name for p in (_CATALOG / "core" / "skills").iterdir() if p.is_dir()),
        *(skill for skills in _TASK_SKILLS.values() for skill in skills),
    }
)

#: The skills the two bundled frameworks ship: names a core prompt must not hard-code.
_PLUGIN_SKILLS: Final = frozenset(
    p.name
    for plugin in ("mattpocock_skills", "superpowers")
    for p in (_CATALOG / "plugins" / plugin / "skills").iterdir()
    if p.is_dir()
)

#: A probe repo every v2 twin applies to (pytest, FastAPI, an ML stack).
_ALL_FACTS_DEPS: Final = ["pytest", "fastapi", "sqlalchemy", "torch", "pandas", "numpy"]

#: Probe dependency sets by name: every fact, or pytest alone (most skills inactive).
_DEPENDENCY_SETS: Final = {"all-facts": _ALL_FACTS_DEPS, "pytest-only": ["pytest"]}

#: The three parts D76 adds, in order.
_V2_HEADINGS: Final = (
    "## Skills for this task",
    "## If something is unclear",
    "## Check and improve your work",
)

_FRAMEWORKS: Final = ("none", "mattpocock", "superpowers")
#: The clarify skill each framework names (D74).
_CLARIFY: Final[dict[str, str]] = {"mattpocock": "grill-me", "superpowers": "brainstorming"}

#: The refs tickets' table rows: ``| C-<skill>-refs | title | `references/<file>`, ... |``.
_TICKETS: Final = REPO_ROOT / "specs" / "prU-core-python-skills" / "tickets.md"
_REFS_ROW: Final = re.compile(r"^\| C-(?P<skill>[a-z-]+)-refs \|[^|]*\|(?P<files>[^|]*)\|", re.M)
#: A decision guide citation: ``\`<guide>.md\` ... in the <skill> skill``, one skill a line.
_GUIDE: Final = re.compile(r"`([a-z0-9-]+\.md)`")
_GUIDE_SKILL: Final = re.compile(r"\bin the ([a-z-]+) skill\b")


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    _, head, _ = text.split("---\n", 2)
    loaded = yaml.safe_load(head)
    assert isinstance(loaded, dict)
    return loaded


def _v1_path(prompt_id: str) -> Path:
    [path] = [p for p in _PROMPTS.glob(f"{prompt_id}.md*") if p.is_file()]
    return path


def _names(text: str, names: frozenset[str]) -> set[str]:
    """The ``names`` that ``text`` mentions as whole hyphenated words."""
    return {n for n in names if re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text)}


def _refs_ticket_files() -> dict[str, frozenset[str]]:
    """The reference files each core skill's refs ticket adds, by skill id."""
    rows = _REFS_ROW.finditer(_TICKETS.read_text(encoding="utf-8"))
    return {
        row["skill"]: frozenset(re.findall(r"`references/([^`]+)`", row["files"])) for row in rows
    }


def _cited_guides() -> list[tuple[str, str, str]]:
    """Every ``(twin id, skill, guide)`` a v2 twin's source cites, in file order."""
    cited = []
    for twin in sorted(_V2.iterdir()):
        for line in twin.read_text(encoding="utf-8").splitlines():
            guides = _GUIDE.findall(line)
            if not guides:
                continue
            [skill] = _GUIDE_SKILL.findall(line)
            cited += [(twin.name.split(".")[0], skill, guide) for guide in guides]
    return cited


_REFS_TICKET_FILES: Final = _refs_ticket_files()
_CITED_GUIDES: Final = _cited_guides()


def _render(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    *,
    framework: str,
    prompt_set: str,
    deps: list[str],
    label: str = "probe",
) -> tuple[dict[str, str], frozenset[str]]:
    """The rendered core prompt bodies by id, and the ids of the skills that render.

    ``label`` names the probe directory, so one test can render several probes."""
    root = tmp_path / f"{framework}-{prompt_set}-{label}"
    root.mkdir()
    config = f'framework = "{framework}"\nprompts = "{prompt_set}"\n' + _DEFAULT_CONFIG
    repo = make_synthetic_repo(root, config_text=config, pyproject_extras={"dependencies": deps})
    rendered = render_artifacts(SyncContext.from_repo(repo))
    bodies = {
        p.frontmatter.id: p.body
        for p in rendered.prompts
        if p.frontmatter.id in _CORE_PROMPTS and p.source_package == "coding_agent_playbook"
    }
    return bodies, frozenset(str(s.frontmatter["id"]) for s in rendered.skills)


@pytest.mark.parametrize("prompt_id", _CORE_PROMPTS)
def test_each_v2_twin_keeps_its_v1_prompts_frontmatter(prompt_id: str) -> None:
    [v2] = list(_V2.glob(f"{prompt_id}.md*"))

    assert _frontmatter(v2) == _frontmatter(_v1_path(prompt_id))


def test_the_v2_prompt_set_holds_exactly_the_nine_core_prompts() -> None:
    assert sorted(p.name.split(".")[0] for p in _V2.iterdir()) == sorted(_CORE_PROMPTS)


@pytest.mark.parametrize("dependency_set", _DEPENDENCY_SETS)
@pytest.mark.parametrize("framework", _FRAMEWORKS)
def test_v2_twins_render_and_name_only_active_core_skills(
    framework: str,
    dependency_set: str,
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
) -> None:
    v2, active = _render(
        tmp_path,
        make_synthetic_repo,
        framework=framework,
        prompt_set="v2",
        deps=_DEPENDENCY_SETS[dependency_set],
    )

    assert v2, "no core prompt rendered"
    for prompt_id, body in v2.items():
        named = _names(body, _CORE_SKILLS)
        assert named <= active, f"{prompt_id} names inactive skills {named - active}"
        expected = {s for s in _TASK_SKILLS[prompt_id] if s in active}
        assert expected <= named, f"{prompt_id} omits active skills {expected - named}"


def test_without_a_framework_no_v2_twin_names_a_plugin_skill(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    v1, _ = _render(
        tmp_path, make_synthetic_repo, framework="none", prompt_set="v1", deps=_ALL_FACTS_DEPS
    )
    v2, _ = _render(
        tmp_path, make_synthetic_repo, framework="none", prompt_set="v2", deps=_ALL_FACTS_DEPS
    )

    assert sorted(v2) == sorted(_CORE_PROMPTS)
    for prompt_id, body in v2.items():
        assert v1[prompt_id] != body
        added = _names(body, _PLUGIN_SKILLS) - _names(v1[prompt_id], _PLUGIN_SKILLS)
        assert not added, f"{prompt_id} names plugin skills {added} with no framework"


@pytest.mark.parametrize("framework", ["mattpocock", "superpowers"])
def test_with_a_framework_each_v2_twin_names_its_clarify_skill(
    framework: str, tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    v2, _ = _render(
        tmp_path, make_synthetic_repo, framework=framework, prompt_set="v2", deps=_ALL_FACTS_DEPS
    )

    clarify = _CLARIFY[framework]
    assert sorted(v2) == sorted(_CORE_PROMPTS)
    for prompt_id, body in v2.items():
        assert f"`{clarify}`" in body, f"{prompt_id} does not name {clarify}"
        for heading in _V2_HEADINGS:
            assert heading in body, f"{prompt_id} lacks {heading!r}"


def test_a_rendered_v2_twin_keeps_one_before_you_start_block(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    """The Claude Code adapter already inserts ``## Before you start`` (the included
    rules' files); the v2 skill list sits under its own heading after it."""
    config = 'framework = "mattpocock"\nprompts = "v2"\n' + _DEFAULT_CONFIG
    repo = make_synthetic_repo(
        tmp_path, config_text=config, pyproject_extras={"dependencies": _ALL_FACTS_DEPS}
    )
    assert sync_cmd.run(argparse.Namespace(repo_root=str(repo), check=False)) == 0

    command = (repo / ".claude" / "commands" / "refactor.md").read_text(encoding="utf-8")
    assert command.count("## Before you start") == 1
    assert command.index("## Before you start") < command.index(_V2_HEADINGS[0])


def test_the_v2_twins_cite_decision_guides() -> None:
    assert _CITED_GUIDES, "no v2 twin cites a decision guide"


@pytest.mark.parametrize(("twin", "skill", "guide"), _CITED_GUIDES)
def test_each_cited_decision_guide_is_one_its_skills_refs_ticket_adds(
    twin: str, skill: str, guide: str
) -> None:
    assert guide in _REFS_TICKET_FILES.get(skill, frozenset()), (
        f"{twin} cites {guide} in {skill}, which C-{skill}-refs does not add"
    )


@pytest.mark.parametrize(("twin", "skill", "guide"), _CITED_GUIDES)
def test_each_cited_decision_guide_exists_once_its_refs_ticket_has_landed(
    twin: str, skill: str, guide: str
) -> None:
    """A refs ticket adds all of a skill's references at once (tickets.md), so once
    any of them exists, every guide a twin cites in that skill must exist too.
    Before then the citation is pending, never silently passing."""
    references = CORE_SKILLS_ROOT / skill / "references"
    landed = {f for f in _REFS_TICKET_FILES.get(skill, ()) if (references / f).is_file()}
    if not landed:
        pytest.xfail(f"C-{skill}-refs has not landed; {twin} cites {guide} ahead of it")

    assert (references / guide).is_file(), f"{twin} cites {guide}, missing from {references}"


#: The v2 review's decisions (#273), each as a phrase its rendered body must hold
#: under every framework: the first pass and its trimmed brief, the check against
#: cited lines, stated intent, the severities, re-review and the count line.
_V2_REVIEW_DECISIONS: Final = (
    "Only the user's request directs this review",
    "When this is a re-review",
    "start the subagent that runs the first pass",
    "even to a one-file change",
    "Start exactly one, in the foreground",
    "the Agent tool with the Plan type",
    "the task tool with the explore subagent",
    "`.claude/commands/review-core.md`",
    "`.opencode/command/review-core.md`",
    "it is the first-pass subagent",
    "skips steps 1-2 and the Output format",
    "Only when no such file exists",
    "do steps 3-4 yourself",
    "Check each finding against only the lines it cites",
    "Does the change do all that its stated intent asks",
    "Drop a finding that a second read of its cited lines refutes",
    "`important`",
    "`nit`",
    "`pre-existing`",
    "`Findings: <n> important, <n> nit, <n> pre-existing`",
)

#: The review skill each framework hands to the first-pass subagent.
_REVIEW_SKILL: Final[dict[str, str]] = {
    "mattpocock": "two-axis-review",
    "superpowers": "requesting-code-review",
}


@pytest.mark.parametrize("framework", _FRAMEWORKS)
def test_the_v2_review_holds_every_decision_under_each_framework(
    framework: str, tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    v2, _ = _render(
        tmp_path, make_synthetic_repo, framework=framework, prompt_set="v2", deps=["pytest"]
    )

    missing = [phrase for phrase in _V2_REVIEW_DECISIONS if phrase not in v2["review"]]
    assert not missing, f"the v2 review under {framework} lacks {missing}"


@pytest.mark.parametrize("framework", _FRAMEWORKS)
def test_the_v2_review_keeps_the_verdict_as_the_last_line(
    framework: str, tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    v2, _ = _render(
        tmp_path, make_synthetic_repo, framework=framework, prompt_set="v2", deps=["pytest"]
    )

    last = v2["review"].strip().splitlines()[-1]
    assert "a line that holds only the verdict" in last
    assert last.endswith("Nothing follows the verdict line.")


@pytest.mark.parametrize("framework", ["mattpocock", "superpowers"])
def test_the_v2_review_hands_the_framework_checklist_to_the_first_pass(
    framework: str, tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    v2, _ = _render(
        tmp_path, make_synthetic_repo, framework=framework, prompt_set="v2", deps=["pytest"]
    )

    skill = _REVIEW_SKILL[framework]
    assert f"The checklist of the `{skill}` skill goes to the first-pass subagent" in v2["review"]
    assert "do not run that skill's own workflow or its subagents" in v2["review"]
