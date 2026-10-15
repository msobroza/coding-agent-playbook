"""Focused unit checks on the find-injected-vulnerability prompt resource.

Runs BEFORE all ten fixtures exist, so it parses the prompt frontmatter and
body directly rather than going through validate_tasks (which needs every
eval_tasks: entry to resolve on-disk — that whole-suite green lands in C4).
"""

from __future__ import annotations

from coding_agent_playbook.types import Prompt
from tests._content import CORE_ROOT

_PROMPT = CORE_ROOT / "prompts" / "find-injected-vulnerability.md.j2"

_EXPECTED_EVAL_TASKS = [
    "find-injected-vuln-modoboa-cmdi",
    "find-injected-vuln-ormar-sqli",
    "find-injected-vuln-changedetection-ssrf",
    "find-injected-vuln-langroid-codeinj",
    "find-injected-vuln-pytorch-deserial",
    "find-injected-vuln-changedetection-pathtraversal",
    "find-injected-vuln-authlib-sigbypass",
    "find-injected-vuln-graphiti-queryinj",
    "find-injected-vuln-pydash-massassign",
    "find-injected-vuln-aiplatform-xss",
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


def test_prompt_lists_every_fixture_id() -> None:
    assert _prompt().frontmatter.eval_tasks == _EXPECTED_EVAL_TASKS


def test_prompt_body_has_no_commit_or_temporal_framing() -> None:
    body = _PROMPT.read_text(encoding="utf-8").lower()
    # Strip the frontmatter (fixture ids legitimately contain no framing words).
    body = body.split("---", 2)[-1]
    offenders = [w for w in _FRAMING_BANS if w in body]
    assert offenders == [], f"framing language leaked into prompt body: {offenders}"
