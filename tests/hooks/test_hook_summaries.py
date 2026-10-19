"""Every core hook with a body authors its one-line guardrail (D6, specs/prS-skills-context.md 8.4.1).

The ``summary`` is the hook's line in ``AGENTS.md``'s Guardrails section. The
first-sentence fallback exists for overlay and repo-local hooks; core writes its
own, because a cut sentence loses its point (``stop-ci-parity-gate``'s would drop
the checks D17 says the line names). Read from the checkout, like every catalog gate.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.artifacts.hook import Hook
from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE
from tests._catalog import core_markdown_sources

pytestmark = pytest.mark.catalog

_HOOK_MARKERS = ("HOOK.md", "HOOK.md.j2")


def _core_hooks() -> dict[str, Hook]:
    paths = [path for path in core_markdown_sources("hooks") if path.name in _HOOK_MARKERS]
    hooks = (Hook.from_markdown(path, ENGINE_PACKAGE) for path in paths)
    return {hook.frontmatter.id: hook for hook in hooks}


def test_every_core_hook_with_a_body_declares_a_summary() -> None:
    with_body = [hook for hook in _core_hooks().values() if hook.template_body.strip()]
    assert with_body, "core ships no hook with a body"

    missing = sorted(hook.frontmatter.id for hook in with_body if not hook.frontmatter.summary)

    assert not missing, f"core hooks with a body but no summary: {missing}"


def test_a_core_hook_without_a_body_declares_no_summary() -> None:
    """A summary with no body would name a guardrail that has no full text in the skill."""
    bodiless = [hook for hook in _core_hooks().values() if not hook.template_body.strip()]

    stray = sorted(hook.frontmatter.id for hook in bodiless if hook.frontmatter.summary)

    assert not stray, f"core hooks without a body that declare a summary: {stray}"


def test_stop_ci_parity_gate_summary_names_the_checks() -> None:
    summary = _core_hooks()["stop-ci-parity-gate"].frontmatter.summary

    for check in ("`ruff check .`", "`ruff format --check .`", "type checker", "tests"):
        assert check in summary, f"stop-ci-parity-gate's summary lacks {check!r}: {summary!r}"
