"""The markdown-link gate pinned against its scan before the extraction fast path.

``extract_markdown_links`` now returns early for a text with nothing a link
pattern could match. The reference copies in ``tests._link_scan_reference`` are
the code before that change; these tests compare the two on every markdown
file of the catalog, on generated markdown, and end to end
(``check_markdown_links``: same findings, messages and order) on the shipped
layers and on a synthetic layer holding every kind of finding.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.catalog.roots import bundled_plugins
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.config.tables.links import LinksConfig
from coding_agent_playbook.validation import link_check
from coding_agent_playbook.validation._links import check_markdown_links
from tests._catalog import CATALOG_ROOT
from tests._link_scan_reference import (
    reference_check_markdown_links,
    reference_extract_markdown_links,
)

if TYPE_CHECKING:
    from pathlib import Path

#: An importable engine stand-in without a ``resources/`` tree, so only the
#: synthetic repo-local layer is scanned.
_LAYERLESS_ENGINE = "json"


def _catalog_markdown() -> list[Path]:
    return sorted(
        path
        for path in CATALOG_ROOT.rglob("*.md*")
        if path.is_file() and path.name.endswith((".md", ".md.j2"))
    )


@pytest.mark.catalog
def test_extract_matches_the_reference_on_every_catalog_markdown_file() -> None:
    files = _catalog_markdown()
    total = 0
    for md in files:
        text = md.read_text(encoding="utf-8")
        links = link_check.extract_markdown_links(text)
        assert links == reference_extract_markdown_links(text), md
        total += len(links)

    assert len(files) > 400, "the catalog walk found too few files to compare"
    assert total > 50, "too few catalog links found: the comparison would be vacuous"


#: Markdown pieces that matter to the link patterns and the masking, plus filler.
_TOKENS = (
    "[", "]", "(", ")", "<", ">", ":", "`", "``", "```", "~~~", "---", "\n", "\n", " ",
    "  ", "\t", "!", "^", "#", "a", "b c", "x.md", "../y.md", "https://h.example/p",
    "mailto:a@b.c", "{{ v }}", "](", "]:", "[^1]:", "<https://h.example/q>", "<b>",
)  # fmt: skip


def _random_markdown(rng: random.Random) -> str:
    return "".join(rng.choice(_TOKENS) for _ in range(rng.randint(0, 60)))


def test_extract_matches_the_reference_on_generated_markdown() -> None:
    rng = random.Random(4242)
    with_links = 0
    for _ in range(4000):
        text = _random_markdown(rng)
        links = link_check.extract_markdown_links(text)
        assert links == reference_extract_markdown_links(text), repr(text)
        with_links += bool(links)

    assert 400 < with_links < 3600, f"{with_links} of 4000 texts held links: retune _TOKENS"


# --- the fast-path predicate -----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["", "plain prose\n", "a <b> tag, list[int] and f(x)\n", "`code` and [brackets]\n"],
)
def test_text_without_link_syntax_cannot_hold_links(text: str) -> None:
    assert link_check._may_hold_links(text) is False


@pytest.mark.parametrize(
    "text", ["[t](x.md)", "[ref]: x.md", "<https://h.example/q>", "`[t](x.md)` masked later"]
)
def test_text_with_link_syntax_may_hold_links(text: str) -> None:
    assert link_check._may_hold_links(text) is True


# --- the whole gate --------------------------------------------------------------------


@pytest.mark.catalog
def test_gate_matches_the_reference_on_the_engine_and_every_bundled_plugin(
    tmp_path: Path,
) -> None:
    source = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=bundled_plugins())
    config = LinksConfig()

    assert check_markdown_links(source, tmp_path, config) == reference_check_markdown_links(
        source, config
    )


_RULE = """\
---
id: r
---
# R

Inline [ok](other.md), [missing](nope.md) and ![img](../../outside.png).
External [ext](https://evil.example.org/x), allowed <https://docs.python.org/3/>.
Scheme [mail](mailto:a@b.c), absolute [abs](/etc/passwd), empty [e]() and [a](#top).
Templated [t]({{ url }}) and `[code](in-a-span.md)`.

```python
x = [y](in-a-fence.md)
```

[ref]: missing-ref.md
[^1]: a footnote, not a link
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _broken_layer(repo: Path) -> Path:
    """A repo-local layer with every finding kind, in every link-checked kind."""
    layer = repo / "playbook"
    _write(layer / "rules" / "r.md", _RULE)
    _write(layer / "rules" / "other.md.j2", "Back to [r](r.md).\n")
    _write(layer / "rules" / ".hidden" / "x.md", "[gone](gone.md)\n")
    _write(layer / "rules" / "notes.md.bak", "[gone](gone.md)\n")
    _write(layer / "prompts" / "p.md", "Run [it](../rules/r.md) then [that](../nowhere.md).\n")
    _write(layer / "skills" / "s" / "SKILL.md", "See [ref](references/deep.md).\n")
    _write(layer / "skills" / "s" / "references" / "deep.md", "Up [x](../../../../../x.md)\n")
    _write(layer / "hooks" / "protect" / "h" / "HOOK.md", "Advice <ftp://files.example/f>.\n")
    return layer


def test_gate_pins_every_finding_kind_on_a_synthetic_layer(tmp_path: Path) -> None:
    layer = _broken_layer(tmp_path)
    source = FileSystemArtifactSource(repo_root=tmp_path, engine_package=_LAYERLESS_ENGINE)
    config = LinksConfig(allowed_domains=("python.org",))

    errors = check_markdown_links(source, tmp_path, config)

    rule, prompt = str(layer / "rules" / "r.md"), str(layer / "prompts" / "p.md")
    deep = str(layer / "skills" / "s" / "references" / "deep.md")
    hook = str(layer / "hooks" / "protect" / "h" / "HOOK.md")
    assert [(error.path, error.message) for error in errors] == [
        (rule, "markdown link 'nope.md' (line 6): target 'nope.md' does not exist in the artifact set"),
        (rule, f"markdown link '../../outside.png' (line 6): target '../../outside.png' escapes the artifact root {str(layer)!r}"),
        (rule, "markdown link 'https://evil.example.org/x' (line 7): external link to host 'evil.example.org' is not in [links] allowed_domains"),
        (rule, "markdown link 'mailto:a@b.c' (line 8): scheme 'mailto' is not self-contained (only relative paths ship)"),
        (rule, "markdown link '/etc/passwd' (line 8): absolute path '/etc/passwd' is layout-dependent, not self-contained"),
        (rule, "markdown link '' (line 8): empty link target"),
        (rule, "markdown link 'missing-ref.md' (line 15): target 'missing-ref.md' does not exist in the artifact set"),
        (prompt, "markdown link '../nowhere.md' (line 1): target '../nowhere.md' does not exist in the artifact set"),
        (deep, f"markdown link '../../../../../x.md' (line 1): target '../../../../../x.md' escapes the artifact root {str(layer)!r}"),
        (hook, "markdown link 'ftp://files.example/f' (line 1): scheme 'ftp' is not self-contained (only relative paths ship)"),
    ]  # fmt: skip
    assert errors == reference_check_markdown_links(source, config)
