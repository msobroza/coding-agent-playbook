"""The hook dispatcher and the model it decides with (specs/prK-lifecycle-hooks.md §D.1-§D.4).

``run`` is the dispatch pipeline every hook process runs: one harness event in,
one decided output out. ``event`` holds the ``CanonicalEvent`` every harness
payload is normalized into, ``paths`` the git-free repo discovery and the
``NormalizedPath`` its fields carry, ``decision`` the ``HandlerResult`` and
``Decision`` model handlers return, ``caps`` the output caps and sanitization,
and ``policy`` the attendance and failure-policy tables. Importers name these
modules directly, so this module is a docstring only.
"""
