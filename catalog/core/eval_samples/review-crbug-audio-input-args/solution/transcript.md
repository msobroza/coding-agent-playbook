**Correctness**

- `src/audio.py:17` - important - when `input_args` is a string of ordinary ffmpeg arguments rather than a preset name, `parse_preset_input()` returns `None` and the fallback `ffmpeg_input.input_args` (or `ffmpeg.input_args` on line 19) is the raw string: `get_ffmpeg_arg_list(ffmpeg.global_args) + "-rtsp_transport tcp"` raises `TypeError: can only concatenate list (not "str") to list`, so audio detection never starts for such a camera. Wrap both fallbacks in `get_ffmpeg_arg_list()` as the global args are.

**Tests**

- `tests/test_audio.py:34` - nit - the tests cover presets and a list of arguments but not a plain string, the config's most common form.

Findings: 1 important, 1 nit, 0 pre-existing

request changes
