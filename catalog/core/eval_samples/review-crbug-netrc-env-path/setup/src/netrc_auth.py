"""Look up the HTTP credentials the user's netrc file holds for a host."""

import os
from netrc import NetrcParseError, netrc

NETRC_FILES = (".netrc", "_netrc")


def get_netrc_auth(host: str, raise_errors: bool = False) -> tuple[str, str] | None:
    """Return the ``(login, password)`` netrc holds for ``host``, or None."""
    netrc_file = os.environ.get("NETRC")
    netrc_locations = (netrc_file,) if netrc_file is not None else NETRC_FILES

    netrc_path = None
    for name in netrc_locations:
        try:
            loc = os.path.expanduser(f"~/{name}")
        except KeyError:
            # expanduser raises when $HOME is unset and there is no passwd entry.
            return None
        if os.path.exists(loc):
            netrc_path = loc
            break

    if netrc_path is None:
        return None

    try:
        entry = netrc(netrc_path).authenticators(host)
    except (NetrcParseError, OSError):
        if raise_errors:
            raise
        return None
    if entry is None:
        return None
    login, _account, password = entry
    return (login, password or "")
