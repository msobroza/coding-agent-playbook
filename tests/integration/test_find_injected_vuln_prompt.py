"""Focused unit checks on the find-injected-vulnerability prompt resource.

Parses the prompt frontmatter and body directly rather than going through
validate_samples; the prompt's samples are its task's, the samples under
``eval_samples/find-injected-vulnerability/`` (#302).
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.evals.task_registry import load_layer_samples
from tests._catalog import CORE_ROOT

pytestmark = pytest.mark.catalog

_PROMPT = CORE_ROOT / "prompts" / "find-injected-vulnerability.md.j2"

_EXPECTED_EVAL_SAMPLES = [
    "find-injected-vulnerability/modoboa-cmdi",
    "find-injected-vulnerability/ormar-sqli",
    "find-injected-vulnerability/changedetection-ssrf",
    "find-injected-vulnerability/langroid-codeinj",
    "find-injected-vulnerability/pytorch-deserial",
    "find-injected-vulnerability/changedetection-pathtraversal",
    "find-injected-vulnerability/authlib-sigbypass",
    "find-injected-vulnerability/graphiti-queryinj",
    "find-injected-vulnerability/pydash-massassign",
    "find-injected-vulnerability/aiplatform-xss",
]

# v2 framing bans (spec §5.2 / §7.1) — none may appear in the model-facing body.
_FRAMING_BANS = (
    "commit",
    "commits",
    "multiple",
    "multi-commit",
    "gradually",
    "over time",
    "across",
    "benign",
    "static analysis",
    "sast",
    "per-commit",
    "scanner",
    "individually",
)


def _prompt() -> Prompt:
    return Prompt.from_markdown(_PROMPT, source_package="coding_agent_playbook")


def test_prompt_is_non_ml_gated() -> None:
    # NON-ML-gated: no applies_if any_ml_stack (spec locked contract).
    # PromptFrontmatter.applies_if defaults to {} and __post_init__ coerces
    # None -> {}, so a prompt omitting applies_if: yields {} (never None).
    assert _prompt().frontmatter.applies_if == {}


def test_prompt_id_is_find_injected_vulnerability() -> None:
    assert _prompt().frontmatter.id == "find-injected-vulnerability"


def test_every_fixture_names_the_prompt() -> None:
    naming = [
        sample.id
        for sample in load_layer_samples(CORE_ROOT / "eval_samples", "coding_agent_playbook")
        if sample.prompt_id == _prompt().frontmatter.id
    ]
    assert sorted(naming) == sorted(_EXPECTED_EVAL_SAMPLES)


def test_prompt_body_has_no_commit_or_temporal_framing() -> None:
    body = _PROMPT.read_text(encoding="utf-8").lower()
    # Strip the frontmatter (fixture ids legitimately contain no framing words).
    body = body.split("---", 2)[-1]
    offenders = [w for w in _FRAMING_BANS if w in body]
    assert offenders == [], f"framing language leaked into prompt body: {offenders}"
