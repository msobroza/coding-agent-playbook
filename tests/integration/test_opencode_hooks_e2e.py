"""A real OpenCode honours the shim's ``tool.execute.before`` throw (specs/prK-lifecycle-hooks.md §C.3.4).

Open issue #52837 claims a throw from ``tool.execute.before`` is swallowed,
while the v1.19.0 source shows it becoming the tool's error result. Only a
real OpenCode can settle that, so this test is opt-in (``opencode`` on PATH
and ``PLAYBOOK_E2E_OPENCODE=1``, which also needs a configured model) and
never runs in CI; CI pins only the shim's own throw, under node.

The repo gets the rendered shim and a pin naming a fake dispatcher that
denies every ``pre_tool_use`` with exit 10. The agent is asked to create a
marker file through bash: the dispatcher must have been called, and the
marker must not exist.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_registrations import OPENCODE_SHIM_PATH, render_opencode_shim

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hook_registrations import OpenCodeRegEntry

_ENABLED = bool(shutil.which("opencode")) and os.environ.get("PLAYBOOK_E2E_OPENCODE") == "1"
_RUN_TIMEOUT_S = 600
_GIT_TIMEOUT_S = 30
_MARKER = "e2e-marker.txt"
_REASON = "playbook e2e: bash is blocked"
_FAKE_DISPATCHER = """\
#!/bin/sh
echo "$5" >> '{log}'
cat > /dev/null
[ "$5" = pre_tool_use ] || exit 0
echo '{{"v":1,"decision":"deny","reason":"{reason}","context":[],"notice":""}}'
exit 10
"""


@pytest.mark.skipif(
    not _ENABLED,
    reason="real opencode e2e: needs the CLI on PATH and PLAYBOOK_E2E_OPENCODE=1",
)
def test_real_opencode_before_hook_throw_blocks_tool(tmp_path: Path) -> None:  # pragma: no cover
    repo = tmp_path / "repo"
    repo.mkdir()
    # Only GIT_* is scrubbed: OpenCode needs the user's own XDG config for its model.
    git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q"], cwd=repo, env=git_env, check=True, timeout=_GIT_TIMEOUT_S)
    shim = repo / OPENCODE_SHIM_PATH
    shim.parent.mkdir(parents=True)
    reg: dict[str, OpenCodeRegEntry] = {
        "session_start": {"timeout_ms": 10_000},
        "pre_tool_use": {"timeout_ms": 10_000, "tools": ["bash"]},
    }
    shim.write_text(render_opencode_shim(reg), encoding="utf-8")
    log = tmp_path / "dispatch.log"
    fake = tmp_path / "fake-dispatch"
    fake.write_text(_FAKE_DISPATCHER.format(log=log, reason=_REASON), encoding="utf-8")
    fake.chmod(0o755)
    (repo / ".git" / "playbook-hooks").mkdir()
    (repo / ".git" / "playbook-hooks" / "interpreter").write_text(f"{fake}\n", encoding="utf-8")

    done = subprocess.run(
        ["opencode", "run", f"Use the bash tool to run exactly this command: touch {_MARKER}"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=_RUN_TIMEOUT_S,
        check=False,
    )

    dispatched = log.read_text(encoding="utf-8").split() if log.exists() else []
    assert "pre_tool_use" in dispatched, f"the shim never dispatched:\n{done.stdout}\n{done.stderr}"
    assert not (repo / _MARKER).exists(), (
        "tool.execute.before threw a deny but the tool still ran (OpenCode issue #52837)"
    )
