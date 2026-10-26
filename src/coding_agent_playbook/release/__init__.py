"""Releases: what one engine release records about its catalog (#281, ADR 0012).

``graded_set`` computes the graded set (the prompts eval samples grade plus the
rules they include) in one function; ``manifest`` reads and writes
``catalog/releases/<version>/manifest.toml`` (the graded set and every shipped
artifact, with digests, plus the base commit); ``snapshot`` builds a manifest from
an artifact source; ``changes`` diffs two manifests; ``notes`` writes the
per-release ``notes.md``; ``versions`` holds the tag and bump-floor rules.
``scripts/release.py`` orchestrates git, commitizen and ``playbook forge`` around
them; evals and CI read the same modules. This module is a docstring only.
"""
