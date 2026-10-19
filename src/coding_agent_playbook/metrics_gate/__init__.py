"""The metrics gate: ``playbook metrics`` and the Stop-stage metrics call (SPEC §21.5).

Deliberately empty: import the defining module. ``run`` is the gate itself
(``run_metrics_gate``, its request, deps and result), ``config`` the ``[metrics]``
table and ``MetricConfig``, ``policy`` the metric defaults and selection, ``inputs``
and ``suite`` the file and test-suite measurement the Stop handlers share, and
``snapshot`` the measurement snapshot. The gate grades through the grading kernel
(``evaluators``), which never imports it back.
"""
