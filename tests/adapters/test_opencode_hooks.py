"""The generated OpenCode V1 shim (specs/prK-lifecycle-hooks.md §C.0, §C.1.2, §C.3.1, §C.3.2, §C.7).

``OpenCodeAdapter`` buffers every hook and, in ``finalize``, renders exactly one
file, ``.opencode/plugins/playbook-hooks.js``, from the packaged template: a
``//`` sentinel on line 1, one ``export default`` object, ``node:`` imports only
and the ``REG`` table of the hooks OpenCode can enforce. It owns that one path
and no other file under ``.opencode/plugin(s)/``: a stale shim is found by a
single-path check, never by walking the user's plugins dir.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.opencode import OpenCodeAdapter
from coding_agent_playbook.generated_output.sentinel import has_sentinel, sentinel_line
from coding_agent_playbook.generated_output.write_guard import UserOwnedFileError
from coding_agent_playbook.hooks.registrations.opencode import (
    OPENCODE_SHIM_PATH,
    opencode_reg_json,
    plan_opencode_reg,
    render_opencode_shim,
)
from coding_agent_playbook.hooks.registrations.templates.opencode_wire_port import (
    WIRE_BEGIN,
    WIRE_END,
)
from coding_agent_playbook.hooks.resolution.tables import HOOK_SUPPORT
from tests.fakes import record_opens
from tests.hook_runtime.handlers.pack_repo import resolve_engine_hooks
from tests.hook_samples import resolved_hook
from tests.node_kit import needs_node, run_node

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

pytestmark = pytest.mark.catalog

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")

_BOTH = ("claude_code", "opencode")
_GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "opencode" / "playbook-hooks.golden.js"


def _pack() -> list[ResolvedHook]:
    """A small default-pack-like hook set: one per OpenCode event, plus a Claude-only hook."""
    return [
        resolved_hook(
            "guard-generated-outputs",
            supports=_BOTH,
            matcher={"pre_tool_use": {"tools": ["edit", "write", "notebook_edit", "shell"]}},
        ),
        resolved_hook(
            "post-edit-lint",
            events=("post_tool_use",),
            supports=_BOTH,
            timeout=10.0,
            matcher={"post_tool_use": {"tools": ["edit", "write"]}},
        ),
        resolved_hook("stop-gate", events=("stop",), supports=_BOTH, timeout=5.0),
        resolved_hook("claude-only", supports=("claude_code",), timeout=3.0),
    ]


def _finalize(out: Path, hooks: Sequence[ResolvedHook]) -> tuple[OpenCodeAdapter, list[Path]]:
    """One adapter pass as sync drives it: begin_sync, every hook, then finalize."""
    adapter = OpenCodeAdapter()
    adapter.begin_sync(out, None)
    written = [path for hook in hooks for path in adapter.write_hook(hook, out)]
    return adapter, written + adapter.finalize(out)


def _shim_text(tmp_path: Path) -> str:
    _finalize(tmp_path, _pack())
    return (tmp_path / OPENCODE_SHIM_PATH).read_text(encoding="utf-8")


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _tagged(name: str) -> str:
    return f"{sentinel_line('slash')}\nexport default {{ id: {name!r} }}\n"


# --- class contract ----------------------------------------------------------------------------


def test_hook_support_equals_the_hooks_table() -> None:
    assert OpenCodeAdapter.hook_support == HOOK_SUPPORT["opencode"]
    assert "pre_compact" not in OpenCodeAdapter.hook_support


def test_output_locations_declare_shim_as_file_not_directory() -> None:
    locations = OpenCodeAdapter.output_locations

    assert OPENCODE_SHIM_PATH == ".opencode/plugins/playbook-hooks.js"
    assert OPENCODE_SHIM_PATH in locations
    # Pruning stops at a declared directory, so the user's plugins dir is never one.
    assert not any(loc.startswith(".opencode/plugin") and loc.endswith("/") for loc in locations)


def test_shim_is_declared_a_runtime_output() -> None:
    assert OpenCodeAdapter.runtime_outputs == (OPENCODE_SHIM_PATH,)


# --- write_hook / finalize ---------------------------------------------------------------------


def test_write_hook_returns_no_paths(tmp_path: Path) -> None:
    adapter = OpenCodeAdapter()

    assert [adapter.write_hook(hook, tmp_path) for hook in _pack()] == [[], [], [], []]
    assert list(tmp_path.iterdir()) == []


def test_finalize_without_hooks_writes_no_shim(tmp_path: Path) -> None:
    _, written = _finalize(tmp_path, [])

    assert written == []
    assert not (tmp_path / ".opencode").exists()


def test_finalize_without_an_opencode_member_writes_no_shim(tmp_path: Path) -> None:
    _, written = _finalize(tmp_path, [resolved_hook("claude-only", supports=("claude_code",))])

    assert written == []
    assert not (tmp_path / ".opencode" / "plugins").exists()


def test_finalize_renders_golden_shim(tmp_path: Path) -> None:
    _, written = _finalize(tmp_path, _pack())

    assert written == [tmp_path / OPENCODE_SHIM_PATH]
    assert (tmp_path / OPENCODE_SHIM_PATH).read_bytes() == _GOLDEN.read_bytes()


def test_finalize_writes_only_playbook_hooks_js(tmp_path: Path) -> None:
    _finalize(tmp_path, _pack())

    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert files == [OPENCODE_SHIM_PATH]
    assert [p.name for p in (tmp_path / ".opencode" / "plugins").iterdir()] == ["playbook-hooks.js"]


def test_render_is_deterministic_across_hook_order(tmp_path: Path) -> None:
    _finalize(tmp_path / "a", _pack())
    _finalize(tmp_path / "b", list(reversed(_pack())))

    first = (tmp_path / "a" / OPENCODE_SHIM_PATH).read_bytes()
    assert (tmp_path / "b" / OPENCODE_SHIM_PATH).read_bytes() == first


# --- the rendered file -------------------------------------------------------------------------


def test_shim_line1_is_slash_sentinel(tmp_path: Path) -> None:
    text = _shim_text(tmp_path)

    assert text.split("\n", 1)[0] == sentinel_line("slash")
    assert has_sentinel(text)


def test_shim_has_exactly_one_export_default_object(tmp_path: Path) -> None:
    exports = [line for line in _shim_text(tmp_path).splitlines() if re.match(r"\s*export\b", line)]

    assert exports == ["export default {"]


def test_shim_imports_only_node_builtins(tmp_path: Path) -> None:
    text = _shim_text(tmp_path)
    specifiers = re.findall(r"^import\b.*?\bfrom\s+\"([^\"]+)\"", text, flags=re.MULTILINE)

    assert specifiers, "expected the shim's static imports"
    assert all(spec.startswith("node:") for spec in specifiers)
    assert "require(" not in text
    assert "@opencode-ai" not in text
    assert re.search(r"\bimport\s*\(", text) is None  # no dynamic import either


def test_shim_has_no_shebang_lf_endings_and_final_newline(tmp_path: Path) -> None:
    _finalize(tmp_path, _pack())
    data = (tmp_path / OPENCODE_SHIM_PATH).read_bytes()

    assert not data.startswith(b"#!")
    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in data
    assert data.endswith(b"}\n") and not data.endswith(b"\n\n")


@pytest.mark.catalog
def test_shim_golden_with_async_post_tool_use(tmp_path: Path) -> None:
    """OQ-19: local-audit-log becomes the ``async`` pre-filter of ``post_tool_use`` in REG."""
    audit = resolve_engine_hooks(["local-audit-log"], tmp_path / "engine")

    with_lint = plan_opencode_reg([*_pack(), *audit])
    alone = plan_opencode_reg(audit)
    _finalize(tmp_path / "out", [*_pack(), *audit])
    text = (tmp_path / "out" / OPENCODE_SHIM_PATH).read_text(encoding="utf-8")

    plain = plan_opencode_reg(_pack())["post_tool_use"]
    assert with_lint["post_tool_use"] == {**plain, "async": "*"}  # the sync pre-filter unchanged
    assert alone["post_tool_use"] == {"timeout_ms": 62_000, "tools": [], "async": "*"}
    assert list(alone) == ["session_start", "post_tool_use"]
    assert f"const REG = {opencode_reg_json(with_lint)}\n" in text
    assert '"--project-dir", ROOT, "--async"]' in text


def test_shim_embeds_reg_as_one_json_line(tmp_path: Path) -> None:
    text = _shim_text(tmp_path)
    [line] = [line for line in text.splitlines() if line.startswith("const REG = ")]

    assert line == "const REG = " + opencode_reg_json(plan_opencode_reg(_pack()))
    assert "@@REG@@" not in text and "@@SENTINEL_LINE@@" not in text


def test_shim_marks_the_wire_parse_slice_once(tmp_path: Path) -> None:
    lines = _shim_text(tmp_path).splitlines()

    assert lines.count(WIRE_BEGIN) == 1 and lines.count(WIRE_END) == 1
    wire = "\n".join(lines[lines.index(WIRE_BEGIN) + 1 : lines.index(WIRE_END)])
    for definition in ("const CAP = ", "function inactive(", "function parse("):
        assert definition in wire


@pytest.mark.parametrize("copies", [0, 2], ids=["missing", "twice"])
def test_render_replaces_placeholder_exactly_once_and_rejects_template_without_it(
    copies: int,
) -> None:
    reg = plan_opencode_reg(_pack())
    template = "@@SENTINEL_LINE@@\nconst REG = /*@@REG@@*/\n"

    rendered = render_opencode_shim(reg, template=template)
    assert rendered == f"{sentinel_line('slash')}\nconst REG = {opencode_reg_json(reg)}\n"

    broken = "@@SENTINEL_LINE@@\n" + "const REG = /*@@REG@@*/\n" * copies
    with pytest.raises(ValueError, match=rf"exactly once, found {copies}"):
        render_opencode_shim(reg, template=broken)


# --- ownership: stale shim, user plugins, symlinks ---------------------------------------------


def test_stale_shim_removed_when_no_hooks_remain(tmp_path: Path) -> None:
    _finalize(tmp_path, _pack())
    shim = tmp_path / OPENCODE_SHIM_PATH
    adapter, written = _finalize(tmp_path, [])

    assert written == []
    assert adapter.stale_outputs(set(), tmp_path) == [shim]
    assert adapter.cleanup_stale(set(), tmp_path) == [shim]
    assert not shim.exists()
    assert (tmp_path / ".opencode" / "plugins").is_dir()  # the dir may hold user plugins


def test_written_shim_is_not_stale(tmp_path: Path) -> None:
    adapter, written = _finalize(tmp_path, _pack())

    assert adapter.stale_outputs({path.resolve() for path in written}, tmp_path) == []


def test_sentinel_tagged_user_plugins_are_never_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_plugins = [
        _write(tmp_path / ".opencode" / "plugins" / "other.js", _tagged("other")),
        _write(tmp_path / ".opencode" / "plugin" / "hook.ts", _tagged("hook")),
        _write(tmp_path / ".opencode" / "plugins" / "pkg" / "index.js", _tagged("pkg")),
        _write(tmp_path / ".opencode/plugins/pkg/node_modules/dep/index.js", _tagged("dep")),
    ]
    opened = record_opens(monkeypatch)

    adapter = OpenCodeAdapter()
    assert adapter.cleanup_stale(set(), tmp_path) == []

    assert all(path.is_file() for path in user_plugins)
    assert [path for path in opened if path in user_plugins] == []


def test_shim_without_sentinel_is_user_owned(tmp_path: Path) -> None:
    shim = _write(tmp_path / OPENCODE_SHIM_PATH, "export default { id: 'mine' }\n")

    assert OpenCodeAdapter().cleanup_stale(set(), tmp_path) == []
    assert shim.is_file()


def test_finalize_refuses_a_same_named_user_file(tmp_path: Path) -> None:
    """Review #1: finalize used to overwrite a user's plugin of the same name."""
    shim = _write(tmp_path / OPENCODE_SHIM_PATH, "export default { id: 'mine' }\n")

    with pytest.raises(UserOwnedFileError, match=re.escape(OPENCODE_SHIM_PATH)):
        _finalize(tmp_path, _pack())

    assert shim.read_text(encoding="utf-8") == "export default { id: 'mine' }\n"


@posix_only
def test_finalize_refuses_a_symlinked_plugins_dir(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    repo = tmp_path / "repo"
    (repo / ".opencode").mkdir(parents=True)
    (repo / ".opencode" / "plugins").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UserOwnedFileError, match="symbolic link"):
        _finalize(repo, _pack())

    assert list(outside.iterdir()) == []


def test_finalize_rewrites_an_engine_owned_shim(tmp_path: Path) -> None:
    shim = _write(tmp_path / OPENCODE_SHIM_PATH, _tagged("old"))

    _finalize(tmp_path, _pack())

    assert shim.read_text(encoding="utf-8") == render_opencode_shim(plan_opencode_reg(_pack()))


def test_planned_runtime_outputs_name_the_shim_only_when_finalize_writes_it() -> None:
    adapter = OpenCodeAdapter()
    claude_only = resolved_hook("claude-only", supports=("claude_code",))

    assert adapter.planned_runtime_outputs(_pack()) == (OPENCODE_SHIM_PATH,)
    assert adapter.planned_runtime_outputs([claude_only]) == ()
    assert adapter.planned_runtime_outputs([]) == ()


@posix_only
@pytest.mark.parametrize("linked", ["file", "plugins-dir"])
def test_shim_symlink_is_never_opened_or_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linked: str
) -> None:
    outside = tmp_path / "outside"
    target = _write(outside / "playbook-hooks.js", _tagged("outside"))
    repo = tmp_path / "repo"
    shim = repo / OPENCODE_SHIM_PATH
    shim.parent.parent.mkdir(parents=True)
    if linked == "file":
        shim.parent.mkdir()
        shim.symlink_to(target)
    else:
        shim.parent.symlink_to(outside, target_is_directory=True)
    opened = record_opens(monkeypatch)

    assert OpenCodeAdapter().cleanup_stale(set(), repo) == []

    assert target.is_file()
    assert os.path.lexists(shim)
    assert [path for path in opened if path.resolve() == target.resolve()] == []


# --- node, when present ------------------------------------------------------------------------


def _as_module(tmp_path: Path) -> Path:
    """The rendered shim copied to ``.mjs``: node 18 parses a bare ``.js`` as CommonJS."""
    _finalize(tmp_path / "repo", _pack())
    module = tmp_path / "playbook-hooks.mjs"
    shutil.copyfile(tmp_path / "repo" / OPENCODE_SHIM_PATH, module)
    return module


@needs_node
def test_node_check_accepts_rendered_shim(tmp_path: Path) -> None:
    module = _as_module(tmp_path)

    done = run_node(["--check", str(module)])

    assert done.returncode == 0, done.stderr


_LOAD_PROBE = """\
const ns = await import(process.argv[1])
const hooks = await ns.default.server()
console.log(JSON.stringify({names: Object.keys(ns), keys: Object.keys(ns.default),
  id: ns.default.id, server: typeof ns.default.server, setup: typeof ns.default.setup,
  hooks: Object.keys(hooks)}))
"""


@needs_node
def test_node_loads_one_default_export_with_the_v1_server_hooks(tmp_path: Path) -> None:
    module = _as_module(tmp_path)

    done = run_node(["--input-type=module", "-e", _LOAD_PROBE, "--", module.as_uri()])

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {
        "names": ["default"],
        "keys": ["id", "server", "setup"],
        "id": "playbook.hooks",
        "server": "function",
        "setup": "function",
        "hooks": [
            "tool.execute.before",
            "tool.execute.after",
            "experimental.chat.system.transform",
            "event",
        ],
    }
