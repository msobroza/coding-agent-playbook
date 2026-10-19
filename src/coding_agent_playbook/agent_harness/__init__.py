"""The Agent Harness format round trip: models, leaf detection, parsing, emitting, sidecar.

This package holds both directions of Agent Harness support:

- the ``agent_harness`` output adapter (canonical → Agent Harness tree), and
- the ``import-harness`` importer (Agent Harness tree → canonical artifacts).

Deliberately empty: import the defining module. ``models`` holds the parsed tree,
``leaf_detectors`` and ``parser`` read a tree, ``emitter`` writes one and
``manifest`` is the ``.playbook/manifest.toml`` sidecar. ``adapter`` holds the
output adapter (``AgentHarnessAdapter``), ``hook_sidecars`` writes the
``.playbook/hooks/`` sidecar, and ``importer`` holds ``import_harness``,
``write_import`` and ``ImportResult``; the private ``_best_effort``,
``_import_files`` and ``_import_hooks`` are the importer's helpers. See
``specs/prH-agent-harness.md`` for the full contract (no network, no telemetry).
"""
