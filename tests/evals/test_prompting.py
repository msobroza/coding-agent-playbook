"""Tests for eval prompt rendering (``evals/prompting.py``).

An eval task's prompt must render exactly as ``playbook sync`` renders it for a
consumer: the ``rule()`` helper resolves through a rule registry, and the Jinja
context carries the detector facts + project metadata. Before this module the
runner rendered with a bare environment, so 7 of the 20 shipped tasks crashed
with ``UndefinedError`` (``rule`` for review/security-review, ``project_name``
for generate-tests) — even under the hermetic ``FakeRunner``.
"""

from __future__ import annotations

import sys
import textwrap
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.loader import load_eval_task_from_dir
from coding_agent_playbook.evals.prompting import (
    PromptResolutionError,
    _infer_prompts_dir,
    render_prompt,
)
from coding_agent_playbook.evals.task import EvalTask, TaskInvocation, TaskSetup
from tests._catalog import CORE_ROOT

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.catalog

_ENGINE = "coding_agent_playbook"
_SHIPPED_TASKS = CORE_ROOT / "eval_tasks"


def _shipped_task_dirs() -> list[Path]:
    return sorted(p for p in _SHIPPED_TASKS.iterdir() if (p / "task.toml").is_file())


def _shipped(task_id: str) -> EvalTask:
    return load_eval_task_from_dir(_SHIPPED_TASKS / task_id, source_package=_ENGINE)


# --------------------------------------------------------------------------- #
# Every shipped task renders strictly (regression: 7/20 crashed)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("task_dir", _shipped_task_dirs(), ids=lambda p: p.name)
def test_every_shipped_task_prompt_renders_strictly(task_dir: Path) -> None:
    """A real runner renders with ``strict=True``; no shipped task may crash."""
    task = load_eval_task_from_dir(task_dir, source_package=_ENGINE)
    prompt = render_prompt(task, strict=True)
    assert prompt.strip()
    assert not prompt.startswith(f"[prompt:{task.prompt_id}]")  # not the placeholder
    if task.invocation.prompt_args:
        assert prompt.rstrip().endswith(task.invocation.prompt_args)


def test_rule_helper_inlines_the_referenced_rule() -> None:
    """``{{ rule("python-error-handling") }}`` inlines that rule's header + body."""
    prompt = render_prompt(_shipped("review-spot-the-bug"), strict=True)
    assert "### Error handling" in prompt


def test_mocked_ml_stack_list_satisfies_any_ml_stack() -> None:
    """``[setup] ml_stack = ["torch", …]`` gates the ML rule in.

    Task TOML authors mock facts as a *list* of names while the detector emits a
    ``{name: version}`` dict; ``any_ml_stack`` reads ``.keys()``, so the list must
    be normalized or the predicate crashes.
    """
    prompt = render_prompt(_shipped("security-review-pickle-load"), strict=True)
    assert "### ML serialization & deserialization security" in prompt


def test_project_name_comes_from_the_setup_pyproject() -> None:
    """``{{ project_name }}`` resolves to the fixture's ``[project].name``."""
    prompt = render_prompt(_shipped("generate-tests-happy-path"), strict=True)
    assert "generate-tests-happy-path-fixture" in prompt


def test_authored_project_kind_is_the_mock_detector_fact() -> None:
    """``[setup].project_kind`` overrides what the detector infers from setup/."""
    prompt = render_prompt(_shipped("generate-tests-happy-path"), strict=True)
    assert "`python-application` project" in prompt


# --------------------------------------------------------------------------- #
# Prompt directory — found by layer, not by a ``resources`` path segment
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "layer_parts",
    [("catalog", "core"), ("pkg", "resources"), ("playbook",)],
    ids=["catalog", "overlay-resources", "repo-local"],
)
def test_infer_prompts_dir_layers(tmp_path: Path, layer_parts: tuple[str, ...]) -> None:
    """``<layer>/eval_tasks/<dir>/task.toml`` finds ``<layer>/prompts`` in every layer.

    The bundled layer (``catalog/core``) has no ``resources`` segment, and a
    repo-local task never found its prompts before.
    """
    layer = tmp_path.joinpath(*layer_parts)
    task_toml = layer / "eval_tasks" / "t" / "task.toml"
    assert _infer_prompts_dir(task_toml) == layer / "prompts"


def test_infer_prompts_dir_non_task_path(tmp_path: Path) -> None:
    """A task dir whose parent is not ``eval_tasks`` has no prompts layer."""
    assert _infer_prompts_dir(tmp_path / "t" / "task.toml") is None


def test_infer_prompts_dir_does_not_resolve_symlinks(tmp_path: Path) -> None:
    """A symlinked task dir maps to the layer it is reached through, not its target's."""
    target = tmp_path / "target_layer" / "eval_tasks" / "t"
    target.mkdir(parents=True)
    (target / "task.toml").write_text("", encoding="utf-8")
    link_layer = tmp_path / "link_layer"
    (link_layer / "eval_tasks").mkdir(parents=True)
    (link_layer / "eval_tasks" / "t").symlink_to(target, target_is_directory=True)

    task_toml = link_layer / "eval_tasks" / "t" / "task.toml"
    assert _infer_prompts_dir(task_toml) == link_layer / "prompts"


def test_strict_unresolved_prompt_hint_points_at_the_layers_prompts_dir(tmp_path: Path) -> None:
    """The strict-mode hint names where the lookup really happens.

    Regression: it said to check "that resources/prompts/ is reachable", but the
    engine's own content has no ``resources/`` since v0.19, and every layer's
    prompts are found next to its ``eval_tasks/`` (:func:`_infer_prompts_dir`).
    """
    task_dir = tmp_path / "catalog" / "core" / "eval_tasks" / "orphan-task"
    (task_dir / "setup").mkdir(parents=True)
    task = EvalTask(
        id="orphan-task",
        prompt_id="no-such-prompt",
        description="A task whose prompt is not shipped.",
        source_path=task_dir / "task.toml",
        source_package=_ENGINE,
        setup=TaskSetup(),
        invocation=TaskInvocation(prompt_args="go"),
    )

    with pytest.raises(PromptResolutionError) as raised:
        render_prompt(task, strict=True)

    message = str(raised.value)
    assert "resources/prompts" not in message
    assert "the prompts/ directory next to the task's eval_tasks/" in message


# --------------------------------------------------------------------------- #
# Synthetic resources tree — failure modes
# --------------------------------------------------------------------------- #


def _synthetic_task(
    tmp_path: Path,
    prompt_body: str,
    *,
    templated: bool = True,
    pyproject: str | None = None,
    setup: TaskSetup | None = None,
) -> EvalTask:
    """Lay down ``<tmp>/pkg/resources/{prompts,eval_tasks}`` with one prompt + task."""
    resources = tmp_path / "pkg" / "resources"
    prompts = resources / "prompts"
    prompts.mkdir(parents=True)
    suffix = ".md.j2" if templated else ".md"
    (prompts / f"synthetic{suffix}").write_text(
        textwrap.dedent(
            """\
            ---
            id: synthetic
            name: Synthetic
            description: A synthetic prompt for tests.
            slash: synthetic
            version: 1
            ---
            """
        )
        + prompt_body,
        encoding="utf-8",
    )
    task_dir = resources / "eval_tasks" / "synthetic-task"
    (task_dir / "setup").mkdir(parents=True)
    if pyproject is not None:
        (task_dir / "setup" / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return EvalTask(
        id="synthetic-task",
        prompt_id="synthetic",
        description="DO-NOT-LEAK task description",
        source_path=task_dir / "task.toml",
        source_package=_ENGINE,
        setup=setup or TaskSetup(),
        invocation=TaskInvocation(prompt_args="go"),
    )


def test_render_error_raises_prompt_resolution_error_even_when_not_strict(
    tmp_path: Path,
) -> None:
    """A resolvable prompt that fails to render is an authoring bug, not a placeholder.

    ``strict`` only governs the *unresolvable*-prompt fallback; a typo'd variable
    in a prompt that does resolve must fail loudly for every runner, and must name
    the task and prompt rather than surfacing a bare Jinja ``UndefinedError``.
    """
    task = _synthetic_task(tmp_path, "Hello {{ no_such_variable }}\n")
    with pytest.raises(PromptResolutionError, match=r"synthetic-task.*no_such_variable"):
        render_prompt(task, strict=False)


def test_non_templated_prompt_is_passed_through_verbatim(tmp_path: Path) -> None:
    """A plain ``.md`` prompt is not run through Jinja (mirrors ``playbook sync``)."""
    task = _synthetic_task(tmp_path, "Literal {{ braces }} stay as written.\n", templated=False)
    assert "Literal {{ braces }} stay as written." in render_prompt(task, strict=True)


def test_input_variables_and_facts_reach_the_template(tmp_path: Path) -> None:
    """``input_variables`` + mock facts + project metadata are all in the context."""
    task = _synthetic_task(
        tmp_path,
        "{{ project_name }}|{{ project_kind }}|{{ target }}|{{ has_ml_dep('torch') }}\n",
        pyproject='[project]\nname = "demo-fixture"\nversion = "0.1.0"\n',
        setup=TaskSetup(project_kind="ml-research", extra_facts={"ml_stack": ["torch"]}),
    )
    task.invocation.input_variables["target"] = "src/x.py::f"
    assert "demo-fixture|ml-research|src/x.py::f|True" in render_prompt(task, strict=True)


@pytest.mark.parametrize(
    ("ml_stack", "inlined"),
    [(["torch"], True), (None, False)],
    ids=["ml-project", "non-ml-project"],
)
def test_rule_helper_honours_the_rule_applies_if(
    tmp_path: Path, ml_stack: list[str] | None, inlined: bool
) -> None:
    """``rule()`` inlines a gated rule only when its ``applies_if`` holds.

    A filtered-out rule renders as ``""`` — the silent-omission contract of
    SPEC §6.2.5, identical to ``playbook sync``.
    """
    extra = {"ml_stack": ml_stack} if ml_stack is not None else {}
    task = _synthetic_task(
        tmp_path,
        'Review.\n{{ rule("ml-serialization-security") }}\n',
        setup=TaskSetup(extra_facts=extra),
    )
    prompt = render_prompt(task, strict=True)
    assert ("### ML serialization & deserialization security" in prompt) is inlined


def test_project_name_falls_back_to_the_task_id_without_a_pyproject(tmp_path: Path) -> None:
    """No ``setup/pyproject.toml`` ⇒ the task id names the project.

    Never the task ``description``: that narrates the scenario (often the bug the
    agent is meant to find), so it must not leak into the agent's prompt.
    """
    task = _synthetic_task(tmp_path, "{{ project_name }}: {{ project_description }}\n")
    prompt = render_prompt(task, strict=True)
    assert prompt.startswith("synthetic-task: ")
    assert "DO-NOT-LEAK" not in prompt


def test_input_variables_win_over_facts_and_project_metadata(tmp_path: Path) -> None:
    """An ``input_variables`` key overrides a same-named fact or project field."""
    task = _synthetic_task(
        tmp_path,
        "{{ project_name }}|{{ project_kind }}\n",
        pyproject='[project]\nname = "from-pyproject"\nversion = "0.1.0"\n',
        setup=TaskSetup(project_kind="ml-research"),
    )
    task.invocation.input_variables.update(project_name="from-invocation", project_kind="cli")
    assert "from-invocation|cli" in render_prompt(task, strict=True)


@pytest.mark.parametrize(
    "extra_facts",
    [{"ml_stack": "torch"}, {"python_version": 3.12}],
    ids=["ml_stack-as-string", "python_version-as-float"],
)
def test_mis_shaped_mock_facts_raise_prompt_resolution_error(
    tmp_path: Path, extra_facts: dict[str, object]
) -> None:
    """A bad mock fact reaching a rule predicate is an authoring error, not a crash.

    Predicates run when the prompt inlines a rule. ``playbook eval --run`` maps
    :class:`PromptResolutionError` to exit 2; a raw ``AttributeError`` /
    ``TypeError`` would surface as a traceback and exit 1 — the code for a
    *failing* report.
    """
    task = _synthetic_task(
        tmp_path,
        '{{ rule("python-error-handling") }}\n',
        setup=TaskSetup(extra_facts=extra_facts),
    )
    with pytest.raises(PromptResolutionError, match="failed to render"):
        render_prompt(task, strict=True)


def test_async_prompt_sees_pytest_asyncio_from_main_dependencies() -> None:
    """``pytest-asyncio`` in ``[project].dependencies`` counts as available.

    The generate-tests prompt and the pytest rule used to check only
    ``dev_dependencies``, so this task's prompt told the agent the plugin was
    missing ("stop and ask first") — working against the task itself.
    """
    prompt = render_prompt(_shipped("generate-tests-async-code"), strict=True)
    assert "with `pytest-asyncio` available" in prompt
    assert "This project has `pytest-asyncio` installed" in prompt
    assert "does not currently depend on `pytest-asyncio`" not in prompt


# --------------------------------------------------------------------------- #
# Overlay tasks — rules resolve by id before applies_if (sync parity)
# --------------------------------------------------------------------------- #

_OVERLAY = "temp_prompting_overlay"


@pytest.fixture
def overlay_package(tmp_path: Path) -> Iterator[Path]:
    """An importable overlay package at ``<tmp>/temp_prompting_overlay``."""
    package = tmp_path / _OVERLAY
    (package / "resources").mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        yield package / "resources"
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop(_OVERLAY, None)


def _overlay_rule(resources: Path, rule_id: str, *, name: str, applies_if: str = "") -> None:
    rules = resources / "rules"
    rules.mkdir(exist_ok=True)
    (rules / f"{rule_id}.md").write_text(
        f"---\nid: {rule_id}\nname: {name}\ndescription: d\nversion: 1\nscope: always\n"
        f"{applies_if}---\nOverlay body for {rule_id}.\n",
        encoding="utf-8",
    )


def _overlay_task(resources: Path, prompt_body: str) -> EvalTask:
    (resources / "prompts").mkdir()
    (resources / "prompts" / "overlay-prompt.md.j2").write_text(
        "---\nid: overlay-prompt\nname: O\ndescription: d\nslash: o\nversion: 1\n---\n"
        + prompt_body,
        encoding="utf-8",
    )
    task_dir = resources / "eval_tasks" / "overlay-task"
    (task_dir / "setup").mkdir(parents=True)
    return EvalTask(
        id="overlay-task",
        prompt_id="overlay-prompt",
        description="d",
        source_path=task_dir / "task.toml",
        source_package=_OVERLAY,
    )


def test_overlay_task_can_inline_an_overlay_only_rule(overlay_package: Path) -> None:
    _overlay_rule(overlay_package, "bank-house-rule", name="Bank house rule")
    task = _overlay_task(overlay_package, '{{ rule("bank-house-rule") }}\n')
    assert "### Bank house rule" in render_prompt(task, strict=True)


def test_overlay_override_with_false_applies_if_drops_the_rule(overlay_package: Path) -> None:
    """An overlay override that does not apply removes the rule — as in sync.

    Filtering before resolving ids used to drop the overlay copy and let the
    engine rule it replaces leak back into the prompt.
    """
    _overlay_rule(
        overlay_package,
        "python-error-handling",
        name="Overlay error handling",
        applies_if="applies_if:\n  any_ml_stack: [torch]\n",
    )
    task = _overlay_task(overlay_package, 'Start.\n{{ rule("python-error-handling") }}\nEnd.\n')
    prompt = render_prompt(task, strict=True)
    assert "### Error handling" not in prompt  # the engine body did not leak back
    assert "Overlay body" not in prompt


def test_detected_project_kind_wins_over_the_unauthored_default(tmp_path: Path) -> None:
    """With no authored ``[setup] project_kind`` the detector's kind is used."""
    task = _synthetic_task(
        tmp_path,
        "kind={{ project_kind }}\n",
        pyproject='[project]\nname = "x"\nversion = "0.1"\ndependencies = ["fastapi"]\n',
    )
    package = task.source_path.parent / "setup" / "src" / "app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    prompt = render_prompt(task, strict=True)
    assert "kind=python-application" in prompt


def _broken_rule(task: EvalTask, *, as_directory: bool = False) -> None:
    rules = task.source_path.parent / "setup" / "playbook" / "rules"
    rules.mkdir(parents=True)
    if as_directory:
        (rules / "bad.md").mkdir()
        return
    (rules / "bad.md").write_text("---\nid: [unclosed\nname: x\n---\nbody\n", encoding="utf-8")


@pytest.mark.parametrize("as_directory", [False, True], ids=["bad-yaml", "directory"])
def test_a_broken_rule_file_fails_only_prompts_that_inline_rules(
    tmp_path: Path, as_directory: bool
) -> None:
    """Rules load lazily, on the first ``rule()`` call.

    A prompt that inlines no rule must not be broken by an unrelated bad file;
    one that does gets a :class:`PromptResolutionError` (exit 2), never a raw
    ``yaml`` / ``OSError`` traceback (exit 1, a "failing report").
    """
    plain = _synthetic_task(tmp_path / "plain", "No rules here, {{ project_name }}.\n")
    _broken_rule(plain, as_directory=as_directory)
    assert "No rules here" in render_prompt(plain, strict=True)

    inlining = _synthetic_task(tmp_path / "inlining", '{{ rule("python-error-handling") }}\n')
    _broken_rule(inlining, as_directory=as_directory)
    with pytest.raises(PromptResolutionError, match="failed to render"):
        render_prompt(inlining, strict=True)


def _sandbox_escaping_rule(task: EvalTask) -> Path:
    """Lay down ``setup/playbook/rules/evil.md.j2`` whose body escapes the Jinja sandbox."""
    rules = task.source_path.parent / "setup" / "playbook" / "rules"
    rules.mkdir(parents=True)
    rule = rules / "evil.md.j2"
    rule.write_text(
        "---\nid: evil\nname: Evil\ndescription: Escapes the sandbox.\n"
        "scope: always\npriority: 50\nversion: 1\n---\n"
        "{{ lipsum.__globals__['os'].__name__ }}\n",
        encoding="utf-8",
    )
    return rule


@pytest.mark.parametrize("strict", [False, True], ids=["fake-runner", "real-runner"])
def test_sandbox_violation_in_inlined_rule_raises_prompt_resolution_error(
    tmp_path: Path, strict: bool
) -> None:
    """Regression: a ``rule()``-inlined rule tripping the sandbox is a render error.

    ``RuleRegistryImpl`` raises ``renderer.TemplateSecurityError`` (a plain
    ``Exception``, not a jinja ``TemplateError``), which escaped ``render_prompt``
    as a raw traceback: ``playbook eval --run`` then exited 1 ("task failed")
    instead of 2. The same escape written in the prompt body was already handled.
    """
    task = _synthetic_task(tmp_path, 'Review.\n{{ rule("evil") }}\n')
    _sandbox_escaping_rule(task)
    with pytest.raises(PromptResolutionError, match=r"synthetic-task") as excinfo:
        render_prompt(task, strict=strict)
    assert "evil.md.j2" in str(excinfo.value)
    assert "sandbox" in str(excinfo.value)


def test_sandbox_violation_in_prompt_body_raises_prompt_resolution_error(
    tmp_path: Path,
) -> None:
    """The direct escape (jinja's own ``SecurityError``) takes the same exit path."""
    task = _synthetic_task(tmp_path, "{{ lipsum.__globals__['os'].__name__ }}\n")
    with pytest.raises(PromptResolutionError, match=r"synthetic-task.*__globals__"):
        render_prompt(task, strict=False)


@pytest.mark.parametrize("with_dockerfile", [False, True])
def test_has_file_rule_gate_resolves_against_the_setup_tree(
    tmp_path: Path, with_dockerfile: bool
) -> None:
    """``has_file`` paths are checked inside ``setup/`` (the project the agent works in),
    never against the eval process's working directory."""
    task = _synthetic_task(tmp_path, '{{ rule("needs-dockerfile") }}\n')
    setup = task.source_path.parent / "setup"
    rules = setup / "playbook" / "rules"
    rules.mkdir(parents=True)
    (rules / "needs-dockerfile.md").write_text(
        textwrap.dedent(
            """\
            ---
            id: needs-dockerfile
            name: Needs Dockerfile
            description: Gated on a Dockerfile.
            scope: always
            applies_if:
              has_file: ["Dockerfile"]
            ---
            DOCKERFILE RULE BODY
            """
        ),
        encoding="utf-8",
    )
    if with_dockerfile:
        (setup / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")

    assert ("DOCKERFILE RULE BODY" in render_prompt(task, strict=True)) is with_dockerfile
