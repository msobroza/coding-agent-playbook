"""Named ffmpeg argument presets, and turning any ``*_args`` value into an argument list."""

from __future__ import annotations

import shlex

from src.config import FfmpegArgs

PRESETS_INPUT: dict[str, list[str]] = {
    "preset-rtsp-generic": ["-rtsp_transport", "tcp", "-timeout", "5000000", "-use_wallclock_as_timestamps", "1"],
    "preset-rtsp-audio-only": ["-rtsp_transport", "tcp", "-timeout", "5000000", "-vn"],
    "preset-http-reolink": ["-user_agent", "FFmpeg Frigate", "-avoid_negative_ts", "make_zero"],
}


def parse_preset_input(arg: FfmpegArgs, detect_fps: int) -> list[str] | None:
    """The argument list the preset ``arg`` names, or None when ``arg`` is not a preset name."""
    if not isinstance(arg, str) or arg not in PRESETS_INPUT:
        return None
    if arg == "preset-http-reolink":
        return [*PRESETS_INPUT[arg], "-r", str(detect_fps)]
    return list(PRESETS_INPUT[arg])


def get_ffmpeg_arg_list(arg: FfmpegArgs) -> list[str]:
    """``arg`` as an argument list: a string is split like a shell would, a list is kept."""
    return arg if isinstance(arg, list) else shlex.split(arg)
