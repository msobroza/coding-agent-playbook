"""The markdown-link gate's scan as it was at 8eb43dff, kept as the reference of its pins.

``validation._links.check_markdown_links`` lists files with
``catalog.skill_rules.iter_md_files`` and reads links with
``validation.link_check.extract_markdown_links``. Both were made cheaper, so
tests/validation/test_links_characterization.py and
tests/catalog/test_iter_md_files_characterization.py compare them with the
copies below. The function bodies are verbatim; the helpers they call
(``_mask_nonlink_regions``, ``classify_link``, ``layer_roots``) did not change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.validation import link_check
from coding_agent_playbook.validation._links import _LINK_CHECKED_SUBDIRS
from coding_agent_playbook.validation.findings import ValidationError
from coding_agent_playbook.validation.link_check import MarkdownLink, classify_link

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path

    from coding_agent_playbook.catalog.source import FileSystemArtifactSource
    from coding_agent_playbook.config.tables.links import LinksConfig


def reference_iter_md_files(root: Path, *, skip: Sequence[Path] = ()) -> Iterator[Path]:
    """``catalog.skill_rules.iter_md_files`` at 8eb43dff."""
    for path in sorted(root.rglob("*.md*")):
        if any(path.is_relative_to(skipped) for skipped in skip):
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if path.name.endswith(".md") or path.name.endswith(".md.j2"):
            yield path


def reference_extract_markdown_links(text: str) -> list[MarkdownLink]:
    """``validation.link_check.extract_markdown_links`` at 8eb43dff."""
    masked = link_check._mask_nonlink_regions(text)
    found: list[tuple[int, MarkdownLink]] = []
    for match in link_check._INLINE_LINK_RE.finditer(masked):
        found.append(
            (
                match.start(),
                MarkdownLink(
                    text=match.group(1),
                    target=link_check._clean_inline_target(match.group(2)),
                    line=link_check._line_of(masked, match.start()),
                ),
            )
        )
    without_inline = link_check._INLINE_LINK_RE.sub(
        lambda m: link_check._blank_keep_newlines(m.group(0)), masked
    )
    for match in link_check._REF_DEF_RE.finditer(without_inline):
        found.append(
            (
                match.start(),
                MarkdownLink(
                    text=match.group(1),
                    target=match.group(2),
                    line=link_check._line_of(without_inline, match.start()),
                ),
            )
        )
    for match in link_check._AUTOLINK_RE.finditer(without_inline):
        found.append(
            (
                match.start(),
                MarkdownLink(
                    text="",
                    target=match.group(1),
                    line=link_check._line_of(without_inline, match.start()),
                ),
            )
        )
    found.sort(key=lambda pair: pair[0])
    return [link for _, link in found]


def reference_check_markdown_links(
    source: FileSystemArtifactSource, links_config: LinksConfig
) -> list[ValidationError]:
    """``check_markdown_links`` at 8eb43dff for a filesystem source, from the copies above."""
    return [
        ValidationError(
            path=str(md),
            message=f"markdown link {link.target!r} (line {link.line}): {verdict}",
        )
        for subdir in _LINK_CHECKED_SUBDIRS
        for _label, root in source.layer_roots(subdir)
        for md in reference_iter_md_files(root)
        for link in reference_extract_markdown_links(md.read_text(encoding="utf-8"))
        if (
            verdict := classify_link(
                link.target,
                base_dir=md.parent,
                root_dir=root.parent,
                allowed_domains=links_config.allowed_domains,
            )
        )
        is not None
    ]
