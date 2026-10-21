"""The two consumer config file names: their one definition outside the hook runtime (SPEC §7.1, §7.2).

``config.files`` re-exports both, and every sync-side module takes them from
there. They live in this stdlib leaf, below ``config``, because the detector
reads the committed file too: its top-level ``platforms`` key turns platform
facts on (prU D63, ``detector.platform_facts``), and the ``config`` package
sits above the detector in the layer contract, so the detector cannot import
it. The hook runtime keeps its own spellings (spec B.5.4).
"""

from __future__ import annotations

from typing import Final

__all__ = ["CONFIG_FILENAME", "CONFIG_LOCAL_FILENAME"]

#: The committed consumer config: team policy, read by every command (SPEC §7.1).
CONFIG_FILENAME: Final = ".coding-agent-playbook.toml"
#: The gitignored personal overrides, merged on top and never written back (SPEC §7.2).
CONFIG_LOCAL_FILENAME: Final = ".coding-agent-playbook.local.toml"
