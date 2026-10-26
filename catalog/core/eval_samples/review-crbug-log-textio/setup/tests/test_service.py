import os
from subprocess import PIPE

import pytest

from src.service import Service


def test_stop_without_start_is_harmless() -> None:
    Service("chromedriver", log_output=PIPE).stop()


def test_a_file_descriptor_is_kept_as_the_log() -> None:
    read_end, write_end = os.pipe()
    try:
        assert Service("chromedriver", log_output=write_end).log_output == write_end
    finally:
        os.close(read_end)
        os.close(write_end)


def test_stop_closes_a_file_descriptor_log() -> None:
    read_end, write_end = os.pipe()
    Service("chromedriver", log_output=write_end).stop()
    os.close(read_end)
    with pytest.raises(OSError):
        os.close(write_end)
