"""The Renderer: artifact bodies through the Jinja sandbox, then into each harness's format.

``jinja`` is the sandboxed environment, ``formats`` the per-format
post-processing, ``rule_registry`` the registry a prompt reaches its included
rules through, and ``prompt_rule_delivery`` how ``includes_rules`` becomes
prompt text. The package sits below ``adapters`` and never imports the sync
context (specs/prT-package-layout.md section 9 AC.3).
"""
