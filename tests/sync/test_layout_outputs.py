"""``rewrite_layout_outputs``: the written files the layout adapter rewrites, and the ones it skips."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.config.layout import LayoutRewriter, RewriteCount
from coding_agent_playbook.sync._layout_outputs import FileRewrite, rewrite_layout_outputs

if TYPE_CHECKING:
    from pathlib import Path

_SPECS = LayoutRewriter.for_layout({"specs": "specs"})


def _write(root: Path, rel: str, data: bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_rewrites_each_written_text_file_once(tmp_path: Path) -> None:
    rule = _write(tmp_path, "AGENTS.md", b"see docs/specs/x.md\n")

    rewrites = rewrite_layout_outputs([rule, rule], tmp_path, _SPECS)

    assert rule.read_bytes() == b"see specs/x.md\n"
    assert rewrites == [FileRewrite("AGENTS.md", (RewriteCount("docs/specs", "specs", 1),))]


def test_skips_co_owned_files_and_binary_files(tmp_path: Path) -> None:
    settings = _write(tmp_path, ".claude/settings.json", b'{"x": "docs/specs/"}')
    image = _write(tmp_path, ".claude/skills/s/logo.bin", b"\xff\xfe docs/specs/")

    rewrites = rewrite_layout_outputs(
        [settings, image], tmp_path, _SPECS, skip={".claude/settings.json"}
    )

    assert rewrites == []
    assert settings.read_bytes() == b'{"x": "docs/specs/"}'
    assert image.read_bytes() == b"\xff\xfe docs/specs/"


def test_the_default_layout_touches_nothing(tmp_path: Path) -> None:
    rule = _write(tmp_path, "AGENTS.md", b"see docs/specs/x.md\n")

    assert rewrite_layout_outputs([rule], tmp_path, LayoutRewriter.for_layout({})) == []
    assert rule.read_bytes() == b"see docs/specs/x.md\n"
