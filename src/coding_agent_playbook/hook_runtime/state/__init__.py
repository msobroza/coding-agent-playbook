"""What the hook runtime remembers between processes (specs/prK-lifecycle-hooks.md §D.6).

``store`` is the per-worktree state root ``<git_dir>/playbook-hooks``;
``_files`` holds its no-follow file primitives and ``_sweep`` its bounded TTL
sweep. ``session`` keeps the per-session flags and dedupe keys, ``ledger`` the
paths a session touched and the checks it ran, and ``active_prompt`` (with
``_prompt_boundary``) the playbook prompt the turn is running. ``audit_log``
is the one append-only JSONL writer of the engine's local logs and
``decision_summary`` counts the guard-decision log per guard. Importers name
these modules directly, so this module is a docstring only.
"""
