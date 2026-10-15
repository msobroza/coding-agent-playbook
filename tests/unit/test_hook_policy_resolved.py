"""``ResolvedHook.to_json()``: the single ``guard_config.json`` hook record (prK §A.7, §D.8.2).

One name per field (``supports``, ``matcher``, ``timeout_ms``), a handler record
per declared event (``kind`` builtin or external), the top-level
``script_sha256``, and nothing machine-specific: external argv is the logical
launcher plus the repo-relative script copy under ``HOOK_SCRIPTS_DIR``. Also the
advisory rule the effective view hands K3, with globs inherited from a linked rule.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook._hook_schema import MATCHER_KEYS
from coding_agent_playbook.hook_policy import (
    HOOK_SCRIPTS_DIR,
    ResolvedHook,
    resolve_effective_hooks,
)
from coding_agent_playbook.hooks_config import GuardrailsConfig, HooksConfig
from coding_agent_playbook.types import Hook, Rule, RuleFrontmatter
from tests.hook_samples import sample_hook, write_hook

if TYPE_CHECKING:
    from collections.abc import Sequence

OVERLAY = "acme_rules"
_EXTERNAL = {"command": "python", "script": "scripts/check.py", "args": ["--max", "5"]}


def _resolved(
    hook: Hook, *, cfg: HooksConfig | None = None, rules: Sequence[Rule] = ()
) -> ResolvedHook:
    view = resolve_effective_hooks(
        [hook],
        rules,
        HooksConfig(enabled=True) if cfg is None else cfg,
        GuardrailsConfig(),
        {},
        Path("/repo"),
        adapters_enabled=["claude_code", "opencode"],
    )
    (resolved,) = view.resolved
    return resolved


def _external_hook(root: Path, script: bytes = b"print('ok')\n", **overrides: Any) -> Hook:
    """An overlay hook on disk whose external handler runs ``scripts/check.py``."""
    path = write_hook(root, "guard-x", scripts=True, **{"handler": _EXTERNAL, **overrides})
    (path.parent / "scripts" / "check.py").write_bytes(script)
    return Hook.from_markdown(path, OVERLAY)


def test_to_json_field_names_exact() -> None:
    hook = sample_hook(
        priority=10,
        timeout=2.5,
        matcher={"pre_tool_use": {"tools": ["edit", "write"]}},
        handler={"builtin": "guard_x", "config": {"extra_protected": []}},
    )

    record = _resolved(hook).to_json()

    assert list(record) == [
        "id",
        "source_package",
        "events",
        "priority",
        "matcher",
        "handlers",
        "decisions",
        "timeout_ms",
        "on_error",
        "supports",
        "mandatory",
        "script_sha256",
    ]
    assert record["timeout_ms"] == 2500
    assert isinstance(record["timeout_ms"], int)
    assert list(record["matcher"]["pre_tool_use"]) == list(MATCHER_KEYS)
    assert record["matcher"]["pre_tool_use"]["tools"] == ["edit", "write"]
    assert record["handlers"] == {
        "pre_tool_use": {
            "kind": "builtin",
            "name": "guard_x",
            "config": {"extra_protected": []},
        }
    }
    assert record["on_error"] == {"pre_tool_use": "ask"}
    assert record["supports"] == ["claude_code"]
    assert (record["mandatory"], record["script_sha256"]) == (False, None)


def test_to_json_has_a_matcher_entry_for_every_event() -> None:
    """An event without an authored matcher matches every occurrence: all lists empty."""
    record = _resolved(sample_hook(events=["stop"], decisions=["none"])).to_json()

    assert record["matcher"] == {"stop": {key: [] for key in MATCHER_KEYS}}


def test_to_json_external_handler_record(tmp_path: Path) -> None:
    record = _resolved(_external_hook(tmp_path)).to_json()

    assert record["handlers"] == {
        "pre_tool_use": {
            "kind": "external",
            "argv": ["python", f"{HOOK_SCRIPTS_DIR}/guard-x/check.py", "--max", "5"],
            "config": {},
        }
    }


def test_to_json_is_machine_independent(tmp_path: Path) -> None:
    record = _resolved(_external_hook(tmp_path)).to_json()

    text = json.dumps(record, sort_keys=True)
    assert json.loads(text) == record
    assert str(tmp_path) not in text
    assert str(Path.home()) not in text
    assert sys.prefix not in text
    argv = record["handlers"]["pre_tool_use"]["argv"]
    assert not any(Path(part).is_absolute() for part in argv)


def test_to_json_returns_copies() -> None:
    resolved = _resolved(sample_hook(handler={"builtin": "guard_x", "config": {"rows": ["a"]}}))

    resolved.to_json()["handlers"]["pre_tool_use"]["config"]["rows"].append("b")

    assert resolved.handlers["pre_tool_use"].config == {"rows": ["a"]}


def test_resolved_hook_is_frozen() -> None:
    resolved = _resolved(sample_hook())

    with pytest.raises(dataclasses.FrozenInstanceError):
        resolved.priority = 1  # type: ignore[misc]


# --- script_sha256 ----------------------------------------------------------------------


def test_script_sha256_hashes_the_script_bytes(tmp_path: Path) -> None:
    script = b"import sys\nprint(sys.argv)\n"

    resolved = _resolved(_external_hook(tmp_path, script))

    assert resolved.script_sha256 == hashlib.sha256(script).hexdigest()


def test_script_sha256_is_none_for_a_builtin_hook() -> None:
    assert _resolved(sample_hook()).script_sha256 is None


def test_script_sha256_covers_every_script_the_hook_runs(tmp_path: Path) -> None:
    handlers = {
        "pre_tool_use": {**_EXTERNAL, "script": "scripts/check.py"},
        "post_tool_use": {**_EXTERNAL, "script": "scripts/after.py"},
    }
    hook = _external_hook(
        tmp_path,
        events=["pre_tool_use", "post_tool_use"],
        decisions=["deny", "context", "none"],
        handler=None,
        handlers=handlers,
    )
    assert hook.scripts_dir is not None
    (hook.scripts_dir / "after.py").write_bytes(b"after\n")

    first = _resolved(hook).script_sha256
    (hook.scripts_dir / "after.py").write_bytes(b"changed\n")

    assert first is not None
    assert first != hashlib.sha256(b"print('ok')\n").hexdigest()
    assert _resolved(hook).script_sha256 not in (None, first)


def test_script_outside_scripts_dir_is_never_hashed(tmp_path: Path) -> None:
    """Validate rejects the escape (H7); the effective view must not read the file."""
    hook = _external_hook(tmp_path, handler={**_EXTERNAL, "script": "../outside.py"})
    assert hook.hook_dir is not None
    (hook.hook_dir.parent / "outside.py").write_bytes(b"secret\n")

    assert _resolved(hook).script_sha256 is None


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
def test_symlinked_script_is_never_hashed(tmp_path: Path) -> None:
    hook = _external_hook(tmp_path)
    assert hook.scripts_dir is not None
    target = tmp_path / "elsewhere.py"
    target.write_bytes(b"elsewhere\n")
    (hook.scripts_dir / "check.py").unlink()
    (hook.scripts_dir / "check.py").symlink_to(target)

    assert _resolved(hook).script_sha256 is None


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX modes, ignored by root"
)
def test_unreadable_script_has_no_digest(tmp_path: Path) -> None:
    hook = _external_hook(tmp_path)
    assert hook.scripts_dir is not None
    script = hook.scripts_dir / "check.py"
    script.chmod(0)
    try:
        digest = _resolved(hook).script_sha256
    finally:
        script.chmod(0o644)

    assert digest is None


def test_missing_script_has_no_digest(tmp_path: Path) -> None:
    hook = _external_hook(tmp_path)
    assert hook.scripts_dir is not None
    (hook.scripts_dir / "check.py").unlink()

    assert _resolved(hook).script_sha256 is None


# --- the advisory rule (§A.8) -----------------------------------------------------------


def _scoped_rule() -> Rule:
    frontmatter = RuleFrontmatter(
        id="pii-handling",
        name="PII handling",
        description="Mask PII.",
        scope="scoped",
        globs=["**/*.sql"],
    )
    return Rule(frontmatter, "Mask it.\n", "Mask it.\n", False, None, "<repo-local>")


def test_advisory_rule_uses_inherited_globs() -> None:
    resolved = _resolved(sample_hook(linked_rule="pii-handling"), rules=[_scoped_rule()])

    advisory = resolved.advisory
    assert advisory is not None
    assert advisory.frontmatter.id == "guardrail-guard-x"
    assert (advisory.frontmatter.scope, advisory.frontmatter.globs) == ("scoped", ["**/*.sql"])
    assert advisory.body == "Advice.\n"


def test_advisory_is_none_when_hooks_advisory_is_false() -> None:
    cfg = HooksConfig(enabled=True, advisory=False)

    assert _resolved(sample_hook(), cfg=cfg).advisory is None


def test_advisory_is_none_for_a_blank_body() -> None:
    hook = dataclasses.replace(sample_hook(), body="  \n", template_body="  \n")

    assert _resolved(hook).advisory is None
