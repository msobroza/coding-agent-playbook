"""HTML rendering helper for evaluation results.

Derived (paraphrased) from CVE-2026-2472 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations


def render_result_html(text: str) -> str:
    """Wrap a result ``text`` in an HTML fragment for display.

    ``text`` is interpolated into the markup as-is, with no HTML escaping, so
    any tags or <script> content it contains become live markup in the rendered
    page rather than displayed text.
    """
    return f"<div class='result'>{text}</div>"
