"""Run the rendered OpenCode shim under node against a fake dispatcher (specs/prK-lifecycle-hooks.md §C.3.2, §C.3.5).

``ShimRepo`` is a tmp worktree holding the shim at its committed path, a
``package.json`` declaring ESM (node 18 reads a bare ``.js`` as CommonJS) and
a per-worktree pin naming a fake ``sh`` dispatcher. The fake is the only
process boundary: it records each call's argv and stdin under ``calls/<n>/``,
then marks the record complete with ``calls/<n>/done`` (a fired, not awaited,
dispatch may still be writing it when the shim returns)
and replays the canned stdout and exit code in ``responses/<event>.{out,code}``,
or ``exec``s ``sleep`` for ``responses/<event>.sleep`` seconds so the shim's
kill reaches it. ``tests/fixtures/opencode/shim_driver.mjs`` calls the server
hooks the way OpenCode V1 does. No real dispatcher, no network. POSIX-only.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hook_runtime.dispatch.decision import CombinedResult, Decision
from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hook_runtime.harness.opencode import render_opencode
from coding_agent_playbook.hooks.registrations.opencode import (
    OPENCODE_SHIM_PATH,
    render_opencode_shim,
)
from tests.node_kit import run_node

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.harness.wire import WireOutput
    from coding_agent_playbook.hooks.registrations.opencode import OpenCodeRegEntry

type Step = dict[str, Any]

SESSION = "ses_1"
#: The pin's argv before ``<event>``: the §D.1 runtime launch.
RUNTIME_ARGV = ["-I", "-m", "coding_agent_playbook.hook_runtime", "dispatch"]
SETUP: Step = {"setup": True}
_WARM_TIMEOUT_S = 30
_DRIVER = Path(__file__).resolve().parents[1] / "fixtures" / "opencode" / "shim_driver.mjs"
_FAKE_DISPATCHER = """\
#!/bin/sh
[ "$1" = --warm ] && exit 0
d='{fake}'
n=$(cat "$d/count" 2>/dev/null || echo 0)
echo $((n + 1)) > "$d/count"
mkdir -p "$d/calls/$n"
echo $$ > "$d/calls/$n/pid"
printf '%s\\n' "$@" > "$d/calls/$n/argv"
cat > "$d/calls/$n/stdin"
: > "$d/calls/$n/done"
r="$d/responses/$5"
if [ -f "$r.sleep" ]; then exec sleep "$(cat "$r.sleep")"; fi
if [ -f "$r.out" ]; then cat "$r.out"; fi
exit "$(cat "$r.code" 2>/dev/null || echo 0)"
"""


@dataclass(frozen=True)
class DispatchCall:
    """One spawn of the pin: its argv after the interpreter, the stdin it read, its pid."""

    argv: list[str]
    stdin: bytes
    pid: int

    @property
    def event(self) -> str:
        """The canonical event the shim dispatched (argv ``dispatch <event>``)."""
        return self.argv[len(RUNTIME_ARGV)]

    @property
    def payload(self) -> dict[str, Any]:
        """The stdin JSON object."""
        body: dict[str, Any] = json.loads(self.stdin)
        return body


@dataclass(frozen=True)
class ShimRun:
    """One driver run: a result per step, the shim's ``console.error`` lines, every dispatch."""

    results: list[dict[str, Any]]
    errors: list[str]
    calls: list[DispatchCall]

    @property
    def events(self) -> list[str]:
        """The dispatched events, in call order."""
        return [call.event for call in self.calls]


@dataclass(frozen=True)
class ShimRepo:
    """A worktree with the rendered shim; ``root`` and ``fake`` are resolved real paths.

    Example::

        shim = ShimRepo.create(tmp_path, {"session_start": {"timeout_ms": 2000}})
        shim.pin()
        run = shim.run([transform()])
    """

    root: Path
    fake: Path

    @classmethod
    def create(cls, tmp_path: Path, reg: Mapping[str, OpenCodeRegEntry]) -> ShimRepo:
        """A ``.git`` dir, an ESM ``package.json`` and the shim rendered for ``reg``; no pin yet."""
        root = tmp_path / "repo"
        (root / ".git").mkdir(parents=True)
        (root / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
        shim = root / OPENCODE_SHIM_PATH
        shim.parent.mkdir(parents=True)
        shim.write_text(render_opencode_shim(reg), encoding="utf-8")
        fake = tmp_path / "fake"
        (fake / "calls").mkdir(parents=True)
        (fake / "responses").mkdir()
        dispatcher = fake / "dispatch"
        dispatcher.write_text(_FAKE_DISPATCHER.format(fake=fake.resolve()), encoding="utf-8")
        dispatcher.chmod(0o755)
        # macOS vets a new executable on its first exec, which can outlast a 200 ms shim timeout.
        subprocess.run([str(dispatcher), "--warm"], check=True, timeout=_WARM_TIMEOUT_S)
        return cls(root.resolve(), fake.resolve())

    def pin(self, interpreter: str | None = None, *, git_dir: Path | None = None) -> None:
        """Write ``<git_dir>/playbook-hooks/interpreter``, by default naming the fake dispatcher."""
        state = (git_dir or self.root / ".git") / "playbook-hooks"
        state.mkdir(parents=True, exist_ok=True)
        target = interpreter or str(self.fake / "dispatch")
        (state / "interpreter").write_text(f"{target}\n", encoding="utf-8")

    def respond(self, event: str, wire: WireOutput) -> None:
        """Make the fake answer ``event`` with ``wire``'s stdout and exit code."""
        (self.fake / "responses" / f"{event}.out").write_text(wire.stdout, encoding="utf-8")
        (self.fake / "responses" / f"{event}.code").write_text(str(wire.exit_code))

    def hang(self, event: str, seconds: int) -> None:
        """Make the fake sleep through ``event`` instead of answering."""
        (self.fake / "responses" / f"{event}.sleep").write_text(str(seconds))

    def run(self, steps: list[Step]) -> ShimRun:
        """Drive the shim through ``steps`` in one node process (so ``warned`` is shared)."""
        shim = self.root / OPENCODE_SHIM_PATH
        args = [str(_DRIVER), str(shim), str(self.fake / "responses")]
        done = run_node(args, stdin=json.dumps(steps), cwd=self.root)
        assert done.returncode == 0, done.stderr
        body = json.loads(done.stdout)
        return ShimRun(body["results"], body["errors"], self.calls())

    def calls(self) -> list[DispatchCall]:
        """Every completely recorded dispatch, oldest first.

        A record without its ``done`` marker is still being written by an async
        (fired, not awaited) dispatch; reading it raced on CI (PR #266), so it is
        left out until complete (``tests/adapters/test_opencode_shim_node.py``
        polls for it).
        """
        dirs = [path for path in (self.fake / "calls").iterdir() if (path / "done").exists()]
        return [_call(directory) for directory in sorted(dirs, key=lambda path: int(path.name))]


def _call(directory: Path) -> DispatchCall:
    return DispatchCall(
        argv=(directory / "argv").read_text(encoding="utf-8").splitlines(),
        stdin=(directory / "stdin").read_bytes(),
        pid=int((directory / "pid").read_text(encoding="utf-8")),
    )


def rendered(
    event: str,
    decision: Decision = Decision.NONE,
    *,
    reason: str = "",
    context: tuple[str, ...] = (),
    user_notes: tuple[str, ...] = (),
) -> WireOutput:
    """What the real dispatcher writes for this combined result (``render_opencode``)."""
    combined = CombinedResult(
        decision=decision, reason=reason, context=context, user_notes=user_notes
    )
    return render_opencode(EventName(event), combined)


def before(
    tool: str, args: dict[str, Any], *, call: str = "call_1", session: str = SESSION
) -> Step:
    """``tool.execute.before(input, output)`` as OpenCode V1 calls it."""
    return {
        "hook": "tool.execute.before",
        "input": {"tool": tool, "sessionID": session, "callID": call},
        "output": {"args": args},
    }


def after(
    tool: str, output: object, *, args: dict[str, Any] | None = None, call: str = "call_1"
) -> Step:
    """``tool.execute.after(input, output)``: V1 passes the call's args on ``input``."""
    return {
        "hook": "tool.execute.after",
        "input": {"tool": tool, "sessionID": SESSION, "callID": call, "args": args or {}},
        "output": {"title": "t", "output": output, "metadata": {}},
    }


def transform(session: str = SESSION) -> Step:
    """One model request: ``experimental.chat.system.transform``."""
    return {
        "hook": "experimental.chat.system.transform",
        "input": {"sessionID": session},
        "output": {"system": []},
    }


def idle(session: str = SESSION, kind: str = "session.idle") -> Step:
    """A bus event; OpenCode does not await this hook, the driver does."""
    return {
        "hook": "event",
        "input": {"event": {"type": kind, "properties": {"sessionID": session}}},
    }


def respond_step(event: str, wire: WireOutput) -> Step:
    """Change the fake's answer for ``event`` mid-run."""
    return {"respond": {"event": event, "out": wire.stdout, "code": wire.exit_code}}
