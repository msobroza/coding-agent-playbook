"""The audit pack's builtin handlers (specs/prK-hook-pack.md §E.5).

One module per hook, named after its snake-cased hook id (``local_audit_log``
runs local-audit-log), each listed in ``dispatch.registry._BUILTIN_HANDLER_MODULES``
under the hook's registry name. A ``_``-prefixed module is a helper only this pack
imports, and registers no handler. Importers name the modules directly, so this
module is a docstring only.
"""
