"""The hook trust contract ``playbook validate`` enforces (specs/prK-lifecycle-hooks.md §B.5).

Deliberately empty: import the defining module. ``contract`` checks one hook,
``contract_set`` checks across hooks and config, ``handler_catalog`` checks
against the handler registry (H6/H21's registry half), and ``findings`` is the
issue type they all return (``HookIssue``, ``Severity``, ``did_you_mean``).
"""
