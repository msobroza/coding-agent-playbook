# Rubrics

A named rubric is a code-defined `Rubric` subclass that declares its `CRITERIA`. An
eval sample's `sample.toml` uses it by name, as `[rubric] ref = "<name>"`, so
several samples share one rubric. The engine ships none in this group.

```toml
[project.entry-points."coding_agent_playbook.rubrics"]
code-review = "my_package.rubrics:CodeReviewRubric"
```

## The contract

```{eval-rst}
.. autoclass:: coding_agent_playbook.grading.rubric.Rubric
   :members:

.. autofunction:: coding_agent_playbook.evals.compile.rubric_registry.register_rubric
```
