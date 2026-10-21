"""Expression runner for the table-question agent.

Derived (paraphrased) from CVE-2025-46724 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations


def run_expression(expression: str, table: dict[str, list[int]]) -> object:
    """Evaluate a pandas-style ``expression`` against ``table`` and return it.

    ``expression`` is handed to eval(). Passing an empty globals dict and only
    ``table`` as a local does not contain the evaluation: builtins remain
    reachable, so any Python the string encodes runs with full privileges.
    """
    return eval(expression, {}, {"table": table})
