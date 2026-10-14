"""Opt-in content packs bundled inside the engine wheel (SPEC §11.5).

A pack is an importable subpackage whose ``resources/`` tree (``rules/``,
``prompts/``, ``skills/``) is layered exactly like an overlay package, but ships
in this distribution — enabling one needs no extra install. Packs are **off by
default**: a consumer opts in by listing the pack's dotted package name in
``overlays_enabled`` of ``.coding-agent-playbook.toml``.

Example::

    overlays_enabled = ["coding_agent_playbook.packs.superpowers"]
"""
