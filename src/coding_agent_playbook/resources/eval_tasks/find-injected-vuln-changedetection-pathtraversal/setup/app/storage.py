"""Artifact storage: reads a stored file from the artifacts directory.

Derived (paraphrased) from CVE-2026-29065 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

_ARTIFACT_ROOT = "/var/lib/app/artifacts"


def read_artifact(name: str) -> bytes:
    """Read the artifact called ``name`` from under the artifact root.

    ``name`` is appended to the root as plain text with no normalization or
    containment check, so a value like '../../etc/passwd' resolves to a path
    outside the intended directory.
    """
    full_path = f"{_ARTIFACT_ROOT}/{name}"
    with open(full_path, "rb") as handle:
        return handle.read()
