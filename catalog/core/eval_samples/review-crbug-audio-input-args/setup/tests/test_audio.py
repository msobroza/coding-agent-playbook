from src.audio import AudioEventMaintainer, get_ffmpeg_command
from src.config import CameraConfig, CameraInput, FfmpegConfig


def _camera(**ffmpeg_options: object) -> CameraConfig:
    inputs = [
        CameraInput("/streams/porch-main.mp4", ["detect", "record"]),
        CameraInput("/streams/porch-sub.mp4", ["audio"]),
    ]
    return CameraConfig("porch", FfmpegConfig(inputs=inputs, **ffmpeg_options))  # type: ignore[arg-type]


def test_the_command_reads_the_audio_input_and_writes_raw_samples() -> None:
    cmd = AudioEventMaintainer(_camera()).ffmpeg_cmd
    assert cmd[0] == "ffmpeg"
    assert cmd[cmd.index("-i") + 1] == "/streams/porch-sub.mp4"
    assert cmd[-8:] == ["-f", "s16le", "-ar", "16000", "-ac", "1", "-y", "pipe:"]


def test_the_camera_wide_preset_is_used_by_default() -> None:
    cmd = AudioEventMaintainer(_camera()).ffmpeg_cmd
    assert "-use_wallclock_as_timestamps" in cmd


def test_the_audio_input_preset_wins_over_the_camera_wide_one() -> None:
    ffmpeg = FfmpegConfig(
        inputs=[CameraInput("/streams/porch.flv", ["audio"], input_args="preset-http-reolink")],
    )
    cmd = get_ffmpeg_command(ffmpeg)
    assert "-user_agent" in cmd
    assert "-use_wallclock_as_timestamps" not in cmd


def test_a_list_of_arguments_is_used_as_is() -> None:
    ffmpeg = FfmpegConfig(
        inputs=[CameraInput("/streams/porch-sub.mp4", ["audio"], input_args=["-rtsp_transport", "udp"])],
    )
    cmd = get_ffmpeg_command(ffmpeg)
    assert cmd[cmd.index("-rtsp_transport") + 1] == "udp"
