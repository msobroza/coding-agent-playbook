"""The eval run pipeline: run an eval sample against a harness in a scratch workspace and score it.

Deliberately empty: import the defining module. ``harness_runner`` holds the runner
interface and the workspace, ``scoring`` the scoring, ``fake_runner``,
``claude_code_runner`` and ``opencode_runner`` the runners the
``coding_agent_playbook.runners`` entry points name, ``agent_env`` and ``git_env``
the environment a run gives the agent and its git calls.
"""
