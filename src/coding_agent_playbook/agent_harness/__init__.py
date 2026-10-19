"""The Agent Harness format round trip: models, leaf detection, parsing, emitting, sidecar.

This package holds both directions of Agent Harness support:

- the ``agent_harness`` output adapter (canonical → Agent Harness tree), and
- the ``import-harness`` importer (Agent Harness tree → canonical artifacts).

Deliberately empty: import the defining module. ``models`` holds the parsed tree
(``HarnessTree``), ``leaf_detectors`` and ``parser`` read a tree, ``emitter`` builds
one's files and ``manifest`` is the ``.playbook/manifest.toml`` sidecar. ``adapter``
holds the output adapter (``AgentHarnessAdapter``; the private ``_emit_skills``
writes its skill-shaped leaves), ``hook_sidecars`` writes and reads the
``.playbook/hooks/`` sidecar, ``importer`` holds ``import_harness``,
``write_import`` and ``ImportResult`` (the private ``_lossless``, ``_best_effort``
and ``_import_writes`` are its tiers and its file side), and ``lint`` holds the
``validate-harness`` checks (``lint_harness``, ``HarnessFindings``). See
``specs/prH-agent-harness.md`` for the full contract (no network, no telemetry).
"""
