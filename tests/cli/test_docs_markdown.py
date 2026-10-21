"""The stdlib half of ``playbook docs-check``: link forms and fence shapes (D69).

Each row is one Markdown document written as ``README.md`` beside an existing
``docs/guide.md`` and ``docs/my file.md``; the row states the findings
:func:`markdown_findings` must report (none means the link or block is fine or
is not checked).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands.twins._docs_markdown import markdown_findings

if TYPE_CHECKING:
    from pathlib import Path


def _broken(line: int, target: str) -> str:
    return f"README.md:{line}: broken relative link {target!r} (no such file)"


@pytest.fixture
def readme(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "docs" / "my file.md").write_text("# Mine\n", encoding="utf-8")
    return tmp_path / "README.md"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("![logo](img/gone.png)\n", [_broken(1, "img/gone.png")], id="image"),
        pytest.param("[ref]: docs/gone.md\n", [_broken(1, "docs/gone.md")], id="reference"),
        pytest.param("[a](<docs/gone.md>)\n", [_broken(1, "docs/gone.md")], id="angle"),
        pytest.param('[a](gone.md "Title")\n', [_broken(1, "gone.md")], id="title"),
        pytest.param('[a](docs/guide.md "Title")\n', [], id="title-ok"),
        pytest.param("[a](https://example.com/gone.md)\n", [], id="https"),
        pytest.param("[a](mailto:me@example.com)\n", [], id="mailto"),
        pytest.param("[a](#section)\n", [], id="anchor-only"),
        pytest.param("[a](/site/absolute.md)\n", [], id="site-absolute"),
        pytest.param("[a]({{base_url}}/gone.md)\n", [], id="template"),
        pytest.param("[a](docs/my%20file.md)\n", [], id="percent-encoded"),
        pytest.param("[a](docs/guide.md?plain=1)\n", [], id="query"),
        pytest.param("[a](docs)\n", [], id="directory"),
        pytest.param("[a](docs/guide.md#top)\n", [], id="fragment"),
    ],
)
def test_link_forms(readme: Path, text: str, expected: list[str]) -> None:
    readme.write_text(text, encoding="utf-8")

    assert markdown_findings(readme, "README.md") == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("~~~\n[a](gone.md)\n~~~\n", [], id="tilde-fence-hides-links"),
        pytest.param(
            "~~~python\ndef broken(:\n~~~\n",
            ["README.md:2: Python code block does not parse: invalid syntax"],
            id="tilde-python-block-parsed",
        ),
        pytest.param(
            "````\n```\n[a](gone.md)\n````\n[b](gone.md)\n",
            [_broken(5, "gone.md")],
            id="shorter-fence-does-not-close",
        ),
        pytest.param(
            "```\nx\n`````\n[b](gone.md)\n",
            [_broken(4, "gone.md")],
            id="longer-closing-fence-closes",
        ),
        pytest.param("text\n```\n[a](gone.md)\n", [], id="unclosed-fence-runs-to-end"),
    ],
)
def test_fence_shapes(readme: Path, text: str, expected: list[str]) -> None:
    readme.write_text(text, encoding="utf-8")

    assert markdown_findings(readme, "README.md") == expected
