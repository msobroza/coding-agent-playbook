"""Markdown-link extraction + self-containedness classification (SPEC §12.6, PR L).

A canonical artifact is *self-contained* when every markdown link in its body
stays inside the shipped bundle: relative targets must resolve to a file under
the artifact's source layer, and ``http(s)://`` targets are only tolerated when
their host matches the ``[links] allowed_domains`` allowlist. The check is
fully deterministic — stdlib only, no network.

Usage::

    links = extract_markdown_links(body)
    for link in links:
        verdict = classify_link(
            link.target, base_dir=md.parent, root_dir=resources_root,
            allowed_domains=config.allowed_domains,
        )
        # verdict is None (self-contained) or a human-readable violation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class MarkdownLink:
    """One extracted link: display text, raw target, 1-based source line."""

    text: str
    target: str
    line: int


@dataclass(frozen=True)
class LinksConfig:
    """Parsed ``[links]`` table of ``.coding-agent-playbook.toml``.

    ``allowed_domains`` is the external-link allowlist (lowercase hostnames;
    subdomains of an entry are allowed too). Empty — the default — means fully
    strict: no external links at all.
    """

    allowed_domains: tuple[str, ...] = ()


# Inline links and images: `[text](target)` / `![alt](target)`.
_INLINE_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(([^)]*)\)")
# Reference definitions: `[label]: target` — footnotes (`[^1]:`) excluded,
# their "target" is prose.
_REF_DEF_RE = re.compile(r"^[ ]{0,3}\[([^\]^][^\]]*)\]:[ \t]*(\S+)", re.MULTILINE)
# Autolinks: `<scheme:rest>`.
_AUTOLINK_RE = re.compile(r"<([A-Za-z][A-Za-z0-9+.-]*:[^<>\s]+)>")
# Inline code spans, possibly multi-backtick and multi-line.
_CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.DOTALL)


def extract_markdown_links(text: str) -> list[MarkdownLink]:
    """Extract every markdown link from ``text``, in source order.

    Leading YAML frontmatter, fenced code blocks (``` or ~~~), and inline code
    spans are masked first — code examples like ``def first[T](items: list[T])``
    must never read as links. Line numbers refer to the original ``text``.
    """
    masked = _mask_nonlink_regions(text)
    found: list[tuple[int, MarkdownLink]] = []
    for match in _INLINE_LINK_RE.finditer(masked):
        found.append(
            (
                match.start(),
                MarkdownLink(
                    text=match.group(1),
                    target=_clean_inline_target(match.group(2)),
                    line=_line_of(masked, match.start()),
                ),
            )
        )
    # Blank inline matches before the autolink pass so `[t](<https://x>)`
    # is not reported twice.
    without_inline = _INLINE_LINK_RE.sub(lambda m: _blank_keep_newlines(m.group(0)), masked)
    for match in _REF_DEF_RE.finditer(without_inline):
        found.append(
            (
                match.start(),
                MarkdownLink(
                    text=match.group(1),
                    target=match.group(2),
                    line=_line_of(without_inline, match.start()),
                ),
            )
        )
    for match in _AUTOLINK_RE.finditer(without_inline):
        found.append(
            (
                match.start(),
                MarkdownLink(
                    text="",
                    target=match.group(1),
                    line=_line_of(without_inline, match.start()),
                ),
            )
        )
    found.sort(key=lambda pair: pair[0])
    return [link for _, link in found]


def classify_link(
    target: str,
    *,
    base_dir: Path | None,
    root_dir: Path | None,
    allowed_domains: tuple[str, ...],
) -> str | None:
    """Return a violation message for ``target``, or ``None`` if self-contained.

    ``base_dir`` is the directory the containing artifact lives in;
    ``root_dir`` is the artifact root the target must stay inside (the layer
    root: ``catalog/core/`` or ``catalog/plugins/<name>/`` for a bundled layer,
    an overlay package's ``resources/``, or the repo-local ``playbook/``). Pass
    ``base_dir=None`` for artifacts with no on-disk location (non-filesystem
    sources): relative targets are then skipped, but the external-link policy
    still applies.
    """
    if "{{" in target or "{%" in target:
        return None  # Jinja-generated target — not statically checkable.
    stripped = target.strip()
    if not stripped:
        return "empty link target"
    if stripped.startswith("#"):
        return None  # Self-referential anchor.
    split = urlsplit(stripped)
    if split.scheme in ("http", "https"):
        host = (split.hostname or "").lower()
        for domain in allowed_domains:
            allowed = domain.lower()
            if host == allowed or host.endswith("." + allowed):
                return None
        return f"external link to host {host!r} is not in [links] allowed_domains"
    if split.scheme:
        return f"scheme {split.scheme!r} is not self-contained (only relative paths ship)"
    path = unquote(split.path)
    if not path:
        return None  # Query-only target — nothing to resolve.
    if path.startswith("/"):
        return f"absolute path {path!r} is layout-dependent, not self-contained"
    if base_dir is None or root_dir is None:
        return None  # No on-disk anchor to resolve against.
    resolved = (base_dir / path).resolve()
    root = root_dir.resolve()
    if not resolved.is_relative_to(root):
        return f"target {path!r} escapes the artifact root {str(root_dir)!r}"
    # Rendering drops the `.j2` suffix, so `other.md` is satisfied by a
    # canonical `other.md.j2`.
    if resolved.exists() or resolved.with_name(resolved.name + ".j2").exists():
        return None
    return f"target {path!r} does not exist in the artifact set"


def _mask_nonlink_regions(text: str) -> str:
    """Blank frontmatter, fenced code blocks, and inline code spans.

    Line count is preserved so match offsets in the masked text map to the
    original line numbers.
    """
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                for masked_index in range(index + 1):
                    lines[masked_index] = ""
                break
    in_fence = False
    fence_marker = ""
    for index, line in enumerate(lines):
        head = line.lstrip()
        if not in_fence and (head.startswith("```") or head.startswith("~~~")):
            in_fence = True
            fence_marker = head[:3]
            lines[index] = ""
        elif in_fence:
            closing = head.startswith(fence_marker)
            lines[index] = ""
            if closing:
                in_fence = False
    masked = "\n".join(lines)
    return _CODE_SPAN_RE.sub(lambda m: _blank_keep_newlines(m.group(0)), masked)


def _blank_keep_newlines(fragment: str) -> str:
    """Replace ``fragment`` with same-shape whitespace (newlines preserved)."""
    return "".join("\n" if char == "\n" else " " for char in fragment)


def _clean_inline_target(raw: str) -> str:
    """Normalize an inline-link target: drop the optional title, unwrap ``<>``."""
    raw = raw.strip()
    if raw.startswith("<"):
        end = raw.find(">")
        if end != -1:
            return raw[1:end]
    parts = raw.split()
    return parts[0] if parts else ""


def _line_of(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1
