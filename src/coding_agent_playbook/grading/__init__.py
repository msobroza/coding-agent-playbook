"""The grading kernel: measure, grade and aggregate over a scope (SPEC §21).

A rubric criterion, a code metric, a coverage number and a test-pass rate are all
a *graded measurement over a scope*. Deliberately empty: import the defining
module. ``metric`` is the "measure" layer (``Metric`` and the metric registry),
``check`` the "grade" layer (``Check``, ``ThresholdCheck``, ``NonRegressionCheck``)
with its registry in ``check_registry``, and ``rubric`` the "aggregate" layer
(``Rubric``), which runs its checks through ``scheduler``. ``compose``, ``judged``,
``judge_metric`` and ``execution_checks`` hold the kernel's other checks, and
``static_metrics/`` and ``execution_metrics/`` the in-tree metrics. Eval tasks and
the metrics gate both measure through ``measuring`` (the one measuring pass) and
grade through this kernel, which imports neither.
"""
