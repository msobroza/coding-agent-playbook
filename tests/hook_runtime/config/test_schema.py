"""The ``guard_config.json`` contract names the writer shares with the runtime (specs/prT-package-layout.md 9 AC.2.5).

Sync's writer imports the file path, the schema version and the shared tables
from ``hook_runtime.config.schema``, and the dispatcher loads the module on
every event, so a fresh interpreter importing it pays only for the stdlib and
the hook runtime's own package roots.
"""

from __future__ import annotations

import sys

from tests.engine_modules import engine_module
from tests.import_probe import new_modules_after


def test_schema_module_loads_only_the_stdlib_and_its_package_roots() -> None:
    loaded = new_modules_after("import coding_agent_playbook.hook_runtime.config.schema")

    engine_modules = [name for name in loaded if name.split(".")[0] not in sys.stdlib_module_names]
    assert engine_modules == [
        engine_module("coding_agent_playbook.hook_runtime"),
        engine_module("coding_agent_playbook.hook_runtime.config"),
        engine_module("coding_agent_playbook.hook_runtime.config.schema"),
    ]
