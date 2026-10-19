"""The committed launcher's path, shared by registrations and the settings merge (H15).

``hooks/registrations/launcher.py`` is a stdlib leaf: the Claude Code settings
merge imports its token and stays stdlib-only, and the Claude registrations import
it instead of the adapters package, which sits above ``hooks`` in the layers
(specs/prT-package-layout.md 4.11, 6.3.1).
"""

from __future__ import annotations

import sys

from coding_agent_playbook.hooks.registrations.launcher import LAUNCHER_PATH, LAUNCHER_TOKEN
from tests.import_probe import new_modules_after


def test_launcher_path_is_the_repo_relative_token() -> None:
    assert LAUNCHER_TOKEN == "/.claude/hooks/playbook/launch.sh"
    assert LAUNCHER_PATH == ".claude/hooks/playbook/launch.sh"


def test_launcher_imports_only_the_stdlib() -> None:
    loaded = new_modules_after("import coding_agent_playbook.hooks.registrations.launcher")

    foreign = [
        name
        for name in loaded
        if not name.startswith("coding_agent_playbook")
        and name.split(".")[0] not in sys.stdlib_module_names
    ]
    assert foreign == []
    assert [name for name in loaded if name.startswith("coding_agent_playbook")] == [
        "coding_agent_playbook.hooks",
        "coding_agent_playbook.hooks.registrations",
        "coding_agent_playbook.hooks.registrations.launcher",
    ]


def test_claude_registrations_never_load_the_adapters() -> None:
    # The hooks -> adapters edge LAUNCHER_TOKEN used to make (6.3.1) stays gone.
    loaded = new_modules_after("import coding_agent_playbook.hooks.registrations.claude")

    assert [name for name in loaded if name.startswith("coding_agent_playbook.adapters")] == []
