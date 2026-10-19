"""Helpers that handlers of more than one pack import; none registers a handler.

``targets`` holds the paths a tool call writes, ``edit_preview`` what a file-tool
call would leave in its file, ``control_plane_paths`` which control-plane row a
path falls under, ``pii_settings`` the ``pii`` key of the hooks that only observe
PII, and ``ruff_pipeline`` the one ruff diagnostics call per edited file. The
package is private to ``handlers``; its modules carry no ``_`` prefix because the
package name already does. Importers name the modules directly, so this module is
a docstring only.
"""
