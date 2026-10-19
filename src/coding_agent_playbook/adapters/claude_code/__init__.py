"""The Claude Code adapter's package: the adapter, its hooks, rule paths and settings merge.

``adapter`` holds ``ClaudeCodeAdapter`` (the ``claude_code`` entry point); ``hooks``
emits the managed hook groups, the launcher and the heartbeat, with the private
``_secret_native``, ``_destructive_native`` and ``_overlay_native`` row sources;
``paths`` is the stdlib-only leaf that names where the adapter composes its rules;
``settings`` holds the co-owned ``.claude/settings.json`` merge and its drift check.
This module is a docstring only: import the defining module.
"""
