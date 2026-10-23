"""``RenderSession``: one render pass for sync, ``playbook render`` and the eval runner.

specs/prT-package-layout.md section 9 AC.3: each pass opens one session, which
filters the rules by ``applies_if`` once and builds one sandboxed environment and
one rule registry from the rules it kept. :class:`TemplateContext` is the Jinja
context every body renders with (SPEC §9.4).
"""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from jinja2 import UndefinedError

import coding_agent_playbook
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.commands import render as render_command
from coding_agent_playbook.config.model import Config, ProjectMeta
from coding_agent_playbook.evals.prompting import render_prompt
from coding_agent_playbook.evals.sample import EvalSample
from coding_agent_playbook.rendering.jinja import TemplateSecurityError
from coding_agent_playbook.rendering.session import RenderSession, TemplateContext
from coding_agent_playbook.sync import pipeline
from tests.fakes import FakeGitClient
from tests.hook_samples import resolved_hook, sample_hook

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.detector.facts import Facts

    SyntheticRepoFactory = Callable[..., Path]
    CaptureFixture = pytest.CaptureFixture[str]


def _facts(**values: object) -> Facts:
    """Facts with keys the detector never sets, as an eval sample's mock facts may have."""
    return cast("Facts", values)


def _rule(rule_id: str, text: str, *, applies_if: dict[str, object] | None = None) -> Rule:
    """An always rule named ``rule_id.title()``, rendered through Jinja when ``text`` holds ``{{``."""
    frontmatter = RuleFrontmatter(
        id=rule_id,
        name=rule_id.title(),
        description="d",
        scope="always",
        applies_if=dict(applies_if or {}),
    )
    return Rule(frontmatter, text, text, "{{" in text, None, "<repo-local>")


#: ``gated`` needs fastapi, which :data:`_CONTEXT`'s facts do not have.
_GATED = _rule("gated", "GATED-BODY\n", applies_if={"has_framework": ["fastapi"]})
_OPEN = _rule("open", "OPEN-BODY\n")
_CONTEXT = TemplateContext(facts={"frameworks": {}}, project_name="demo", engine_version="1.0")


def test_template_context_precedence() -> None:
    """facts < project < user_choices < engine_version and layout < overrides (RS-D6, D71)."""
    every_key = (
        "kind",
        "project_name",
        "project_description",
        "engine_version",
        "layout",
        "target",
    )
    context = TemplateContext(
        facts=_facts(**dict.fromkeys(every_key, "F")),
        project_name="P",
        project_description="P",
        engine_version="E",
        user_choices={
            "project_description": "C",
            "engine_version": "C",
            "layout": "C",
            "target": "C",
        },
        overrides={"target": "O"},
        layout={"specs": "L"},
    )

    assert context.as_dict() == {
        "kind": "F",
        "project_name": "P",
        "project_description": "C",
        "engine_version": "E",
        "layout": {"specs": "L"},
        "target": "O",
    }
    overridden = dataclasses.replace(context, overrides={"engine_version": "O"})
    assert overridden.as_dict()["engine_version"] == "O"


def test_for_config_takes_the_installed_version_when_the_config_pins_none() -> None:
    config = Config(1, ProjectMeta("demo", "python-library", "About."), "")

    context = TemplateContext.for_config(config, {"python_version": "3.12"})

    assert (context.project_name, context.project_description) == ("demo", "About.")
    assert context.engine_version == coding_agent_playbook.__version__
    assert context.as_dict()["python_version"] == "3.12"


def test_for_config_prefers_the_pinned_engine_version() -> None:
    """A pinned ``[engine] version`` wins over the installed one (RS-D6 keeps today's order)."""
    pinned = "9.9.9"
    assert pinned != coding_agent_playbook.__version__  # else the test cannot tell them apart
    config = Config(1, ProjectMeta("demo", "python-library"), pinned)

    context = TemplateContext.for_config(config, {})

    assert context.engine_version == pinned
    assert context.as_dict()["engine_version"] == pinned


def test_registry_holds_only_applicable_rules(tmp_path: Path) -> None:
    session = RenderSession.open([_GATED, _OPEN], _CONTEXT, repo_root=tmp_path)

    assert session.registry.render_for_inclusion("gated", {}) == ""
    assert session.registry.reference_for("gated") is None
    assert session.registry.render_for_inclusion("open", {}) == "### Open\n\nOPEN-BODY\n"


#: ``has_framework`` takes a list: ``playbook validate`` rejects this predicate.
_MALFORMED = _rule("malformed", "MALFORMED-BODY\n", applies_if={"has_framework": "fastapi"})


def test_open_raises_on_a_predicate_validate_would_reject(tmp_path: Path) -> None:
    """Sync and the eval runner report it (sync's validate gate normally comes first)."""
    with pytest.raises(ValueError, match="must be a list of strings"):
        RenderSession.open([_MALFORMED, _OPEN], _CONTEXT, repo_root=tmp_path)


def test_open_can_omit_a_rule_whose_predicate_validate_would_reject(tmp_path: Path) -> None:
    """``playbook render`` runs no validate gate and reads such a predicate as false (B1)."""
    session = RenderSession.open(
        [_MALFORMED, _OPEN], _CONTEXT, repo_root=tmp_path, on_malformed_predicate="omit"
    )

    assert [rule.frontmatter.id for rule in session.render_rules()] == ["open"]
    assert session.registry.render_for_inclusion("malformed", {}) == ""


def test_render_rules_renders_applicable_rules_in_input_order_with_the_full_context(
    tmp_path: Path,
) -> None:
    config = Config(
        1, ProjectMeta("acme-api", "python-library"), "1.0", user_choices={"team": "core"}
    )
    named = _rule("named", "{{ project_name }} by {{ team }}\n")
    session = RenderSession.open(
        [named, _GATED, _OPEN], TemplateContext.for_config(config, {}), repo_root=tmp_path
    )

    rendered = session.render_rules()

    assert [(rule.frontmatter.id, rule.body) for rule in rendered] == [
        ("named", "acme-api by core\n"),
        ("open", "OPEN-BODY\n"),
    ]


def test_render_rule_renders_an_inapplicable_rule_on_request(tmp_path: Path) -> None:
    """``playbook render <rule-id>`` shows a rule whatever its ``applies_if`` (RS-D4)."""
    gated = _rule("gated", "Gated for {{ project_name }}\n", applies_if={"has_framework": ["x"]})
    session = RenderSession.open([gated], _CONTEXT, repo_root=tmp_path)

    assert session.render_rule(gated).body == "Gated for demo\n"


def test_rule_bodies_see_the_detector_facts_through_the_helpers(tmp_path: Path) -> None:
    """``has_framework`` and ``has_ml_dep`` read the session's facts (SPEC §9.4)."""
    context = TemplateContext(
        facts={"frameworks": {"fastapi": "0.115"}, "ml_stack": {"torch": "2.4"}},
        project_name="demo",
        engine_version="1.0",
    )
    helpers = _rule("helpers", '{{ has_framework("fastapi") }}/{{ has_ml_dep("numpy") }}\n')
    session = RenderSession.open([helpers], context, repo_root=tmp_path)

    assert session.render_rules()[0].body == "True/False\n"
    assert session.registry.render_for_inclusion("helpers", {}) == "### Helpers\n\nTrue/False\n"


# --- prompts ------------------------------------------------------------------

#: A placeholder the OpenCode format maps to ``$ARGUMENTS`` after Jinja (SPEC §9.7).
_PLACEHOLDER_BODY = 'Run {{ target | default("{{ target }}") }}.\n'


def _prompt(text: str, *, includes: tuple[str, ...] = (), templated: bool = True) -> Prompt:
    """Prompt ``tidy`` taking the input variable ``target`` and including ``includes``."""
    frontmatter = PromptFrontmatter(
        id="tidy",
        name="Tidy",
        description="d",
        slash="tidy",
        input_variables=[{"name": "target", "description": "a file"}],
        includes_rules=list(includes),
    )
    return Prompt(frontmatter, text, text, templated, None, "<repo-local>")


def test_render_prompt_masks_input_variable_names(tmp_path: Path) -> None:
    """A fact named like an input variable leaves the ``{{ target }}`` placeholder in place."""
    context = TemplateContext(facts=_facts(target="FACT"), project_name="demo", engine_version="1")
    session = RenderSession.open([], context, repo_root=tmp_path)

    assert session.render_prompt(_prompt(_PLACEHOLDER_BODY)).body == "Run {{ target }}.\n"


def test_prompt_bodies_see_the_detector_facts_through_the_helpers(tmp_path: Path) -> None:
    context = TemplateContext(
        facts={"ml_stack": {"torch": "2.4"}}, project_name="d", engine_version="1"
    )
    session = RenderSession.open([], context, repo_root=tmp_path)
    prompt = _prompt('{% if has_ml_dep("torch") %}ml{% endif %}.\n')

    assert session.render_prompt(prompt).body == "ml.\n"
    assert session.prompt_text(prompt) == "ml.\n"


@pytest.mark.parametrize("render", ["render_prompt", "prompt_text"])
def test_a_prompt_cannot_call_rule(tmp_path: Path, render: str) -> None:
    """Regression (D15): a prompt lists its rules in ``includes_rules``; ``rule()`` is gone."""
    session = RenderSession.open([_OPEN], _CONTEXT, repo_root=tmp_path)

    with pytest.raises(UndefinedError, match="'rule' is undefined"):
        getattr(session, render)(_prompt('{{ rule("open") }}\n'))


def test_prompt_text_passes_a_plain_prompt_through_with_the_appendix(tmp_path: Path) -> None:
    session = RenderSession.open([_OPEN], _CONTEXT, repo_root=tmp_path)
    plain = _prompt("Keep {{ target }}.\n", includes=("open",), templated=False)

    text = session.prompt_text(plain)

    assert text == "Keep {{ target }}.\n\n## Reference rules\n\n### Open\n\nOPEN-BODY\n"
    assert session.render_prompt(plain) is plain


def test_prompt_text_keeps_invocation_values_and_appends_reference_rules(tmp_path: Path) -> None:
    """The eval runner's text: the invocation's ``target`` substituted, then the appendix (D22)."""
    context = TemplateContext(
        facts={"frameworks": {}},
        project_name="demo",
        engine_version="1",
        overrides={"target": "src/x.py"},
    )
    session = RenderSession.open([_GATED, _OPEN], context, repo_root=tmp_path)

    text = session.prompt_text(_prompt(_PLACEHOLDER_BODY, includes=("gated", "open")))

    assert text == "Run src/x.py.\n\n## Reference rules\n\n### Open\n\nOPEN-BODY\n"


def test_check_inclusions_names_the_file_of_a_sandbox_escape(tmp_path: Path) -> None:
    """The escape fires only in the facts-only render an adapter's appendix repeats (D15)."""
    source = tmp_path / "playbook" / "rules" / "evil.md.j2"
    evil = dataclasses.replace(
        _rule(
            "evil", '{% if project_name is not defined %}{{ lipsum.__globals__["os"] }}{% endif %}'
        ),
        source_path=source,
    )
    session = RenderSession.open([evil], _CONTEXT, repo_root=tmp_path)
    assert session.render_rules()[0].body == ""  # the full context does not escape

    with pytest.raises(TemplateSecurityError) as caught:
        session.check_inclusions([_prompt("Tidy.\n", includes=("evil",))])

    assert caught.value.source == str(source)


# --- the three callers converge (AC.3.1) ------------------------------------------

_GATED_MD = (
    "---\nid: gated\nname: Gated\ndescription: d\nscope: always\npriority: 50\n"
    'applies_if:\n  has_framework: ["fastapi"]\n---\nGATED-BODY\n'
)
_OPEN_MD = (
    "---\nid: open\nname: Open\ndescription: d\nscope: always\npriority: 50\n---\nOPEN-BODY\n"
)
_TIDY_MD = (
    "---\nid: tidy\nname: Tidy\ndescription: d\nslash: tidy\nversion: 1\n"
    "includes_rules:\n  - gated\n  - open\n---\nTidy up.\n"
)


def _write_layer(root: Path) -> Path:
    """``root/playbook`` with rules ``gated`` (needs fastapi) and ``open``, and prompt ``tidy``."""
    for kind, name, text in (("rules", "gated", _GATED_MD), ("rules", "open", _OPEN_MD)):
        (root / "playbook" / kind).mkdir(parents=True, exist_ok=True)
        (root / "playbook" / kind / f"{name}.md").write_text(text, encoding="utf-8")
    return root


def _via_sync(tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, _: CaptureFixture) -> str:
    repo = make_synthetic_repo(
        tmp_path, prompts=[("tidy", {"body": "Tidy up.\n", "includes_rules": ["gated", "open"]})]
    )
    assert pipeline.execute(_write_layer(repo), git=FakeGitClient()) == 0
    return (repo / ".continue" / "prompts" / "tidy.md").read_text(encoding="utf-8")


def _via_render(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: CaptureFixture
) -> str:
    repo = make_synthetic_repo(
        tmp_path, prompts=[("tidy", {"body": "Tidy up.\n", "includes_rules": ["gated", "open"]})]
    )
    args = argparse.Namespace(
        repo_root=str(_write_layer(repo)),
        id="tidy",
        format="prompt_continue",
        show_source=False,
        show_rules=False,
    )
    assert render_command.run(args) == 0
    return capsys.readouterr().out


def _via_eval_runner(tmp_path: Path, _: SyntheticRepoFactory, __: CaptureFixture) -> str:
    layer = tmp_path / "layer"
    (layer / "prompts").mkdir(parents=True)
    (layer / "prompts" / "tidy.md").write_text(_TIDY_MD, encoding="utf-8")
    sample_dir = layer / "eval_samples" / "tidy-sample"
    _write_layer(sample_dir / "setup")
    sample = EvalSample(
        id="tidy-sample",
        prompt_id="tidy",
        description="d",
        source_path=sample_dir / "sample.toml",
        source_package="coding_agent_playbook",
    )
    return render_prompt(sample, strict=True)


@pytest.mark.parametrize(
    "render_tidy", [_via_sync, _via_render, _via_eval_runner], ids=["sync", "render", "eval-runner"]
)
def test_every_caller_omits_an_inapplicable_included_rule(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: CaptureFixture,
    render_tidy: Callable[[Path, SyntheticRepoFactory, CaptureFixture], str],
) -> None:
    """The convergence test: ``gated`` needs fastapi, so no caller inlines it (B1 has render's)."""
    text = render_tidy(tmp_path, make_synthetic_repo, capsys)

    assert "### Open\n\nOPEN-BODY" in text
    assert "### Gated" not in text


def _render_out(repo: Path, capsys: CaptureFixture, artifact_id: str, **flags: object) -> str:
    """``playbook render <artifact_id>`` with ``flags``; asserts exit 0 and returns stdout."""
    args = {"format": None, "show_source": False, "show_rules": False, **flags}
    namespace = argparse.Namespace(repo_root=str(repo), id=artifact_id, **args)
    assert render_command.run(namespace) == 0
    return capsys.readouterr().out


def test_render_reports_and_omits_a_rule_whose_predicate_validate_would_reject(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: CaptureFixture
) -> None:
    """``--show-rules``, ``--show-source`` and the rendered prompt agree (AC.3.5, B1)."""
    repo = make_synthetic_repo(
        tmp_path, prompts=[("tidy", {"body": "Tidy up.\n", "includes_rules": ["gated", "open"]})]
    )
    _write_layer(repo)
    malformed = _GATED_MD.replace('["fastapi"]', '"fastapi"')  # a string, not a list
    (repo / "playbook" / "rules" / "gated.md").write_text(malformed, encoding="utf-8")

    shown = _render_out(repo, capsys, "tidy", show_rules=True)
    source = _render_out(repo, capsys, "gated", show_source=True)
    rendered = _render_out(repo, capsys, "tidy", format="prompt_continue")

    assert "  - gated  (<repo-local>, applies_if=False -> OMITTED)" in shown
    assert source.endswith("applies_if evaluated: False\n")
    assert "GATED-BODY" not in rendered
    assert "OPEN-BODY" in rendered


# --- hook bodies (prK §A.8, §C.1.3, H19) ----------------------------------------
# Only a hook's advisory body passes through Jinja: frontmatter, handler commands
# and scripts never do. These were the tests of sync.render's render_hook_body.

_HOOK_PATH = "playbook/hooks/protect/guard-x/HOOK.md.j2"


def _hook(body: str, *, templated: bool = True) -> Hook:
    hook = sample_hook(path=_HOOK_PATH)
    return dataclasses.replace(hook, body=body, template_body=body, is_templated=templated)


def _hook_session(tmp_path: Path) -> RenderSession:
    return RenderSession.open([], _CONTEXT, repo_root=tmp_path)


def test_plain_hook_body_is_verbatim(tmp_path: Path) -> None:
    hook = _hook("Keep {{ braces }}.\n", templated=False)

    assert _hook_session(tmp_path).render_hook_body(hook) == "Keep {{ braces }}.\n"


def test_templated_hook_body_renders_from_the_template_not_a_prior_render(tmp_path: Path) -> None:
    hook = dataclasses.replace(_hook("Guard {{ project_name }}.\n"), body="Guard old.\n")

    assert _hook_session(tmp_path).render_hook_body(hook) == "Guard demo.\n"


def test_hook_body_cannot_call_rule(tmp_path: Path) -> None:
    with pytest.raises(UndefinedError, match="'rule' is undefined"):
        _hook_session(tmp_path).render_hook_body(_hook("{{ rule('python-style') }}\n"))


def test_hook_sandbox_violation_names_the_hook_file(tmp_path: Path) -> None:
    with pytest.raises(TemplateSecurityError) as caught:
        _hook_session(tmp_path).render_hook_body(_hook("{{ cycler.__init__.__globals__ }}\n"))

    assert caught.value.source == str(Path(_HOOK_PATH))


def test_hook_sandbox_violation_without_a_path_names_the_hook_id(tmp_path: Path) -> None:
    hook = dataclasses.replace(_hook("{{ cycler.__init__.__globals__ }}\n"), source_path=None)

    with pytest.raises(TemplateSecurityError) as caught:
        _hook_session(tmp_path).render_hook_body(hook)

    assert caught.value.source == "guard-x"


def test_with_hook_body_renders_the_definition_into_the_advisory(tmp_path: Path) -> None:
    resolved = resolved_hook(body="placeholder\n")
    assert resolved.definition is not None
    definition = dataclasses.replace(
        resolved.definition, template_body="Guard {{ project_name }}.\n", is_templated=True
    )

    hook = _hook_session(tmp_path).with_hook_body(
        dataclasses.replace(resolved, definition=definition)
    )

    assert hook.definition is not None
    assert hook.definition.body == "Guard demo.\n"
    assert hook.advisory is not None
    assert hook.advisory.body.startswith("Guard demo.\n")


def test_with_hook_body_passes_a_hook_built_in_memory_through(tmp_path: Path) -> None:
    hook = dataclasses.replace(resolved_hook(), definition=None)

    assert _hook_session(tmp_path).with_hook_body(hook) is hook
