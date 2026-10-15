"""The canonical JSON bytes and hash of one managed settings element (specs/prK-lifecycle-hooks.md §B.6).

Sync records each managed element of ``.claude/settings.json`` as a scoped
lock entry whose ``sha256`` is :func:`element_sha256`; control-plane-guard
recognizes the element at run time by the same hash (specs/prK-hook-pack.md
§E.1), and the drift check (``lockfile.drift_entries``) finds it at its JSON
pointer. One definition serves all three, so it lives here, importable by the
hook runtime, which may not import ``adapters`` (§D.1): ``json`` and
``hashlib`` only. ``adapters._settings_plan`` re-exports :func:`canonical_json`
and :func:`pointer_keys`.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["array_at", "canonical_json", "element_hashes", "element_sha256", "pointer_keys"]


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


def pointer_keys(pointer: str) -> tuple[str, ...]:
    """The object keys of an RFC 6901 ``pointer`` (``~1`` is ``/``, ``~0`` is ``~``).

    Example::

        >>> pointer_keys("/permissions/allow")
        ('permissions', 'allow')
    """
    return tuple(p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:])


def array_at(doc: object, pointer: str) -> Sequence[Any]:
    """The array at ``pointer`` in ``doc``, or ``()`` when a step is absent or not that shape.

    Example::

        >>> array_at({"hooks": {"Stop": [1]}}, "/hooks/Stop"), array_at({}, "/hooks/Stop")
        ([1], ())
    """
    node: Any = doc
    for key in pointer_keys(pointer):
        if not isinstance(node, dict) or key not in node:
            return ()
        node = node[key]
    return node if isinstance(node, list) else ()


def element_hashes(doc: object, pointer: str) -> list[str]:
    """:func:`element_sha256` of each element of the array at ``pointer``, in array order.

    A scoped lock entry is present when its ``sha256`` is among them (§C.2.6).

    Example::

        >>> element_hashes({"a": [[]]}, "/a") == [element_sha256([])]
        True
    """
    return [element_sha256(item) for item in array_at(doc, pointer)]
