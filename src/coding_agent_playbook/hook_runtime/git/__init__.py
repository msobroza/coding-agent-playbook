"""Every git call the hook runtime makes (specs/prK-lifecycle-hooks.md §D.5.3).

``safe_git`` is the interface: ``SafeGit`` runs git hardened and ``GitPort`` is
the seam the dispatch depends on. ``_argv`` builds the hardened argv and env,
``_cache`` keeps the git version and filter-driver discovery, ``_fingerprint``
computes the working-tree fingerprint and ``parse`` holds the pure parsers of
git's output. ``log`` and ``range`` are ``SafeGit``'s commit-log and revision
query mixins, ``memo`` answers each read-only call once per dispatch and
``head_snapshot`` keeps the session's default-branch snapshot. Importers name
these modules directly, so this module is a docstring only.
"""
