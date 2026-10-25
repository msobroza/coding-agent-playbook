# Hook handlers

A hook handler is the code an assistant lifecycle hook runs. The engine's handlers
are built in; this group is for out-of-tree ones, such as an overlay's. A hook
names its handler in its `HOOK.md` frontmatter (`handler: builtin: <name>`), and
the entry point must be a function decorated with `register_hook_handler`.

`playbook sync` resolves the entry point and records it in the hook config, so the
hook runtime never scans entry points. The handler runs only when its package is
listed in `[hooks] allow_code_from` (see [Trust](../../hooks.md#trust)).

```toml
[project.entry-points."coding_agent_playbook.hook_handlers"]
acme_guard = "acme_playbook.handlers:acme_guard"
```

## The contract

```{eval-rst}
.. autofunction:: coding_agent_playbook.hook_runtime.dispatch.registry.register_hook_handler

.. autoclass:: coding_agent_playbook.hook_runtime.dispatch.registry.HandlerContext
```
