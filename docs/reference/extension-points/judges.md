# Judges

A judge scores rubric criteria into `0-1` scores. `playbook eval --judge <name>`
picks one; without the flag the run is deterministic only.

The engine ships `llm` in this group, which shells out to the `claude` CLI. A judge
subclasses `Judge`, sets `name` to its entry-point key and implements
`score_criterion`:

```toml
[project.entry-points."coding_agent_playbook.judges"]
my_judge = "my_package.judge:MyJudge"
```

## The contract

```{eval-rst}
.. autoclass:: coding_agent_playbook.evals.judge.Judge
   :members:
```
