"""Tests for ``coding_agent_playbook.links`` (PR L).

Covers markdown-link extraction (masking of frontmatter, fenced code blocks,
and inline code spans) and per-target self-containedness classification —
the deterministic engine behind the SPEC §12.6 link rule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.config.tables.links import LinksConfig
from coding_agent_playbook.links import MarkdownLink, classify_link, extract_markdown_links

if TYPE_CHECKING:
    from pathlib import Path


# --- extraction -----------------------------------------------------------


def test_extract_inline_link() -> None:
    links = extract_markdown_links("See [the spec](docs/spec.md) for details.\n")
    assert links == [MarkdownLink(text="the spec", target="docs/spec.md", line=1)]


def test_extract_image_link() -> None:
    links = extract_markdown_links("![diagram](assets/flow.png)\n")
    assert links == [MarkdownLink(text="diagram", target="assets/flow.png", line=1)]


def test_extract_reference_definition() -> None:
    links = extract_markdown_links("Intro [spec][1].\n\n[1]: https://example.com/spec\n")
    assert MarkdownLink(text="1", target="https://example.com/spec", line=3) in links


def test_extract_autolink() -> None:
    links = extract_markdown_links("Visit <https://example.com/x> now.\n")
    assert links == [MarkdownLink(text="", target="https://example.com/x", line=1)]


def test_extract_strips_optional_title() -> None:
    links = extract_markdown_links('[t](foo.md "A title")\n')
    assert links == [MarkdownLink(text="t", target="foo.md", line=1)]


def test_extract_angle_bracketed_target_keeps_spaces() -> None:
    links = extract_markdown_links("[t](<my file.md>)\n")
    assert links == [MarkdownLink(text="t", target="my file.md", line=1)]


def test_extract_reports_1_based_line_numbers() -> None:
    text = "one\ntwo\nthree [x](a.md) tail\n"
    links = extract_markdown_links(text)
    assert links == [MarkdownLink(text="x", target="a.md", line=3)]


def test_extract_multiple_links_on_one_line() -> None:
    links = extract_markdown_links("[a](one.md) and [b](two.md)\n")
    assert [link.target for link in links] == ["one.md", "two.md"]


def test_extract_masks_fenced_code_blocks() -> None:
    # Regression: the shipped typing rule contains PEP 695 generics inside a
    # ```python fence — `def first[T](items: list[T])` must not read as a link.
    text = "Generics:\n\n```python\ndef first[T](items: list[T]) -> T | None:\n    return items[0]\n```\n"
    assert extract_markdown_links(text) == []


def test_extract_masks_tilde_fences() -> None:
    text = "~~~\n[not a link](nope.md)\n~~~\n"
    assert extract_markdown_links(text) == []


def test_extract_masks_inline_code_spans() -> None:
    assert extract_markdown_links("Use `[T](items: list[T])` syntax.\n") == []


def test_extract_masks_leading_frontmatter() -> None:
    text = "---\ndescription: not [a link](ghost.md)\n---\nBody [real](real.md)\n"
    links = extract_markdown_links(text)
    assert links == [MarkdownLink(text="real", target="real.md", line=4)]


def test_extract_link_after_fence_keeps_line_number() -> None:
    text = "```\ncode\n```\n[x](a.md)\n"
    links = extract_markdown_links(text)
    assert links == [MarkdownLink(text="x", target="a.md", line=4)]


# --- classification -------------------------------------------------------


def _classify(target: str, tmp_path: Path, *, allowed: tuple[str, ...] = ()) -> str | None:
    base = tmp_path / "rules"
    base.mkdir(exist_ok=True)
    return classify_link(target, base_dir=base, root_dir=tmp_path, allowed_domains=allowed)


def test_fragment_only_is_self_contained(tmp_path: Path) -> None:
    assert _classify("#section", tmp_path) is None


def test_jinja_target_is_skipped(tmp_path: Path) -> None:
    assert _classify("{{ base_url }}/x.md", tmp_path) is None


def test_external_allowed_exact_host(tmp_path: Path) -> None:
    verdict = _classify("https://agentharnesses.io/spec", tmp_path, allowed=("agentharnesses.io",))
    assert verdict is None


def test_external_allowed_subdomain(tmp_path: Path) -> None:
    verdict = _classify(
        "https://docs.agentharnesses.io/x", tmp_path, allowed=("agentharnesses.io",)
    )
    assert verdict is None


def test_external_disallowed_host(tmp_path: Path) -> None:
    verdict = _classify("https://evil.example.com/x", tmp_path, allowed=("agentharnesses.io",))
    assert verdict is not None
    assert "evil.example.com" in verdict
    assert "allowed_domains" in verdict


def test_external_denied_by_default_empty_allowlist(tmp_path: Path) -> None:
    assert _classify("https://example.com/x", tmp_path) is not None


def test_host_suffix_is_not_subdomain(tmp_path: Path) -> None:
    # "notagentharnesses.io" must not sneak past an "agentharnesses.io" entry.
    verdict = _classify("https://notagentharnesses.io/x", tmp_path, allowed=("agentharnesses.io",))
    assert verdict is not None


def test_non_http_scheme_is_violation(tmp_path: Path) -> None:
    verdict = _classify("mailto:dev@example.com", tmp_path)
    assert verdict is not None
    assert "mailto" in verdict


def test_absolute_path_is_violation(tmp_path: Path) -> None:
    assert _classify("/etc/passwd", tmp_path) is not None


def test_empty_target_is_violation(tmp_path: Path) -> None:
    assert _classify("", tmp_path) is not None


def test_relative_existing_file_is_self_contained(tmp_path: Path) -> None:
    (tmp_path / "rules").mkdir(exist_ok=True)
    (tmp_path / "rules" / "other.md").write_text("x\n", encoding="utf-8")
    assert _classify("other.md", tmp_path) is None


def test_relative_missing_file_is_violation(tmp_path: Path) -> None:
    verdict = _classify("ghost.md", tmp_path)
    assert verdict is not None
    assert "ghost.md" in verdict


def test_relative_resolves_j2_suffixed_source(tmp_path: Path) -> None:
    # Rendering drops the .j2 suffix, so a link to `other.md` is satisfied by
    # a canonical `other.md.j2`.
    (tmp_path / "rules").mkdir(exist_ok=True)
    (tmp_path / "rules" / "other.md.j2").write_text("x\n", encoding="utf-8")
    assert _classify("other.md", tmp_path) is None


def test_relative_may_cross_kinds_within_root(tmp_path: Path) -> None:
    (tmp_path / "rules").mkdir(exist_ok=True)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "refactor.md").write_text("x\n", encoding="utf-8")
    assert _classify("../prompts/refactor.md", tmp_path) is None


def test_relative_escaping_root_is_violation(tmp_path: Path) -> None:
    root = tmp_path / "resources"
    (root / "rules").mkdir(parents=True)
    (tmp_path / "outside.md").write_text("x\n", encoding="utf-8")
    verdict = classify_link(
        "../../outside.md",
        base_dir=root / "rules",
        root_dir=root,
        allowed_domains=(),
    )
    assert verdict is not None
    assert "escapes" in verdict


def test_relative_fragment_and_query_are_stripped(tmp_path: Path) -> None:
    (tmp_path / "rules").mkdir(exist_ok=True)
    (tmp_path / "rules" / "other.md").write_text("x\n", encoding="utf-8")
    assert _classify("other.md#anchor", tmp_path) is None


def test_relative_percent_encoding_is_decoded(tmp_path: Path) -> None:
    (tmp_path / "rules").mkdir(exist_ok=True)
    (tmp_path / "rules" / "my file.md").write_text("x\n", encoding="utf-8")
    assert _classify("my%20file.md", tmp_path) is None


def test_no_base_dir_skips_relative_resolution() -> None:
    assert classify_link("anything.md", base_dir=None, root_dir=None, allowed_domains=()) is None


def test_no_base_dir_still_applies_external_policy() -> None:
    verdict = classify_link(
        "https://example.com/x", base_dir=None, root_dir=None, allowed_domains=()
    )
    assert verdict is not None


# --- LinksConfig ----------------------------------------------------------


def test_links_config_defaults_to_strict() -> None:
    assert LinksConfig().allowed_domains == ()
