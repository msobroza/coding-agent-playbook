"""The ``guard_config.json`` contract names the writer shares with the runtime (specs/prT-package-layout.md 9 AC.2.5).

Sync's writer imports the file path, the schema version and the shared tables
from ``hook_runtime.config.schema``, and the dispatcher loads the module on
every event, so a fresh interpreter importing it pays only for the stdlib and
the hook runtime's own package roots.
"""

from __future__ import annotations

import sys

from coding_agent_playbook.hook_runtime.config.protected import (
    DEFAULT_HOOK_ARTIFACTS,
    ENGINE_RESOURCES_ID,
)
from coding_agent_playbook.hook_runtime.config.schema import (
    GUARD_CONFIG_SCHEMA_VERSION,
    HOOK_RECORD_KEYS,
    SUPPORTED_SCHEMA_VERSIONS,
    HandlerRecordJson,
)
from tests.engine_modules import engine_module
from tests.import_probe import new_modules_after

# Each derived contract value against the literal it replaced (GC-4): a change to
# one of them changes guard_config.json bytes or what the runtime accepts.


def test_supported_schema_versions_end_at_the_version_the_writer_writes() -> None:
    assert GUARD_CONFIG_SCHEMA_VERSION == 1
    assert SUPPORTED_SCHEMA_VERSIONS == (1, 1)


def test_engine_resources_id_is_the_engine_package_in_the_resource_root_format() -> None:
    assert ENGINE_RESOURCES_ID == "pkg:coding_agent_playbook/resources"


def test_default_hook_artifacts_open_with_the_hook_output_dir() -> None:
    assert DEFAULT_HOOK_ARTIFACTS == (
        ".coding-agent-playbook/hooks/",
        ".claude/hooks/playbook/",
        ".opencode/plugins/playbook-hooks.js",
    )


def test_hook_record_keys_are_the_twelve_guard_config_record_fields() -> None:
    assert sorted(HOOK_RECORD_KEYS) == [
        "decisions",
        "events",
        "handlers",
        "id",
        "mandatory",
        "matcher",
        "on_error",
        "priority",
        "script_sha256",
        "source_package",
        "supports",
        "timeout_ms",
    ]


def test_handler_record_requires_kind_and_config_and_locates_by_kind() -> None:
    """``name`` (builtin), ``target`` + ``dist`` (entry point) or ``argv`` (external)."""
    assert HandlerRecordJson.__required_keys__ == {"kind", "config"}
    assert HandlerRecordJson.__optional_keys__ == {"name", "target", "dist", "argv"}


def test_schema_module_loads_only_the_stdlib_and_its_package_roots() -> None:
    loaded = new_modules_after("import coding_agent_playbook.hook_runtime.config.schema")

    engine_modules = [name for name in loaded if name.split(".")[0] not in sys.stdlib_module_names]
    assert engine_modules == [
        engine_module("coding_agent_playbook.hook_runtime"),
        engine_module("coding_agent_playbook.hook_runtime.config"),
        engine_module("coding_agent_playbook.hook_runtime.config.schema"),
    ]
