"""Download view: serves a stored artifact chosen by the request.

Derived (paraphrased) from CVE-2026-29065 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

from app.storage import read_artifact


def download(request: dict[str, str]) -> bytes:
    """Return the bytes of the artifact named in ``request['filename']``.

    ``request['filename']`` is taken directly from the incoming request and
    passed to storage without stripping directory components, so the caller
    controls exactly which path is opened.
    """
    filename = request["filename"]
    return read_artifact(filename)
