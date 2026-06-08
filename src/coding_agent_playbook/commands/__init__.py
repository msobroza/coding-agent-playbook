"""Per-subcommand modules for the ``playbook`` CLI.

The ``cli.py`` dispatcher imports each module and binds its ``run`` function
as the subparser's ``func``. Splitting per-command keeps the argparse glue in
``cli.py`` slim and each command's logic colocated with its tests.
"""
