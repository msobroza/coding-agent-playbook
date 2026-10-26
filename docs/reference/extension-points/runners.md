# Runners

A runner invokes an agent on one eval sample and grades the result.
`playbook eval --runner <name>` picks one, and so does an eval target's `harness`
(`playbook eval --target`); without either it is `claude_code`.

The engine ships `fake` (hermetic, no agent), `claude_code` and `opencode` in this
group. A runner subclasses `HarnessRunner`, sets `name` to its entry-point key and
implements `_invoke_agent`. A runner that can drive a chosen model sets
`accepts_model = True` and takes `model=` in its constructor; a target with a model
is refused for any other runner. Likewise a runner that can reach a custom endpoint
sets `accepts_endpoint = True` and takes `route=` (today only `claude_code` does);
a target with an endpoint is refused for any other runner:

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
