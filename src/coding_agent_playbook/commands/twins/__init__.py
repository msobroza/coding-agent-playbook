"""The Guard twins: CLI commands that run a guard hook's judge outside an agent session.

Deliberately empty: import the defining module. Each public module but one is a
``playbook`` subcommand (``gate_scan``, ``scan_secrets``, ``scan_sinks``,
``check_notebooks``, ``check_commit_trailers``, ``check_deps`` and the aggregate
``ci``); ``policy`` is the shared policy reader that ``init`` also imports. The
underscore modules (``_runner`` for the run skeleton every twin shares,
``_git_scope`` for the git a twin runs and the range it scans, ``_secret_scope``,
``_ci_commit_convention``, ``_ci_report``) are private to this package.
"""
