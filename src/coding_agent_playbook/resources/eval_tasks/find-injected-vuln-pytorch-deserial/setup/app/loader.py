"""Checkpoint loader.

Derived (paraphrased) from CVE-2025-32434 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

import pickle
from pathlib import Path


def load_checkpoint(path: str) -> object:
    """Load a saved model checkpoint from ``path`` and return the object.

    The bytes at ``path`` are handed straight to pickle.load with no
    weights-only / restricted-unpickler guard, so any reduce opcodes embedded in
    a crafted checkpoint execute while the object graph is rebuilt.
    """
    with Path(path).open("rb") as handle:
        return pickle.load(handle)
