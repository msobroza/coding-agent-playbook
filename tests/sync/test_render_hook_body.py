"""``render_hook_body``: only a hook's advisory body passes through Jinja (prK §A.8, §C.1.3, H19).

A ``HOOK.md`` body is returned verbatim; a ``HOOK.md.j2`` body renders in the
sandboxed base environment, which has no ``rule()`` helper (D15), so a call is
undefined, and an attribute escape names the hook's file. Frontmatter, handler
commands and scripts are never rendered.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from jinja2.exceptions import UndefinedError

from coding_agent_playbook.renderer import TemplateSecurityError, build_environment
from coding_agent_playbook.sync.render import render_hook_body
from tests.hook_samples import sample_hook

if TYPE_CHECKING:
    from coding_agent_playbook.types import Hook

_PATH = "playbook/hooks/protect/guard-x/HOOK.md.j2"


def _hook(body: str, *, templated: bool = True) -> Hook:
    hook = sample_hook(path=_PATH)
    return dataclasses.replace(hook, body=body, template_body=body, is_templated=templated)


def _render(hook: Hook, **context: object) -> str:
    return render_hook_body(hook, dict(context), build_environment([]))


def test_plain_body_is_verbatim() -> None:
    assert _render(_hook("Keep {{ braces }}.\n", templated=False)) == "Keep {{ braces }}.\n"


def test_templated_body_renders_the_context() -> None:
    assert _render(_hook("Guard {{ project_name }}.\n"), project_name="demo") == "Guard demo.\n"


def test_templated_body_renders_from_the_template_not_a_prior_render() -> None:
    hook = dataclasses.replace(_hook("Guard {{ project_name }}.\n"), body="Guard old.\n")

    assert _render(hook, project_name="new") == "Guard new.\n"


def test_hook_body_cannot_call_rule() -> None:
    with pytest.raises(UndefinedError, match="'rule' is undefined"):
        _render(_hook("{{ rule('python-style') }}\n"))


def test_sandbox_violation_names_the_hook_file() -> None:
    hook = _hook("{{ cycler.__init__.__globals__ }}\n")

    with pytest.raises(TemplateSecurityError) as caught:
        _render(hook)

    assert caught.value.source == str(Path(_PATH))


def test_sandbox_violation_without_a_path_names_the_hook_id() -> None:
    hook = dataclasses.replace(_hook("{{ cycler.__init__.__globals__ }}\n"), source_path=None)

    with pytest.raises(TemplateSecurityError) as caught:
        _render(hook)

    assert caught.value.source == "guard-x"
