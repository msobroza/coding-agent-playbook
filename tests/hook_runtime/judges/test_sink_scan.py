"""The unsafe-sink visitor shared by the deserialization guard and its twins (specs/prK-hook-pack.md §E.3).

``new_sink_calls`` is pure: text in, the multiset ``post - pre`` of sink calls
out. Callees resolve through import aliases; a row matches on the callee
pattern and the call's literal keyword arguments. When either image fails to
parse, both are scanned with the regex fallback so the two counts stay comparable.
"""

from __future__ import annotations

from typing import Final

import pytest

from coding_agent_playbook.hook_runtime.judges.notebook_cells import notebook_code
from coding_agent_playbook.hook_runtime.judges.sink_scan import (
    SinkTable,
    new_sink_calls,
)

TABLE: Final = SinkTable.from_config(
    {
        "block": [
            {"call": "pickle.loads"},
            {"call": "yaml.load", "unless": {"Loader": ["SafeLoader", "CSafeLoader"]}},
            {"call": "torch.load", "kwarg": {"weights_only": False}},
            {"call": "numpy.load", "kwarg": {"allow_pickle": True}},
            {"call": "*", "kwarg": {"trust_remote_code": True}},
        ],
        "warn": [
            {"call": "torch.load", "missing": ["weights_only"]},
            {"call": "*.from_pretrained", "missing": ["revision"]},
            {"call": "eval"},
            {"call": "subprocess.*", "kwarg": {"shell": True}},
        ],
    }
)


def _calls(pre: str | None, post: str) -> list[tuple[str, str, int]]:
    return [(hit.callee, hit.kind, hit.line) for hit in new_sink_calls(pre, post, TABLE)]


def test_alias_resolution_and_only_new_calls_count() -> None:
    pre = "import pickle as pk\nx = pk.loads(a)\n"
    post = "import pickle as pk\nx = pk.loads(a)\ny = pk.loads(b)\n"

    assert _calls(pre, post) == [("pickle.loads", "block", 3)]


def test_from_import_and_conventional_np_alias() -> None:
    post = "from pickle import loads as l\nl(b)\nnp.load(f, allow_pickle=True)\n"

    assert _calls(None, post) == [("pickle.loads", "block", 2), ("numpy.load", "block", 3)]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("torch.load(p, weights_only=True)", []),
        ("torch.load(p, weights_only=False)", [("torch.load", "block", 2)]),
        ("torch.load(p)", [("torch.load", "warn", 2)]),
        ("yaml.load(f, Loader=yaml.SafeLoader)", []),
        ("yaml.load(f)", [("yaml.load", "block", 2)]),
        ("AutoModel.from_pretrained(n, revision=r)", []),
        ("AutoModel.from_pretrained(n)", [("AutoModel.from_pretrained", "warn", 2)]),
        (
            "AutoModel.from_pretrained(n, trust_remote_code=True)",
            [("AutoModel.from_pretrained", "block", 2)],
        ),
        ("subprocess.run(c, shell=True)", [("subprocess.run", "warn", 2)]),
        ("model.eval()", []),
        ("eval(x)", [("eval", "warn", 2)]),
    ],
)
def test_rows_match_on_literal_kwargs(line: str, expected: list[tuple[str, str, int]]) -> None:
    assert _calls(
        "import torch, yaml, subprocess\n", f"import torch, yaml, subprocess\n{line}\n"
    ) == (expected)


def test_unparseable_post_image_falls_back_to_regex() -> None:
    post = "import pickle\ndef broken(:\n    return pickle.loads(data)\n"

    assert _calls("import pickle\n", post) == [("pickle.loads", "block", 3)]


def test_regex_fallback_counts_new_against_old() -> None:
    pre = "import pickle\nx = pickle.loads(a)\n"
    post = "import pickle\nx = pickle.loads(a)\nif (:\n"

    assert _calls(pre, post) == []


def test_notebook_code_joins_code_cells_and_comments_magics() -> None:
    doc = (
        '{"cells": [{"cell_type": "code", "source": ["%matplotlib inline\\n", "import numpy as np"]},'
        '{"cell_type": "markdown", "source": "pickle.loads(x)"},'
        '{"cell_type": "code", "source": "np.load(f, allow_pickle=True)"}]}'
    )

    code = notebook_code(doc)

    assert code is not None
    assert _calls(None, code) == [("numpy.load", "block", 3)]


def test_malformed_row_names_the_row() -> None:
    with pytest.raises(ValueError, match=r"block\[0\].*'call'"):
        SinkTable.from_config({"block": [{"kwarg": {}}]})
