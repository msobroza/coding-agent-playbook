"""Evaluation page builder: renders a stored result into HTML.

Derived (paraphrased) from CVE-2026-2472 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

from app.render import render_result_html


def build_evaluation_page(result: dict[str, str]) -> str:
    """Build the HTML page that shows an evaluation ``result``.

    ``result['output']`` is model / agent output derived from attacker-supplied
    prompt data and stored earlier; here it flows straight into the HTML
    renderer, so anything it contains is emitted into the page unescaped.
    """
    output = result["output"]
    return render_result_html(output)
