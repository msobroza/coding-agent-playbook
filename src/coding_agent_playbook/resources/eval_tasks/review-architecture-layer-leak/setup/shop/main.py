"""Entry point: read one JSON order from stdin and print the response."""

import json
import sys

from shop.api import handle_place_order


def main() -> int:
    payload = json.load(sys.stdin)
    print(json.dumps(handle_place_order(payload)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
