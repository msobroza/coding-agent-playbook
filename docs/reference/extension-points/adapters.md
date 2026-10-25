# Adapters

An adapter writes rendered content in one harness's native format and locations.
`playbook sync` runs the adapters listed in the consumer config's
`adapters_enabled`, and always `agents_md`.

The engine ships `agent_harness`, `agents_md`, `claude_code`, `continue`,
`opencode` and `shared_skills` in this group:

```toml
[project.entry-points."coding_agent_playbook.adapters"]
my_harness = "my_package.adapter:MyHarnessAdapter"
```

## The contract

```{eval-rst}
.. autoclass:: coding_agent_playbook.adapters.base.Adapter
   :members:
```
