"""Regression tests: the eval runner renders prompts the way ``playbook sync`` does.

Before the fix ``render_prompt`` rendered bare bodies with no ``rule()`` helper and
no project context, so every shipped ``.md.j2`` prompt that inlines a rule
(``review``, ``security-review``) or reads a fact (``generate-tests``) raised
``UndefinedError`` — real-runner evals of those tasks crashed before the agent ran.
The shipped-task tests pin the fix on real content; the synthetic-tree tests pin
the rendering contract (SPEC §6.2.5 inclusion, applies_if filtering, mock facts,
overlay rule precedence) hermetically.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from coding_agent_playbook.evals.loader import discover_eval_task_dirs, load_eval_task_from_dir
from coding_agent_playbook.evals.prompt_render import resolve_rules, task_facts
from coding_agent_playbook.evals.runner import PromptResolutionError, render_prompt
from coding_agent_playbook.evals.task import EvalTask, TaskInvocation, TaskSetup

_SHIPPED_TASKS_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "coding_agent_playbook"
    / "resources"
    / "eval_tasks"
)
_SHIPPED_TASK_DIRS = sorted(discover_eval_task_dirs(_SHIPPED_TASKS_ROOT))


def _shipped_task(task_id: str) -> EvalTask:
    return load_eval_task_from_dir(
        _SHIPPED_TASKS_ROOT / task_id, source_package="coding_agent_playbook"
    )


# --------------------------------------------------------------------------- #
# Shipped tasks
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("task_dir", _SHIPPED_TASK_DIRS, ids=lambda path: path.name)
def test_every_shipped_task_prompt_renders_strictly(task_dir: Path) -> None:
    task = load_eval_task_from_dir(task_dir, source_package="coding_agent_playbook")

    prompt = render_prompt(task, strict=True)

    assert not prompt.startswith(f"[prompt:{task.prompt_id}]")  # not the placeholder
    assert "{{" not in prompt
    assert "{%" not in prompt
    assert task.invocation.prompt_args in prompt


def test_review_inlines_each_rule_once_without_an_appendix() -> None:
    prompt = render_prompt(_shipped_task("review-spot-the-bug"), strict=True)

    assert prompt.count("### Python typing conventions") == 1
    assert prompt.count("### Python error handling") == 1
    assert prompt.count("## Reference rules") == 1  # the authored heading only


def test_generate_tests_renders_fixture_project_name_and_mock_kind() -> None:
    prompt = render_prompt(_shipped_task("generate-tests-happy-path"), strict=True)

    assert "generate-tests-happy-path-fixture — a `python-application` project" in prompt
    assert "### pytest conventions" in prompt


def test_security_review_includes_ml_rule_from_list_shaped_mock_ml_stack() -> None:
    """``[setup] ml_stack = [...]`` must satisfy the ML rule's ``any_ml_stack`` gate."""
    prompt = render_prompt(_shipped_task("security-review-pickle-load"), strict=True)

    assert "### ML serialization & deserialization security" in prompt


def test_plain_md_prompt_gets_generated_includes_rules_appendix() -> None:
    prompt = render_prompt(_shipped_task("refactor-extract-helper"), strict=True)

    assert "refactoring existing code" in prompt
    appendix = prompt.split("\n## Reference rules\n", 1)[1]
    assert "### Python typing conventions" in appendix
    assert "### Python error handling" in appendix


# --------------------------------------------------------------------------- #
# Synthetic resources tree (hermetic)
# --------------------------------------------------------------------------- #

_GATED_RULE = """\
---
id: fastapi-only
name: FastAPI only
description: d
scope: always
applies_if:
  has_framework: ["fastapi"]
---
FASTAPI RULE BODY
"""

_OVERRIDING_TYPING_RULE = """\
---
id: python-typing
name: Overlay typing
description: d
scope: always
---
OVERLAY TYPING BODY
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")


def _prompt_md(body: str, *, includes_rules: list[str]) -> str:
    rules = "".join(f"  - {rule_id}\n" for rule_id in includes_rules)
    return f"---\nid: p\nname: P\ndescription: d\nslash: p\nincludes_rules:\n{rules}---\n{body}"


def _synthetic_task(
    tmp_path: Path,
    *,
    prompt_file: str,
    prompt_text: str,
    rules: dict[str, str] | None = None,
    pyproject: str | None = '[project]\nname = "demo-fixture"\nrequires-python = ">=3.12"\n',
    setup: TaskSetup | None = None,
    invocation: TaskInvocation | None = None,
) -> EvalTask:
    """Lay down ``tmp/resources/{prompts,rules,eval_tasks/t/setup}`` and return its task."""
    resources = tmp_path / "resources"
    _write(resources / "prompts" / prompt_file, prompt_text)
    for name, text in (rules or {}).items():
        _write(resources / "rules" / name, text)
    task_dir = resources / "eval_tasks" / "t"
    (task_dir / "setup").mkdir(parents=True)
    if pyproject is not None:
        _write(task_dir / "setup" / "pyproject.toml", pyproject)
    return EvalTask(
        id="t",
        prompt_id="p",
        description="d",
        source_path=task_dir / "task.toml",
        source_package="overlay_pkg",
        setup=setup or TaskSetup(),
        invocation=invocation or TaskInvocation(),
    )


def test_rule_filtered_by_applies_if_is_silently_omitted(tmp_path: Path) -> None:
    task = _synthetic_task(
        tmp_path,
        prompt_file="p.md.j2",
        prompt_text=_prompt_md(
            'BEFORE\n{{ rule("fastapi-only") }}\nAFTER\n', includes_rules=["fastapi-only"]
        ),
        rules={"gated.md": _GATED_RULE},
    )

    prompt = render_prompt(task, strict=True)

    assert "BEFORE" in prompt and "AFTER" in prompt
    assert "FASTAPI RULE BODY" not in prompt


def test_framework_gate_reads_setup_pyproject(tmp_path: Path) -> None:
    task = _synthetic_task(
        tmp_path,
        prompt_file="p.md.j2",
        prompt_text=_prompt_md('{{ rule("fastapi-only") }}\n', includes_rules=["fastapi-only"]),
        rules={"gated.md": _GATED_RULE},
        pyproject='[project]\nname = "d"\nrequires-python = ">=3.12"\ndependencies = ["fastapi"]\n',
    )

    assert "FASTAPI RULE BODY" in render_prompt(task, strict=True)


def test_setup_copies_of_pyproject_owned_facts_are_ignored(tmp_path: Path) -> None:
    """``setup/pyproject.toml`` owns frameworks/python_version (``uv sync`` installs
    exactly it), so a stale ``[setup]`` copy must not change the rendered prompt."""
    task = _synthetic_task(
        tmp_path,
        prompt_file="p.md.j2",
        prompt_text=_prompt_md(
            '{{ python_version }}\n{{ rule("fastapi-only") }}\n', includes_rules=["fastapi-only"]
        ),
        rules={"gated.md": _GATED_RULE},
        setup=TaskSetup(extra_facts={"frameworks": ["fastapi"], "python_version": "3.9"}),
    )

    prompt = render_prompt(task, strict=True)

    assert prompt.startswith("3.12")  # from setup/pyproject.toml
    assert "FASTAPI RULE BODY" not in prompt


@pytest.mark.parametrize("with_dockerfile", [False, True])
def test_has_file_gate_is_anchored_at_the_setup_tree(tmp_path: Path, with_dockerfile: bool) -> None:
    rule = "---\nid: docker\nname: Docker\ndescription: d\nscope: always\napplies_if:\n  has_file: [Dockerfile]\n---\nDOCKER RULE\n"
    task = _synthetic_task(
        tmp_path,
        prompt_file="p.md.j2",
        prompt_text=_prompt_md('{{ rule("docker") }}\n', includes_rules=["docker"]),
        rules={"docker.md": rule},
    )
    if with_dockerfile:
        (task.source_path.parent / "setup" / "Dockerfile").write_text(
            "FROM python\n", encoding="utf-8"
        )

    assert ("DOCKER RULE" in render_prompt(task, strict=True)) is with_dockerfile


def test_task_tree_rule_overrides_engine_rule_and_engine_rules_still_resolve(
    tmp_path: Path,
) -> None:
    task = _synthetic_task(
        tmp_path,
        prompt_file="p.md",
        prompt_text=_prompt_md(
            "PLAIN BODY\n", includes_rules=["python-typing", "python-error-handling"]
        ),
        rules={"typing.md": _OVERRIDING_TYPING_RULE},
    )

    prompt = render_prompt(task, strict=True)

    appendix = prompt.split("\n## Reference rules\n", 1)[1]
    assert "OVERLAY TYPING BODY" in appendix  # the task tree's override wins
    assert "### Python error handling" in appendix  # engine-only rule still resolves


def test_input_variables_and_project_context_reach_the_body(tmp_path: Path) -> None:
    task = _synthetic_task(
        tmp_path,
        prompt_file="p.md.j2",
        prompt_text=_prompt_md(
            "{{ project_name }} {{ python_version }} {{ target }}\n", includes_rules=[]
        ),
        invocation=TaskInvocation(input_variables={"target": "src/x.py"}),
    )

    assert render_prompt(task, strict=True).startswith("demo-fixture 3.12 src/x.py")


def test_project_name_falls_back_to_task_id_without_pyproject(tmp_path: Path) -> None:
    task = _synthetic_task(
        tmp_path,
        prompt_file="p.md.j2",
        prompt_text=_prompt_md("NAME={{ project_name }}\n", includes_rules=[]),
        pyproject=None,
    )

    assert render_prompt(task, strict=True).startswith("NAME=t")


@pytest.mark.parametrize("strict", [True, False])
def test_broken_template_raises_prompt_resolution_error(tmp_path: Path, strict: bool) -> None:
    task = _synthetic_task(
        tmp_path,
        prompt_file="p.md.j2",
        prompt_text=_prompt_md("{{ no_such_variable }}\n", includes_rules=[]),
    )

    with pytest.raises(PromptResolutionError, match="no_such_variable"):
        render_prompt(task, strict=strict)


def test_task_facts_keep_detected_kind_unless_authored(tmp_path: Path) -> None:
    unauthored = _synthetic_task(
        tmp_path / "a", prompt_file="p.md", prompt_text=_prompt_md("x", includes_rules=[])
    )
    (unauthored.source_path.parent / "setup" / "src").mkdir()
    authored = _synthetic_task(
        tmp_path / "b",
        prompt_file="p.md",
        prompt_text=_prompt_md("x", includes_rules=[]),
        setup=TaskSetup(project_kind="ml-research", extra_facts={"ml_stack": ["torch"]}),
    )

    assert task_facts(unauthored)["project_kind"] == "python-library"  # detected from src/
    authored_facts = task_facts(authored)
    assert authored_facts["project_kind"] == "ml-research"
    assert authored_facts["ml_stack"] == {"torch": ""}


def test_resolve_rules_reads_engine_rules_for_an_engine_task() -> None:
    rule_ids = {rule.frontmatter.id for rule in resolve_rules(_shipped_task("review-spot-the-bug"))}

    assert {"python-typing", "python-error-handling", "pytest"} <= rule_ids
