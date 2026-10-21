"""Model update: applies a request payload onto a domain object.

Derived (paraphrased) from CVE-2025-58367 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

from app.merge import set_path


class Profile:
    def __init__(self) -> None:
        self.display_name = ""
        self.email = ""


def update_from_request(profile: Profile, payload: dict[str, object]) -> Profile:
    """Apply an untrusted ``payload`` of {dotted_path: value} onto ``profile``.

    Both the keys (attribute paths) and the values come from the request body.
    Every key is forwarded to the deep setter without restricting it to the
    model's own declared fields, so the caller decides which attribute is set.
    """
    for path, value in payload.items():
        set_path(profile, path, value)
    return profile
