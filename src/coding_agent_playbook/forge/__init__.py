"""Forges: which forge a remote is on, and what its forge CLI looks like, offline (ADR 0003).

``hosts`` maps a git remote URL to its host and the host to a forge (GitHub or
GitLab) from the ``[forge] hosts`` table and the environment, both passed in;
``dialects`` holds each forge CLI's per-forge tables (argv0, its commands'
value-taking, file-carrying and pushing flags, host and token env vars, push
options); ``operations`` is the forge-operation catalogue ``playbook forge``
runs and the guards recognise. The package imports only the standard library
and other stdlib leaves, never contacts a forge and runs no subprocess: the
hook runtime reads ``dialects`` and ``operations`` on its hot path. This module
is a docstring only.
"""
