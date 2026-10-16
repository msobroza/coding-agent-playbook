"""Engine security primitives shared by sync, the detector and the hook runtime.

Deliberately empty: every submodule is stdlib-only and imported directly
(``security.patterns``, ``security.paths``), so loading one never drags in the
others. The hook dispatcher imports from this package on its hot path
(specs/prK-lifecycle-hooks.md §D.1).
"""
