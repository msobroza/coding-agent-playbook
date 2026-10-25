# Runners

A runner invokes an agent on one eval sample and grades the result.
`playbook eval --runner <name>` picks one; without the flag it is `claude_code`.

The engine ships `fake` (hermetic, no agent), `claude_code` and `opencode` in this
group. A runner subclasses `HarnessRunner`, sets `name` to its entry-point key and
implements `_invoke_agent`:

```toml
[project.entry-points."coding_agent_playbook.runners"]
my_agent = "my_package.runner:MyAgentRunner"
```

## The contract

```{eval-rst}
.. autoclass:: coding_agent_playbook.evals.run.harness_runner.HarnessRunner
   :members:
   :private-members: _invoke_agent
```
