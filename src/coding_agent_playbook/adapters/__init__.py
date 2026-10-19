"""The Adapters: each writes rendered content in one Harness's native format and locations.

``base`` is the contract out-of-tree adapters implement (the entry-point group
``coding_agent_playbook.adapters`` loads them, through ``registry``); every other
module or package here is one built-in adapter or a helper the adapters share. This module is a docstring
only: import the defining module.
"""
