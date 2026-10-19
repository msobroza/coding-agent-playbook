"""The sync-time half of a Hook (specs/prK-lifecycle-hooks.md §A.6, §A.7, §A.11, §B.5).

Deliberately empty: import the defining module. ``resolution`` turns every
layer's hook definitions into the effective view sync compiles into
``guard_config.json``; ``contract`` is the trust contract ``playbook validate``
enforces; ``enforcement`` labels how each adapter carries a hook and projects its
body to advisory text; ``guardrails_skill`` composes the ``playbook-guardrails``
skill. Sync-time only, stdlib plus the import-light ``hook_runtime`` tables and
registry it shares with the dispatcher: ``hook_runtime`` never imports it, it
reads the compiled ``guard_config.json`` instead (§D.8).
"""
