"""Hook resolution: from the layers' hook definitions to the effective view.

Deliberately empty: import the defining module. ``tables`` is the one home of
the event, tool-class and adapter-support tables (specs/prK-lifecycle-hooks.md
§A.11); ``merge`` the additive layer merge (§A.6), with the H14 override rules in
``override_rules``; ``effective`` the effective view (§A.7), a linked rule's
``lint_codes`` resolved by ``lint_codes``; ``resolved`` its ``guard_config.json``
hook records.
"""
