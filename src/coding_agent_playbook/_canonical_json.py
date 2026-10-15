"""The canonical JSON bytes and hash of one managed settings element (specs/prK-lifecycle-hooks.md §B.6).

Sync records each managed element of ``.claude/settings.json`` as a scoped
lock entry whose ``sha256`` is :func:`element_sha256`; control-plane-guard
recognizes the element at run time by the same hash (specs/prK-hook-pack.md
§E.1). One function serves both, so it lives here, importable by the hook
runtime, which may not import ``adapters`` (§D.1): ``json`` and ``hashlib`` only.
``adapters._settings_plan`` re-exports :func:`canonical_json`.
"""

from __future__ import annotations

import hashlib
import json

__all__ = ["canonical_json", "element_sha256"]


def canonical_json(value: object) -> bytes:
    """The bytes a scoped lock entry hashes: sorted keys, no whitespace, UTF-8.

    Key order and the file's own formatting never change the hash (§C.1.4).

    Example::

        >>> canonical_json({"b": 1, "a": "é"})
        b'{"a":"\\xc3\\xa9","b":1}'
    """
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8", errors="surrogatepass")


def element_sha256(value: object) -> str:
    """The sha256 hex digest of :func:`canonical_json` (a scoped entry's ``sha256``).

    Example::

        >>> element_sha256([]) == hashlib.sha256(b"[]").hexdigest()
        True
    """
    return hashlib.sha256(canonical_json(value)).hexdigest()
