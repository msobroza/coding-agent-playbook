# Gates

A gate is a composed boolean [check](checks.md): an `AllOf`, `AnyOf` or `Not` tree
over file, threshold and judge checks. An eval sample binds one by name in its
`[gate.bind]` table, as `<handle> = { ref = "<name>" }`. The registry holds a
factory that builds the gate when asked. The engine ships none in this group.

```toml
[project.entry-points."coding_agent_playbook.gates"]
must-touch-tests = "my_package.gates:must_touch_tests"
```

## The contract

```{eval-rst}
.. autofunction:: coding_agent_playbook.evals.compile.gate_registry.register_gate
```
