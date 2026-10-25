# Metrics

A metric measures code over a scope and maps the raw value to a `0-1` goodness,
where higher is always better. The engine's own metrics register themselves with
`register_metric`; this group is for out-of-tree ones, and the engine ships none
in it.

```toml
[project.entry-points."coding_agent_playbook.metrics"]
my_metric = "my_package.metrics:MyMetric"
```

## The contract

```{eval-rst}
.. autoclass:: coding_agent_playbook.grading.metric.Metric
   :members:

.. autofunction:: coding_agent_playbook.grading.metric.register_metric
```
