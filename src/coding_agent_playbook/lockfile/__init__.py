"""The Lockfile: the record of every generated output sync wrote, with its source and hash (SPEC §14.4).

``model`` holds the dataclasses and their TOML shape, ``drift`` the one definition
of drift against them, and ``canonical_json`` the hash of a managed settings
element. The package imports only the standard library (no jinja2, no yaml): the
hook runtime loads it on its briefing, drift and control-plane branches. This
module is a docstring only.
"""
