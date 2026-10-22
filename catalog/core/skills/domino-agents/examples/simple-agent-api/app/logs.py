"""One JSON line per log record on stdout, the App's and the Jobs' log stream.

configure_logging is called by each entry point (app/asgi.py and the two
evaluation Jobs), never at import. Modules log through logging.getLogger(__name__)
with named fields in ``extra=``; nothing logs a token, a key or a header, and
prompts and answers stay in the trace instead of the logs.
"""

import json
import logging
import sys

#: Attributes every LogRecord has; anything else on a record came from ``extra=``.
_RECORD_ATTRIBUTES = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonLinesFormatter(logging.Formatter):
    """Format a record as one JSON object: time, level, logger, message, extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(
            (key, value) for key, value in vars(record).items() if key not in _RECORD_ATTRIBUTES
        )
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class StdoutHandler(logging.Handler):
    """Writes each record to the current sys.stdout, looked up at emit time."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stdout.write(self.format(record) + "\n")
            sys.stdout.flush()
        except Exception:
            self.handleError(record)


def configure_logging(level: str) -> None:
    """Send every record at ``level`` and above to stdout as JSON lines.

    Calling it again replaces the handler it installed before and keeps any other.
    """
    handler = StdoutHandler()
    handler.setFormatter(JsonLinesFormatter())
    root = logging.getLogger()
    for previous in [h for h in root.handlers if isinstance(h, StdoutHandler)]:
        root.removeHandler(previous)
    root.addHandler(handler)
    root.setLevel(level)
