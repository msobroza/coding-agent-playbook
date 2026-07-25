"""Model registry: resolves a requested model name to a checkpoint on disk.

Derived (paraphrased) from CVE-2025-32434 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

from app.loader import load_checkpoint


def restore_model(model_name: str) -> object:
    """Restore the checkpoint for a caller-requested ``model_name``.

    ``model_name`` is attacker-influenced (it selects which uploaded artifact to
    open), and the resolved path is deserialized without any trust check on the
    file's contents.
    """
    checkpoint_path = f"checkpoints/{model_name}.pt"
    return load_checkpoint(checkpoint_path)
