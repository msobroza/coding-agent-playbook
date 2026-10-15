"""The one canonical-JSON hash of a managed settings element (specs/prK-lifecycle-hooks.md §B.6, §C.1.4).

Sync records a managed ``settings.json`` element as ``sha256(canonical_json(element))``
and control-plane-guard recognizes the element at run time by the same hash,
so both must use one function. It lives in the import-light
``_canonical_json`` (the runtime may not import ``adapters``), and K3's
``_settings_plan`` re-exports it.
"""

from __future__ import annotations

from coding_agent_playbook import _canonical_json
from coding_agent_playbook._canonical_json import canonical_json, element_sha256
from coding_agent_playbook.adapters import _settings_plan
from coding_agent_playbook.adapters._settings_plan import scoped_lock_entry
from tests.import_probe import run_python_probe

_GROUP = {"matcher": "Bash", "hooks": [{"type": "command", "command": "launch.sh pre", "é": 1}]}


def test_settings_plan_reexports_the_one_function() -> None:
    assert _settings_plan.canonical_json is _canonical_json.canonical_json


def test_element_sha256_is_the_scoped_lock_entry_hash() -> None:
    entry = scoped_lock_entry(
        ".claude/settings.json", "/hooks/PreToolUse", _GROUP, artifact_id="registration:x"
    )

    assert element_sha256(_GROUP) == entry.sha256
    assert canonical_json({"b": 1, "a": "é"}) == b'{"a":"\xc3\xa9","b":1}'


def test_key_order_and_formatting_never_change_the_hash() -> None:
    reordered = {
        "hooks": [{"é": 1, "command": "launch.sh pre", "type": "command"}],
        "matcher": "Bash",
    }

    assert element_sha256(reordered) == element_sha256(_GROUP)


def test_module_imports_only_json_and_hashlib() -> None:
    out = run_python_probe(
        "import sys, coding_agent_playbook; before = set(sys.modules); "
        "import coding_agent_playbook._canonical_json; "
        "print(sorted(m for m in set(sys.modules) - before if m.startswith('coding_agent')))"
    )

    assert out == "['coding_agent_playbook._canonical_json']"
