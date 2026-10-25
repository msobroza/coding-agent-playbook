# Checks

A check grades one thing, a metric against a threshold or a file that must exist,
on the `Metric`, `Check`, `Rubric` stack. The registry holds factories keyed by id
prefix: a function that returns a `Check`, or a `Check` subclass. The engine's own
checks are built in; this group is for new grading strategies, and the engine ships
none in it.

```toml
[project.entry-points."coding_agent_playbook.checks"]
my_check = "my_package.checks:make_my_check"
```

## The contract

```{eval-rst}
.. autoclass:: coding_agent_playbook.grading.check.Check
   :members:

.. autofunction:: coding_agent_playbook.grading.check_registry.register_check
```
