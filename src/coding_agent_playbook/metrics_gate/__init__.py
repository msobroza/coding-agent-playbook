"""The metrics gate: ``playbook metrics`` and the Stop-stage metrics call (SPEC §21.5).

Deliberately empty: import the defining module. ``run`` is the gate itself
(``run_metrics_gate``, its request, deps and result), ``config`` the ``[metrics]``
table and ``MetricConfig``, ``policy`` the metric defaults and selection, ``inputs``
the targets and the static baseline, ``suite`` the test-suite runs, and ``snapshot``
the measurement snapshot. The gate measures and grades through the grading kernel
(``grading.measuring`` is the measuring pass), which never imports it back.
"""
