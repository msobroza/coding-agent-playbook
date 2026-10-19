"""``docstring_example``: the opt-in strict docstring mode (prK §F.3.1, OQ-42)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.grading.parse import parse_module
from coding_agent_playbook.grading.static_metrics.docstring_example import DocstringExampleMetric
from coding_agent_playbook.grading.types import EvalContext


def _scores(source: str) -> dict[str, float]:
    ctx = EvalContext(module=parse_module(source, "a.py"), source=source, label="a.py")
    return {m.scope_key: m.value for m in DocstringExampleMetric().measure(ctx)}


def _def_with(docstring: str) -> str:
    body = "\n".join(f"    {line}" if line else "" for line in docstring.splitlines())
    return f'def load(path):\n    """{body.lstrip()}\n    """\n    return path\n'


@pytest.mark.parametrize(
    "docstring",
    [
        "Load it.\n\n>>> load('a')\n'a'",
        "Load it.\n\nExample:\n    load('a')",
        "Load it.\n\nExamples:\n    load('a')",
        "Load it.\n\nExamples\n--------\nload('a')",
        "Load it.\n\nUsage::\n\n    load('a')",
    ],
    ids=["doctest", "example", "examples", "numpy", "usage-literal"],
)
def test_example_forms_score_one(docstring: str) -> None:
    assert _scores(_def_with(docstring)) == {"a.py::load": 1.0}


def test_summary_only_scores_half() -> None:
    assert _scores(_def_with("Load the file at ``path``.")) == {"a.py::load": 0.5}


def test_missing_scores_zero() -> None:
    assert _scores("def load(path):\n    return path\n") == {"a.py::load": 0.0}


def test_private_defs_skipped() -> None:
    source = (
        "def _helper():\n    pass\n\n"
        "class Box:\n    def __init__(self):\n        pass\n\n"
        "    def open(self):\n        pass\n\n"
        "class _Hidden:\n    def run(self):\n        pass\n"
    )

    assert _scores(source) == {"a.py::Box.open": 0.0}
