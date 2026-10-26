"""Listen to a camera's audio stream: the ffmpeg command that decodes it to raw samples."""

from __future__ import annotations

from src.config import CameraConfig, CameraInput, FfmpegConfig
from src.ffmpeg_presets import get_ffmpeg_arg_list, parse_preset_input

AUDIO_FORMAT = "s16le"
AUDIO_SAMPLE_RATE = 16000


def get_ffmpeg_command(ffmpeg: FfmpegConfig) -> list[str]:
    """ffmpeg reading the camera's audio input and writing mono 16 kHz samples to stdout."""
    ffmpeg_input: CameraInput = [i for i in ffmpeg.inputs if "audio" in i.roles][0]
    input_args = get_ffmpeg_arg_list(ffmpeg.global_args) + (
        parse_preset_input(ffmpeg_input.input_args, 1)
        or ffmpeg_input.input_args
        or parse_preset_input(ffmpeg.input_args, 1)
        or ffmpeg.input_args
    )
    return (
        ["ffmpeg", "-vn"]
        + input_args
        + ["-i", ffmpeg_input.path]
        + ["-f", AUDIO_FORMAT, "-ar", str(AUDIO_SAMPLE_RATE), "-ac", "1", "-y", "pipe:"]
    )


class AudioEventMaintainer:
    """Decodes one camera's audio stream and reports the sounds it hears."""

    def __init__(self, camera: CameraConfig) -> None:
        self.camera = camera
        self.ffmpeg_cmd = get_ffmpeg_command(camera.ffmpeg)
