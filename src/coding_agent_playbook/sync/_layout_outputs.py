"""The layout adapter's sync step: rewrite layout path prefixes in the written files (D71).

Every adapter, the sync-level ``guard_config.json`` and the hook script copies write
their files first; then :func:`rewrite_layout_outputs` rewrites, in place, the default
path prefixes of every ``[layout]`` key that differs from D60 and every prefix the
enabled framework declares in ``[layout_aliases]`` (``config.layout.LayoutRewriter``).
Working on the written files, not on the artifacts, reaches every place a path can
land: rule and prompt bodies, skill files and their copied references, rule globs in
frontmatter and in skill-nudge's table, and the hook path tables of
``guard_config.json`` (D78(12)). It runs before the lockfile hashes the output, in
write mode and in both check modes alike, so ``sync --check`` stays clean.

Co-owned files (``.claude/settings.json``) and the files owned element-wise by scoped
lock entries hold user content and are never touched; a file that is not UTF-8 text
(an image, a binary script) is left as written.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from coding_agent_playbook.generated_output.output_io import (
    is_character_device,
    write_output_bytes,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable
    from pathlib import Path

    from coding_agent_playbook.config.layout import LayoutRewriter, RewriteCount


@dataclass(frozen=True)
class FileRewrite:
    """The rewrites applied to one written file.

    Example: ``FileRewrite(".claude/skills/x/SKILL.md", (RewriteCount("docs/specs", "specs", 2),))``.
    """

    path: str
    counts: tuple[RewriteCount, ...]


def rewrite_layout_outputs(
    written: Iterable[Path],
    out_root: Path,
    rewriter: LayoutRewriter,
    *,
    skip: Collection[str] = (),
) -> list[FileRewrite]:
    """Rewrite each written file in place; return what changed, one entry per file.

    ``written`` are the paths the render wrote under ``out_root`` (duplicates and
    links to one file are rewritten once); ``skip`` holds ``out_root``-relative
    POSIX paths never to touch (the co-owned and element-wise owned files). A
    falsy ``rewriter`` (the default layout, no aliases) touches nothing.

    Example::

        rewrites = rewrite_layout_outputs(recorder.written, repo, config.layout_rewriter(),
                                          skip={".claude/settings.json"})
    """
    if not rewriter:
        return []
    seen: set[Path] = set()
    rewrites: list[FileRewrite] = []
    for path in written:
        resolved = path.resolve()
        if resolved in seen or _relative(path, out_root) in skip:
            continue
        seen.add(resolved)
        counts = _rewrite_file(path, rewriter)
        if counts:
            rewrites.append(FileRewrite(_relative(path, out_root) or path.as_posix(), counts))
    return rewrites


def _rewrite_file(path: Path, rewriter: LayoutRewriter) -> tuple[RewriteCount, ...]:
    """Rewrite one regular UTF-8 file; ``()`` when it is not one or nothing matched."""
    if not path.is_file() or is_character_device(path):
        return ()
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return ()
    rewritten, counts = rewriter.rewrite(text)
    if counts:
        write_output_bytes(path, rewritten.encode("utf-8"))
    return counts


def _relative(path: Path, root: Path) -> str:
    """``path`` relative to ``root`` as spelled, POSIX; ``""`` outside it."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return ""
