"""The human-run and self-check entries of the hook runtime (specs/prK-lifecycle-hooks.md §D.9).

``doctor`` answers whether this worktree's hook runtime is healthy, with its
environment checks in ``_doctor_checks``, its OpenCode checks in
``_doctor_opencode`` and its guard-decision-log summary in
``_doctor_decisions``. ``canary`` runs synthetic events through the real
pipeline, ``heartbeat`` turns the canaries into the session-start guard line,
and ``simulate`` runs the dispatch pipeline on one payload. Importers name
these modules directly, so this module is a docstring only.
"""
