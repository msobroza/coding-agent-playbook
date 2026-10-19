"""Parsers of the config tables ``Config`` does not own: ``[hooks]``, ``[guardrails]``, ``[links]``.

Deliberately empty: ``tables.hooks`` and ``tables.links`` are imported directly, and
``tables.hooks`` stays stdlib-only for the hook policy's light import.
"""
