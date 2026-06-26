"""Agent Harness core: models, leaf detection, parsing, emitting, sidecar.

This package is the shared substrate (Track H1 of PR H) for both directions of
Agent Harness support:

- the ``agent_harness`` output adapter (canonical → harness tree), and
- the ``import-harness`` importer (harness tree → canonical artifacts).

See ``specs/prH-agent-harness.md`` for the full contract. The module is
stdlib-only and air-gapped-friendly (no network, no telemetry).
"""

from __future__ import annotations
