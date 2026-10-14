"""Render an eval task's prompt like ``playbook sync`` would for the task's fixture.

A real runner drives a live agent with this text, so it must be the prompt a user
of the fixture project would get: the ``rule()`` helper registered and the
``includes_rules:`` appendix generated (SPEC §6.2.5), with project facts and
metadata in the Jinja context (SPEC §9.4). Before this module the runner rendered
bare bodies without either, so every shipped ``.md.j2`` prompt that inlines a rule
or reads a fact (``review``, ``security-review``, ``generate-tests``) crashed with
``UndefinedError``.

The "project" is the task's ``setup/`` tree. The detector reads its
``pyproject.toml`` (Python version, dependencies, frameworks), and the task's
``[setup]`` mock facts override what it detects: ``project_kind`` (unless left at
its ``python-unknown`` default) and extras such as ``ml_stack``. Rules come from
the engine package, overridden by id by the ``resources/rules/`` tree the task
ships in (an overlay's), mirroring overlay resolution.

Deliberate differences from ``sync``: the task's ``input_variables`` are bound in
the body's context (sync masks them so OpenCode can substitute ``$ARGUMENTS``),
the prompt's own ``applies_if`` is not evaluated (the task names its prompt
explicitly), and there are no config ``user_choices``.
"""

from __future__ import annotations

import dataclasses
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from coding_agent_playbook import __version__ as _engine_version
from coding_agent_playbook.detector import detect
from coding_agent_playbook.orchestrator import build_prompt_environment, filter_applies_if
from coding_agent_playbook.renderer import includes_rules_appendix, render_string
from coding_agent_playbook.sources.filesystem import _iter_md_files, _resource_subdir
from coding_agent_playbook.types import Rule

if TYPE_CHECKING:
    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.types import Prompt

ENGINE_PACKAGE = "coding_agent_playbook"

# Facts ``setup/pyproject.toml`` owns (C11): ``uv sync`` installs exactly what it
# declares, so a ``[setup]`` copy would make the prompt describe an environment
# the agent does not have. Stale copies in unmigrated fixtures stay ignored.
_PYPROJECT_OWNED_FACTS: frozenset[str] = frozenset(
    {"python_version", "frameworks", "dependencies", "dev_dependencies"}
)

# Detector facts shaped ``{name: version_spec}`` that ``[setup]`` may mock as a
# plain name list (``ml_stack = ["torch"]``); ``evaluate_predicate`` calls
# ``.keys()`` on them, so a list is normalized to the detector's shape.
_MAPPING_MOCK_FACTS: frozenset[str] = frozenset({"ml_stack"})

# ``TaskSetup.project_kind``'s default is also the detector's own "unknown", so
# an unauthored kind never masks the kind the detector inferred from ``setup/``.
_UNKNOWN_PROJECT_KIND = "python-unknown"


def render_task_prompt(prompt: Prompt, task: EvalTask) -> str:
    """Render ``prompt``'s body for ``task`` like ``playbook sync`` would (module docstring).

    Templated bodies render with ``rule()`` registered and the facts/project
    context plus the task's ``input_variables``; plain ``.md`` bodies pass through
    verbatim. The ``includes_rules:`` appendix is appended only when the template
    never calls ``rule()`` (SPEC §6.2.5).

    Example::

        text = render_task_prompt(prompt, task)  # review: typing rule inlined
    """
    setup_dir = task_setup_dir(task)
    facts = task_facts(task)
    context = _project_context(task, facts)
    rules = filter_applies_if(resolve_rules(task), facts, setup_dir)
    registry, prompt_env = build_prompt_environment(rules, facts)
    body = prompt.body
    if prompt.is_templated:
        body_context = {**context, **task.invocation.input_variables}
        body = render_string(prompt.template_body, body_context, env=prompt_env)
    frontmatter = dataclasses.asdict(prompt.frontmatter)
    return body + includes_rules_appendix(prompt.template_body, frontmatter, registry)


def task_setup_dir(task: EvalTask) -> Path:
    """The task's fixture tree (``<task_dir>/setup/``) — the project being rendered for."""
    return task.source_path.parent / "setup"


def task_facts(task: EvalTask) -> Facts:
    """Detector facts for the task's ``setup/`` tree, overridden by its ``[setup]`` mock facts.

    Mocks of the facts ``setup/pyproject.toml`` owns (``python_version``,
    ``frameworks``, dependencies) are ignored; the detector already read them.

    Example::

        task_facts(task)["python_version"]  # "3.12", from setup/pyproject.toml
    """
    facts: dict[str, Any] = dict(detect(task_setup_dir(task)))
    if task.setup.project_kind != _UNKNOWN_PROJECT_KIND:
        facts["project_kind"] = task.setup.project_kind
    for key, value in task.setup.extra_facts.items():
        if key not in _PYPROJECT_OWNED_FACTS:
            facts[key] = _normalize_mock_fact(key, value)
    # Mock facts are deliberately open-ended (overlays may mock new detector
    # keys), so the merged dict cannot be typed as the closed ``Facts`` shape.
    return cast("Facts", facts)


def resolve_rules(task: EvalTask) -> list[Rule]:
    """Engine rules, overridden by id by the rules in the task's own ``resources/`` tree.

    Example::

        {rule.frontmatter.id for rule in resolve_rules(task)}  # {"python-typing", ...}
    """
    by_id: dict[str, Rule] = {}
    for rules_dir, package in _rule_layers(task):
        for path in _iter_md_files(rules_dir):
            rule = Rule.from_markdown(path, package)
            by_id[rule.frontmatter.id] = rule
    return list(by_id.values())


def resources_root(task_toml: Path) -> Path | None:
    """Locate the ``resources/`` dir a task lives under, or ``None`` for a synthetic task.

    A task lives at ``<…>/resources/eval_tasks/<id>/task.toml``; its prompts and
    rules are the sibling ``<…>/resources/prompts/`` and ``<…>/resources/rules/``.
    """
    parts = task_toml.resolve().parts
    if "resources" not in parts:
        return None
    return Path(*parts[: parts.index("resources") + 1])


def _normalize_mock_fact(key: str, value: Any) -> Any:
    # ``_parse_setup`` already rejected any other shape for these keys.
    if key in _MAPPING_MOCK_FACTS and isinstance(value, list):
        return dict.fromkeys(value, "")
    return value


def _project_context(task: EvalTask, facts: Facts) -> dict[str, Any]:
    """Mirror sync's Jinja context (facts + project + engine metadata) for the fixture."""
    name, description = _fixture_project_metadata(task_setup_dir(task))
    context: dict[str, Any] = dict(facts)
    context["project_name"] = name or task.id
    context["project_description"] = description
    context["engine_version"] = _engine_version
    return context


def _fixture_project_metadata(setup_dir: Path) -> tuple[str | None, str]:
    """``[project]`` name + description from ``setup/pyproject.toml``; ``(None, "")`` if absent."""
    try:
        data = tomllib.loads((setup_dir / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None, ""
    project = data.get("project")
    if not isinstance(project, dict):
        return None, ""
    name = project.get("name")
    description = project.get("description")
    return (
        name if isinstance(name, str) else None,
        description if isinstance(description, str) else "",
    )


def _rule_layers(task: EvalTask) -> list[tuple[Path, str]]:
    """``(rules_dir, source_package)`` pairs, lowest precedence first."""
    layers: list[tuple[Path, str]] = []
    engine_dir = _resource_subdir(ENGINE_PACKAGE, "rules")
    if engine_dir is not None:
        layers.append((engine_dir, ENGINE_PACKAGE))
    root = resources_root(task.source_path)
    task_dir = root / "rules" if root is not None else None
    if task_dir is None or not task_dir.is_dir():
        return layers
    if engine_dir is None or task_dir.resolve() != engine_dir.resolve():
        layers.append((task_dir, task.source_package))
    return layers
