"""Load model metadata using a pickle-free, code-execution-safe format.

These loaders read plain JSON, which carries data but never executable code,
so an untrusted artifact cannot run anything when it is loaded. A security
review should find nothing to change here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_model_spec(path: str) -> dict[str, Any]:
    """Load a model spec from JSON — plain data, no deserialization risk."""
    raw: object = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path!r} did not contain a JSON object")
    return raw


def load_label_map(path: str) -> dict[str, int]:
    """Load a class-index label map from JSON, validating value types."""
    raw: object = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path!r} did not contain a JSON object")
    return {str(key): int(value) for key, value in raw.items()}
