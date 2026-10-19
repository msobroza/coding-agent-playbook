"""The Agent Harness format round trip: models, leaf detection, parsing, emitting, sidecar.

This package is the shared substrate (Track H1 of PR H) for both directions of
Agent Harness support:

- the ``agent_harness`` output adapter (canonical → Agent Harness tree), and
- the ``import-harness`` importer (Agent Harness tree → canonical artifacts).

Deliberately empty: import the defining module. ``models`` holds the parsed tree,
``leaf_detectors`` and ``parser`` read a tree, ``emitter`` writes one and
``manifest`` is the ``.playbook/manifest.toml`` sidecar. See
``specs/prH-agent-harness.md`` for the full contract (no network, no telemetry).
"""
