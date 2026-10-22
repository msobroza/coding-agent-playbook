"""The core v2 prompt set points to skills (D76, D74; prU C-prompts-v2).

Each ``catalog/core/prompts/v2/`` prompt is its v1 twin plus three parts: the core
skills to load before the task, what to do when something is unclear, and the
framework skills and decision guides that check the work. These tests sync a probe
repo with ``prompts = "v2"`` under no framework, mattpocock_skills and superpowers,
then read the rendered prompts.
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

#: Every core skill a v2 prompt may name, shipped today or planned (D76).
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

#: A probe repo every v2 prompt applies to (pytest, FastAPI, an ML stack).
_ALL_FACTS_DEPS: Final = ["pytest", "fastapi", "sqlalchemy", "torch", "pandas", "numpy"]

#: The three parts D76 adds, in order.
_V2_HEADINGS: Final = (
    "## Skills for this task",
    "## If something is unclear",
    "## Check and improve your work",
)

_FRAMEWORKS: Final = ("none", "mattpocock", "superpowers")
#: The clarify skill each framework names (D74), absent without one.
_CLARIFY: Final = {"none": None, "mattpocock": "grill-me", "superpowers": "brainstorming"}


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


def _render(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    *,
    framework: str,
    prompt_set: str,
    deps: list[str],
) -> tuple[dict[str, str], frozenset[str]]:
    """The rendered core prompt bodies by id, and the ids of the skills that render."""
    root = tmp_path / f"{framework}-{prompt_set}-{len(deps)}"
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
def test_each_v2_prompt_keeps_its_v1_twins_frontmatter(prompt_id: str) -> None:
    [v2] = list(_V2.glob(f"{prompt_id}.md*"))

    assert _frontmatter(v2) == _frontmatter(_v1_path(prompt_id))


def test_the_v2_set_holds_exactly_the_nine_core_prompts() -> None:
    assert sorted(p.name.split(".")[0] for p in _V2.iterdir()) == sorted(_CORE_PROMPTS)


@pytest.mark.parametrize("framework", _FRAMEWORKS)
def test_v2_prompts_render_and_name_only_active_core_skills(
    framework: str, tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    for deps in (_ALL_FACTS_DEPS, ["pytest"]):
        v2, active = _render(
            tmp_path, make_synthetic_repo, framework=framework, prompt_set="v2", deps=deps
        )
        assert v2, "no core prompt rendered"
        for prompt_id, body in v2.items():
            named = _names(body, _CORE_SKILLS)
            assert named <= active, f"{prompt_id} names inactive skills {named - active}"
            expected = {s for s in _TASK_SKILLS[prompt_id] if s in active}
            assert expected <= named, f"{prompt_id} omits active skills {expected - named}"


def test_without_a_framework_no_v2_prompt_names_a_plugin_skill(
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
def test_with_a_framework_each_v2_prompt_names_its_clarify_skill(
    framework: str, tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    v2, _ = _render(
        tmp_path, make_synthetic_repo, framework=framework, prompt_set="v2", deps=_ALL_FACTS_DEPS
    )

    clarify = _CLARIFY[framework]
    assert clarify is not None
    assert sorted(v2) == sorted(_CORE_PROMPTS)
    for prompt_id, body in v2.items():
        assert f"`{clarify}`" in body, f"{prompt_id} does not name {clarify}"
        for heading in _V2_HEADINGS:
            assert heading in body, f"{prompt_id} lacks {heading!r}"


def test_a_v2_command_keeps_one_before_you_start_block(
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
