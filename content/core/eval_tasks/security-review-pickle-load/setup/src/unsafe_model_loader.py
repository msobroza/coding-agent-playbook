"""Load trained model artifacts pulled from the shared model registry.

The artifacts and the message-queue payloads below originate outside this
service, so deserializing them with pickle executes whatever code the producer
embedded — a remote-code-execution hole.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any


def load_model(path: str) -> Any:
    """Load a model object pickled by an upstream training job."""
    with Path(path).open("rb") as f:
        return pickle.load(f)


def load_model_from_message(blob: bytes) -> Any:
    """Deserialize a model received over the inference message queue."""
    return pickle.loads(blob)
