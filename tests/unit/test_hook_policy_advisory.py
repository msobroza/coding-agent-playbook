"""The one-line guardrail of a hook and the Guardrails section (D6, specs/prS-skills-context.md 8.4.1).

``guardrail_summary`` prefers the authored ``summary``; without one it falls back
to the body's first sentence, cut at a word boundary to at most
``GUARDRAIL_SUMMARY_MAX_CHARS`` characters. ``guardrails_section`` is the
``## Guardrails`` section AGENTS.md and the Claude Code rules file share.
"""

from __future__ import annotations

from coding_agent_playbook.hook_policy import (
    GUARDRAIL_SUMMARY_MAX_CHARS,
    guardrail_line,
    guardrail_summary,
    guardrails_section,
)
from tests.hook_samples import GUARDRAILS_SECTION_HEAD


def test_guardrail_summary_prefers_the_summary() -> None:
    assert guardrail_summary("Ask first.", "Never act alone. Then report.") == "Ask first."


def test_guardrail_summary_falls_back_to_the_first_sentence() -> None:
    assert guardrail_summary("", "Ask first. Then act.") == "Ask first."


def test_fallback_joins_the_lines_of_a_wrapped_sentence() -> None:
    body = "\nBefore committing a notebook,\nclear its outputs!  Outputs embed data.\n"

    assert guardrail_summary("", body) == "Before committing a notebook, clear its outputs!"


def test_fallback_ignores_a_full_stop_inside_a_code_span() -> None:
    body = "Run `ruff check .` and `ruff format --check .` first. Then report."

    assert guardrail_summary("", body) == "Run `ruff check .` and `ruff format --check .` first."


def test_fallback_keeps_a_body_without_a_full_stop_whole() -> None:
    assert guardrail_summary("", "Ask the user first") == "Ask the user first"


def test_fallback_skips_a_leading_heading() -> None:
    # Regression: the heading's text and its "##" used to open the guardrail line.
    assert guardrail_summary("", "## Heading\n\nDo X. Then Y.") == "Do X."


def test_fallback_drops_list_item_markers() -> None:
    # Regression: the bullet's "-" used to lead the line, after the "- `id`:" bullet.
    assert guardrail_summary("", "- Do X.\n- Do Y.") == "Do X."


def test_fallback_drops_quote_and_numbered_markers() -> None:
    body = "> 1. Ask the user\n> first. Then act."

    assert guardrail_summary("", body) == "Ask the user first."


def test_fallback_keeps_a_dash_inside_the_sentence() -> None:
    body = "Never pass --no-verify - ask first."

    assert guardrail_summary("", body) == body


def test_fallback_of_a_headings_only_body_keeps_the_heading_text() -> None:
    # Blank lines around the heading are no prose: the line keeps the heading's text.
    assert guardrail_summary("", "\n# Ask first\n\n") == "Ask first"


def test_guardrail_summary_cuts_a_long_sentence_at_a_word_boundary() -> None:
    body = " ".join(["guardrail"] * 20) + ". Second sentence."

    summary = guardrail_summary("", body)

    # Twelve 10-character "guardrail " fill the 120: the 12th word ends at 119, then "…".
    assert summary == " ".join(["guardrail"] * 12) + "…"
    assert len(summary) == GUARDRAIL_SUMMARY_MAX_CHARS == 120


def test_cut_drops_trailing_punctuation_before_the_ellipsis() -> None:
    body = "a" * 100 + ", " + "b" * 40 + "."

    assert guardrail_summary("", body) == "a" * 100 + "…"


def test_cut_never_leaves_a_code_span_open() -> None:
    body = "x" * 100 + " `rm -rf build caches` is fine."

    assert guardrail_summary("", body) == "x" * 100 + "…"


def test_cut_of_one_long_word_is_hard() -> None:
    assert guardrail_summary("", "y" * 200) == "y" * 119 + "…"


def test_cut_is_hard_when_closing_the_code_span_leaves_nothing() -> None:
    # Regression: dropping the open span from "`aaa…" left the line as just "…".
    summary = guardrail_summary("", "`" + "a" * 130)

    assert summary == "`" + "a" * 118 + "…"
    assert len(summary) == GUARDRAIL_SUMMARY_MAX_CHARS


def test_hard_cut_after_an_open_span_drops_the_trailing_space() -> None:
    # The space sits at index 118, the last character a hard cut keeps.
    body = "`" + "a" * 117 + " " + "b" * 20

    assert guardrail_summary("", body) == "`" + "a" * 117 + "…"


def test_guardrail_line_names_the_hook_id_in_code() -> None:
    assert guardrail_line("x", "Ask first.") == "- `x`: Ask first."


def test_guardrails_section_sorts_lines_by_hook_id() -> None:
    lines = [("guard-b", "- `guard-b`: B."), ("guard-a", "- `guard-a`: A.")]

    assert guardrails_section(lines) == (
        GUARDRAILS_SECTION_HEAD + "- `guard-a`: A.\n- `guard-b`: B.\n"
    )
