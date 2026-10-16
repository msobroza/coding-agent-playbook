"""Opt-in content packs bundled inside the engine wheel (SPEC §11.5).

A pack's content lives in ``content/plugins/<name>/`` (``rules/``, ``prompts/``,
``skills/``) and is layered exactly like an overlay package, but ships in this
distribution — enabling one needs no extra install. Packs are **off by
default**: a consumer opts in by listing the pack's dotted package name in
``overlays_enabled`` of ``.coding-agent-playbook.toml``.

Example::

    overlays_enabled = ["coding_agent_playbook.packs.superpowers"]
"""
