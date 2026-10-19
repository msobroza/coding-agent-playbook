"""The engine's builtin hook handlers (specs/prK-lifecycle-hooks.md §D.3.1, §E).

Each module registers its handlers with ``dispatch.registry.register_hook_handler``
and is listed, name by name, in ``dispatch.registry._BUILTIN_HANDLER_MODULES``; the
dispatcher imports only the modules bound to the current event, never this
package as a whole. The pack tracks (K5-K10) add them, starting with K5's
``guard_generated_outputs`` and ``control_plane_guard``. A ``_``-prefixed
module is a private helper shared by handlers and registers none.
"""
