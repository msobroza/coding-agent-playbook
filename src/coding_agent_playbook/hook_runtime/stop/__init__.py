"""The Stop coordinator's engine (specs/prK-lifecycle-hooks.md §D.5).

``stages`` is the stage contract every Stop-stage hook implements (K2);
``coordinator`` the policy stop-ci-parity-gate owns (fingerprint skip, block
budget, execution trust), ``chain`` its stop-chain and last-green state,
``output`` the one combined reason and the user notes, and ``runner`` the one
way a stage runs a pinned tool (K6).
"""
