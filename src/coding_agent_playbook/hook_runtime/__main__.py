"""``python -I -m coding_agent_playbook.hook_runtime``: the harness entry (specs/prK-lifecycle-hooks.md §D.1, A-C1)."""

import sys

from coding_agent_playbook.hook_runtime import cli

if __name__ == "__main__":  # pragma: no cover - harnesses run it as a fresh process
    raise SystemExit(cli.main(sys.argv[1:]))
