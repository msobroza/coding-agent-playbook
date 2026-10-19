"""The engine's builtin hook handlers (specs/prK-lifecycle-hooks.md §D.3.1, §E).

Each module registers its handlers with ``dispatch.registry.register_hook_handler``
and is listed, name by name, in ``dispatch.registry._BUILTIN_HANDLER_MODULES``; the
dispatcher imports only the modules bound to the current event, never this
package as a whole. The pack tracks (K5-K10) add them, starting with K5's
``guard_generated_outputs`` and ``control_plane_guard``. A pack package
(``audit``, ``safety``, ``verify``) holds one module per hook, named after its
hook id; ``_shared`` holds the helpers more than one pack imports. A ``_``-prefixed module, or any
module under ``_shared``, is a private helper and registers none.
"""
