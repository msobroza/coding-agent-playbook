"""The images the sink guard compares: a NotebookEdit's notebook before and after (specs/prK-hook-pack.md §E.3).

``notebook_edit_images`` is pure: the current notebook JSON and the tool input
in, the joined code cells before and after out (``None``: no code added).
"""

from __future__ import annotations

import json
from typing import Any, Final

import pytest

from coding_agent_playbook.hook_runtime.handlers.feedback._sink_writes import notebook_edit_images

NOTEBOOK: Final = json.dumps(
    {
        "cells": [
            {"id": "a", "cell_type": "code", "source": "import numpy as np"},
            {"id": "m", "cell_type": "markdown", "source": "# Notes"},
            {"id": "b", "cell_type": "code", "source": "x = 1"},
        ]
    }
)


def _images(**raw: Any) -> tuple[str | None, str] | None:
    return notebook_edit_images({"new_source": "y = 2", **raw}, NOTEBOOK)


def test_replace_swaps_the_cell_source() -> None:
    assert _images(cell_id="b") == ("import numpy as np\nx = 1", "import numpy as np\ny = 2")


def test_insert_goes_after_the_named_cell_or_first() -> None:
    assert _images(cell_id="a", edit_mode="insert") == (
        "import numpy as np\nx = 1",
        "import numpy as np\ny = 2\nx = 1",
    )
    first = _images(edit_mode="insert", cell_type="code")
    assert first is not None
    assert first[1].startswith("y = 2\n")


@pytest.mark.parametrize(
    "raw",
    [
        {"cell_id": "b", "edit_mode": "delete"},
        {"cell_id": "b", "cell_type": "markdown"},
        {"cell_id": "m"},  # a markdown cell stays markdown
    ],
    ids=["delete", "markdown-type", "markdown-cell"],
)
def test_no_code_added_is_none(raw: dict[str, Any]) -> None:
    assert _images(**raw) is None


def test_markdown_cell_turned_into_code_counts() -> None:
    assert _images(cell_id="m", cell_type="code") == (
        "import numpy as np\nx = 1",
        "import numpy as np\ny = 2\nx = 1",
    )


@pytest.mark.parametrize("current", [None, "{not json"], ids=["absent", "unparseable"])
def test_without_a_notebook_the_new_source_is_judged_alone(current: str | None) -> None:
    assert notebook_edit_images({"new_source": "y = 2", "cell_id": "b"}, current) == ("", "y = 2")


def test_unknown_cell_is_judged_alone() -> None:
    assert _images(cell_id="zz") == ("", "y = 2")
