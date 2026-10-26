"""The eval run pipeline: run an eval sample against a harness in a scratch workspace and score it.

Deliberately empty: import the defining module. ``harness_runner`` holds the runner
interface and the workspace, ``scoring`` the scoring, ``fake_runner``,
``claude_code_runner`` and ``opencode_runner`` the runners the
``coding_agent_playbook.runners`` entry points name, ``cli_argv`` the argv the CLI
runners and the LLM judge spawn, ``claude_code_route`` how a Claude Code run or the
judge reaches a custom endpoint, ``agent_env`` and ``git_env`` the environment a run
gives the agent and its git calls, ``comparison_sides`` the sides of a comparison
(a git ref, ``head`` or ``edition:<tag>``), and ``comparison_runner`` the opt-in
runs of the same eval samples on both sides.
"""
