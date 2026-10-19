"""Per-subcommand modules for the ``playbook`` CLI.

The ``cli`` package's parser (``cli/parser.py``) imports each module and binds
its ``run`` function as the subparser's ``func``. Splitting per-command keeps the
argparse glue slim and each command's logic colocated with its tests.
"""
