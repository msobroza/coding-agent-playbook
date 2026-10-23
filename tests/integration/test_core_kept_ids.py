"""The rule ids hooks and prompts depend on survive the prU split (D21, D16).

D21 keeps the old id on the piece of a split rule that keeps the old topic, so
the hooks' ``linked_rule`` and the prompts' ``includes_rules`` keep resolving;
D16 freezes those lists until after the pilot. Four ids retire; their absence is
asserted in ``test_core_final_state.py`` (F-02).
"""

from __future__ import annotations

from typing import Final

import pytest

from tests._catalog import KEPT_RULE_IDS, core_rules
from tests.hook_runtime.handlers.pack_repo import engine_hook, engine_hook_paths, engine_prompts

pytestmark = pytest.mark.catalog

#: Core hook id -> the rule it links (D16: frozen during the pilot).
EXPECTED_HOOK_LINKS: Final = {
    "docstring-nonregression": "python-docstrings",
    "error-handling-lint-feedback": "python-error-handling",
    "ml-unsafe-deserialization-guard": "ml-serialization-security",
    "pytest-conventions-feedback": "pytest",
    "typing-lint-feedback": "python-typing",
}
#: Core prompt id -> its ``includes_rules``, in authored order (D16: frozen during the pilot).
EXPECTED_PROMPT_INCLUDES: Final = {
    "characterize": ("pytest",),
    "generate-tests": ("python-typing", "pytest"),
    "make-testable": ("python-dependency-injection", "python-pure-core"),
    "refactor": (
        "python-typing",
        "python-error-handling",
        "python-dependency-injection",
        "python-pure-core",
    ),
    "review-architecture": ("python-dependency-injection",),
    "review": ("python-typing", "python-error-handling"),
    "security-review": ("ml-serialization-security", "python-error-handling"),
}


@pytest.mark.parametrize("rule_id", sorted(KEPT_RULE_IDS))
def test_kept_id_exists_in_its_skill(rule_id: str) -> None:
    rule = core_rules().get(rule_id)
    assert rule is not None, f"kept rule id {rule_id!r} is gone from core (D21)"
    skill = rule.frontmatter.skill
    assert skill == KEPT_RULE_IDS[rule_id], (
        f"kept rule {rule_id!r} is in skill {skill!r}; expected {KEPT_RULE_IDS[rule_id]!r}"
    )


def test_core_hooks_keep_their_linked_rules() -> None:
    hooks = (engine_hook(hook_id) for hook_id in engine_hook_paths())
    links = {
        h.frontmatter.id: h.frontmatter.linked_rule for h in hooks if h.frontmatter.linked_rule
    }
    assert links == EXPECTED_HOOK_LINKS


def test_core_prompts_keep_their_includes_rules() -> None:
    includes = {
        p.frontmatter.id: tuple(p.frontmatter.includes_rules)
        for p in engine_prompts()
        if p.frontmatter.includes_rules
    }
    assert includes == EXPECTED_PROMPT_INCLUDES


def test_kept_ids_are_exactly_the_ids_hooks_and_prompts_name() -> None:
    named = set(EXPECTED_HOOK_LINKS.values())
    named.update(rule_id for ids in EXPECTED_PROMPT_INCLUDES.values() for rule_id in ids)
    assert named == set(KEPT_RULE_IDS)
