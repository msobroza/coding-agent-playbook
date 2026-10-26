**Correctness**

- `src/audio.py:17` - important - a non-preset string like "-rtsp_transport tcp" is added to a list as a str, which raises TypeError; split it with get_ffmpeg_arg_list first.
