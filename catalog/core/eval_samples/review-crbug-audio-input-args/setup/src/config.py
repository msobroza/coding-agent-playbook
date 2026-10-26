"""Camera configuration: its ffmpeg inputs and their arguments.

Every ``*_args`` option is either a preset name (``preset-...``), a string of
ordinary ffmpeg arguments, or a list of arguments.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FfmpegArgs = str | list[str]


@dataclass(frozen=True)
class CameraInput:
    """One stream of the camera and the roles it serves (``detect``, ``record``, ``audio``)."""

    path: str
    roles: list[str]
    input_args: FfmpegArgs = ""


@dataclass(frozen=True)
class FfmpegConfig:
    inputs: list[CameraInput]
    global_args: FfmpegArgs = "-hide_banner -loglevel warning"
    input_args: FfmpegArgs = "preset-rtsp-generic"


@dataclass(frozen=True)
class CameraConfig:
    name: str
    ffmpeg: FfmpegConfig
    audio_listen: list[str] = field(default_factory=lambda: ["speech", "bark"])
