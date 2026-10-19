"""Tests for agent_harness.hook_sidecars — both halves of the hook sidecar (AH-2, #143).

``emit_hook_sidecars`` writes ``.playbook/hooks/<id>/HOOK.md`` and its manifest
entry; ``read_hook_sidecar`` turns that entry back into the canonical ``Hook``.
"""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness.hook_sidecars import emit_hook_sidecars, read_hook_sidecar
from tests.hook_samples import resolved_from_disk

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.agent_harness.manifest import ManifestEntry


def test_sidecar_written_by_the_adapter_reads_back_as_the_same_hook(tmp_path: Path) -> None:
    resolved = resolved_from_disk(
        tmp_path / "src", body="Advice {{ x }}.\n", templated=True, summary="Never edit x."
    )
    source = resolved.definition
    assert source is not None
    repo = tmp_path / "harness"
    entries: list[ManifestEntry] = []
    emit_hook_sidecars([resolved], repo, entries)
    [entry] = entries
    script = repo / ".playbook" / "hooks" / "guard-x" / "scripts" / "check.sh"
    script.chmod(0o644)  # a transport (zip, Windows checkout) that drops exec bits

    hook = read_hook_sidecar(repo / entry.path, entry, source_package="<imported>")

    assert hook.frontmatter == source.frontmatter
    assert hook.frontmatter.summary == "Never edit x."  # #57's one-line guardrail survives
    assert (hook.template_body, hook.body, hook.is_templated) == (
        "Advice {{ x }}.\n",
        "Advice {{ x }}.\n",
        True,
    )
    assert hook.source_package == "<imported>"
    assert hook.scripts_dir == script.parent
    if os.name == "posix":
        assert script.stat().st_mode & stat.S_IXUSR
        assert not (script.parent / "lib" / "data.txt").stat().st_mode & stat.S_IXUSR
