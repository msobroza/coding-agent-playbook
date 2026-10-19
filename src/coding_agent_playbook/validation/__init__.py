"""Validation: the checks ``playbook validate`` and the sync gate run over canonical artifacts.

Deliberately empty: import the defining module. ``checks`` is the rule set
(``collect_validation_findings`` and the sync gate ``sync_gate_errors``), ``findings``
the ``ValidationError`` type and its reporters, ``context`` the ``SyncContext`` every
catalog-reading command builds and the config-less context of an engine or overlay
checkout, ``preflight`` the environment checks sync, init, check
and validate share, ``link_check`` the markdown link parser, and ``prompts`` the
prompt checks (public because ``playbook sync --check-staged`` imports
``check_prompt_rule_calls``). The underscore modules are the other per-kind checks
``checks`` runs. Nothing here writes a file.
"""
