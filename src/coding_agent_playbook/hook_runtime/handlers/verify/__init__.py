"""The verify pack's builtin handlers (specs/prK-hook-pack.md §E.2, §F.1, §F.2, §F.3).

One module per hook, named after its snake-cased hook id (``subagent_stop_verify``
runs subagent-stop-verify), each listed in ``dispatch.registry._BUILTIN_HANDLER_MODULES``
under the hook's registry name; ``gate_weakening_guard_edit`` is the pre-edit companion
of gate-weakening-guard. A ``_``-prefixed module is a helper only this pack imports,
and registers no handler. Importers name the modules directly, so this module is a
docstring only.
"""
