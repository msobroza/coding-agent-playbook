"""Generated output: the files the engine writes and owns in a consumer repo (L10).

``sentinel`` holds the marker every generated file carries, ``file_identity`` the
spelling-proof file set, ``atomic_io`` and ``output_io`` the writes, ``symlinks``
the link predicates and ``gitignore`` the managed ``.gitignore`` block. The hook
runtime loads ``sentinel`` and ``atomic_io`` on its hot path, so this module is a
docstring only.
"""
