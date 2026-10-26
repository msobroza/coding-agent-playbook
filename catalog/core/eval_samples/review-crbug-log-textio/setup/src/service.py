"""Start and stop a browser-driver child process, with its log sent where the caller asks."""

from __future__ import annotations

import os
import subprocess
from subprocess import PIPE
from typing import IO, Any, TextIO


class Service:
    """Runs the driver ``executable``.

    ``log_output`` is a path (opened for appending), an open file, a file
    descriptor, or ``subprocess.PIPE``; by default the log goes to os.devnull.
    """

    def __init__(self, executable: str, log_output: str | int | IO[Any] | None = None) -> None:
        self.executable = executable
        if isinstance(log_output, str):
            self.log_output: int | IO[Any] = open(log_output, "a+", encoding="utf-8")
        elif log_output is None:
            self.log_output = open(os.devnull, "wb")
        else:
            self.log_output = log_output
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        """Launch the driver, its stdout and stderr going to ``log_output``."""
        self.process = subprocess.Popen(
            [self.executable], stdout=self.log_output, stderr=self.log_output
        )

    def stop(self) -> None:
        """Stop the driver and close the log it was writing to."""
        if self.log_output != PIPE:
            if isinstance(self.log_output, TextIO):
                self.log_output.close()
            elif isinstance(self.log_output, int):
                os.close(self.log_output)

        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=10)
            self.process = None
