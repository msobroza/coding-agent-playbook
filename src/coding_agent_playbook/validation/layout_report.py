"""``playbook validate``'s layout report: every rewrite the layout adapter makes, per file (D71).

``playbook sync`` rewrites the default layout prefixes (and the framework's aliases)
in the files it writes (``sync._layout_outputs``). Validate reports the same
rewrites on the files they come from: every file of the rules, prompts, skills and
hooks directories of each layer (the engine, the enabled framework and overlays,
repo-local ``playbook/``), one line per file and prefix::

    layout: coding_agent_playbook.plugins.mattpocock_skills/rules/x.md: docs/agents -> notes/agents (3)

Nothing is printed for the default layout without aliases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.catalog.layers import REPO_LOCAL_SOURCE
from coding_agent_playbook.catalog.source import FileSystemArtifactSource

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from coding_agent_playbook.catalog.source import ArtifactSource
    from coding_agent_playbook.config.layout import LayoutRewriter, RewriteCount

#: The layer directories whose files sync writes out (``eval_samples`` stay in the engine).
_SYNCED_SUBDIRS: Final = ("rules", "prompts", "skills", "hooks")
_REPO_LOCAL_ROOT: Final = "playbook"


@dataclass(frozen=True)
class SourceRewrite:
    """One prefix rewritten in one source file.

    Example: ``SourceRewrite("<pkg>/rules/x.md", RewriteCount("docs/specs", "specs", 2))``.
    """

    file: str
    count: RewriteCount

    def line(self) -> str:
        """``layout: <file>: <from> -> <to> (<count>)``, as validate prints it.

        Example: ``"layout: p/rules/x.md: docs/specs -> specs (2)"``.
        """
        return (
            f"layout: {self.file}: {self.count.source} -> {self.count.target} ({self.count.count})"
        )


def layout_source_rewrites(
    artifact_source: ArtifactSource, rewriter: LayoutRewriter
) -> list[SourceRewrite]:
    """Every rewrite ``rewriter`` makes in the synced files of ``artifact_source``'s layers.

    A source without an on-disk layout, or a falsy ``rewriter``, reports nothing.

    Example::

        lines = [r.line() for r in layout_source_rewrites(ctx.artifact_source,
                                                          ctx.config.layout_rewriter())]
    """
    if not rewriter or not isinstance(artifact_source, FileSystemArtifactSource):
        return []
    return [
        SourceRewrite(shown, count)
        for shown, path in _synced_files(artifact_source)
        for count in _rewrites_in(path, rewriter)
    ]


def _synced_files(artifact_source: FileSystemArtifactSource) -> Iterator[tuple[str, Path]]:
    """``(shown name, path)`` of each file under a layer's synced directories."""
    for subdir in _SYNCED_SUBDIRS:
        for label, root in artifact_source.layer_roots(subdir):
            prefix = _REPO_LOCAL_ROOT if label == REPO_LOCAL_SOURCE else label
            for path in sorted(root.rglob("*")):
                relative = path.relative_to(root)
                if path.is_file() and not any(part.startswith(".") for part in relative.parts):
                    yield f"{prefix}/{subdir}/{relative.as_posix()}", path


def _rewrites_in(path: Path, rewriter: LayoutRewriter) -> tuple[RewriteCount, ...]:
    """The rewrites in one UTF-8 file; ``()`` for a binary or unreadable one."""
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return ()
    return rewriter.rewrite(text)[1]
