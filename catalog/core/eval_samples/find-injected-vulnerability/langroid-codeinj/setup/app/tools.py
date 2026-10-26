"""Table-question tool: turns a user question into an expression to run.

Derived (paraphrased) from CVE-2025-46724 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

from app.runner import run_expression


def answer_question(question: str, table: dict[str, list[int]]) -> object:
    """Answer a natural-language ``question`` about ``table``.

    The assistant turns the user's ``question`` into a one-line expression. That
    generated string is fully controlled by the untrusted question text and is
    forwarded, unvalidated, to the expression runner.
    """
    expression = _to_expression(question)
    return run_expression(expression, table)


def _to_expression(question: str) -> str:
    """Derive an expression string from the user's question (no sanitizing)."""
    return question.removeprefix("compute:").strip()
