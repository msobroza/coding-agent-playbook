"""Background maintenance jobs for mailbox storage.

Derived (paraphrased) from CVE-2026-27602 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

from app.sysutils import exec_cmd


def relocate_mailbox(operation: dict[str, str]) -> int:
    """Move a user's mailbox directory to a new on-disk location.

    ``operation['argument']`` and ``operation['full_address']`` arrive straight
    from the account-administration request payload and are not sanitized here.
    """
    old_path = operation["argument"]
    full_address = operation["full_address"]
    new_path = f"/var/vmail/{full_address}"
    returncode, _out, _err = exec_cmd(f"mv {old_path} {new_path}")
    return returncode


def create_mailbox(full_address: str) -> int:
    """Provision the on-disk maildir for a newly created address."""
    target = f"/var/vmail/{full_address}"
    returncode, _out, _err = exec_cmd(f"maildirmake {target}")
    return returncode
