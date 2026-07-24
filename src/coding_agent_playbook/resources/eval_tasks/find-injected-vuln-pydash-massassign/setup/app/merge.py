"""Deep object setter: assigns a value at a dotted attribute path.

Derived (paraphrased) from CVE-2025-58367 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations


def set_path(obj: object, path: str, value: object) -> None:
    """Walk ``path`` (dot-separated) from ``obj`` and set the final attribute.

    Each segment is resolved with getattr and the last is written with setattr.
    No segment is checked against a denylist, so this unrestricted attribute-path
    walk can pollute arbitrary object and class attributes -- reaching internals
    such as ``__class__`` -- and overwrite attributes that were never meant to be
    writable through this API.
    """
    target = obj
    segments = path.split(".")
    for segment in segments[:-1]:
        target = getattr(target, segment)
    setattr(target, segments[-1], value)
