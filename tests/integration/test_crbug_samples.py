"""Invariants over the review/crbug-* samples, paraphrased from CRBugBench bugs.

Each sample ships a small fixture with a change (``CHANGE.diff``) already applied,
and its rubric names the one bug that change introduces. A fixture that drifts
from its rubric grades every reviewer wrong (review/spot-the-bug once described
an off-by-one its code did not have), so this module proves, per sample:

- the planted bug reproduces on the shipped ``setup/`` tree;
- it stops reproducing once the known fix is applied, so the reproduction
  exercises exactly that bug and not something else in the fixture;
- the user's request (``prompt_args``) does not name the bug.

Each reproduction runs in a fresh interpreter on a copy of ``setup/`` (every
fixture is a top-level ``src`` package, so they cannot share one process) and
prints ``BUG`` or ``OK``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.task_registry import load_layer_samples, load_task_sample
from tests._catalog import CORE_ROOT

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SAMPLES_ROOT = CORE_ROOT / "eval_samples"
_PREFIX = "review/crbug-"


@dataclass(frozen=True)
class Planted:
    """One sample's planted bug: how to show it, how the fix reads, which words would leak it."""

    sample_id: str
    module: str  # setup-relative path the fix edits
    fix: tuple[tuple[str, str], ...]  # (old, new) replacements, each must match
    probe: str  # Python that prints BUG or OK
    leaks: tuple[str, ...]  # words the request must not contain (lowercase)


PLANTED = (
    Planted(
        "review/crbug-netrc-env-path",
        "src/netrc_auth.py",
        (
            (
                'loc = os.path.expanduser(f"~/{name}")',
                'loc = os.path.expanduser(name if netrc_file is not None else f"~/{name}")',
            ),
        ),
        """
import os, pathlib, tempfile
netrc = pathlib.Path(tempfile.mkdtemp(), "netrc")
netrc.write_text("machine example.com login alice password s3cret\\n")
os.environ["HOME"] = tempfile.mkdtemp()
os.environ["NETRC"] = str(netrc)
from src.netrc_auth import get_netrc_auth
print("OK" if get_netrc_auth("example.com") == ("alice", "s3cret") else "BUG")
""",
        ("expanduser", "absolute", "home directory", "relative"),
    ),
    Planted(
        "review/crbug-basic-auth-not",
        "src/auth.py",
        (
            ("(!hmac.compare_digest(given.username", "(not hmac.compare_digest(given.username"),
            ("!hmac.compare_digest(given.password", "not hmac.compare_digest(given.password"),
        ),
        """
try:
    from src.auth import Credentials, is_authorized
except SyntaxError:
    print("BUG")
else:
    admin = Credentials("admin", "pw")
    ok = is_authorized(Credentials("admin", "pw"), admin) and not is_authorized(Credentials("admin", "x"), admin)
    print("OK" if ok else "BUG")
""",
        ("syntax", "!", "operator", "negat"),
    ),
    Planted(
        "review/crbug-xtrim-maxlen-minid",
        "src/streams.py",
        (
            (
                "        pieces: list[Any] = []\n",
                "        if (maxlen is None) == (minid is None):\n"
                '            raise ValueError("pass exactly one of maxlen and minid")\n'
                "        pieces: list[Any] = []\n",
            ),
        ),
        """
from src.streams import StreamCommands
sent = []
streams = StreamCommands(lambda *args: sent.append(args))
try:
    streams.xtrim("events", maxlen=10, minid="1-0")
except ValueError:
    print("OK")
else:
    print("BUG")
""",
        ("exclusive", "both", "dataerror", "neither", "at most one"),
    ),
    Planted(
        "review/crbug-replace-same-object",
        "src/scene.py",
        (
            (
                "            if new_m in mobj_list:",
                "            if new_m is not old_m and new_m in mobj_list:",
            ),
        ),
        """
from src.scene import Mobject, Scene
scene, circle = Scene(), Mobject("circle")
scene.add(circle)
try:
    scene.replace(circle, circle)
except ValueError:
    print("BUG")
else:
    print("OK" if scene.mobjects == [circle] else "BUG")
""",
        ("itself", "same object", "identity", "with the same"),
    ),
    Planted(
        "review/crbug-form-method-none",
        "src/forms.py",
        (
            (
                'method = kwargs.pop("method", form.method).upper()',
                'method = (kwargs.pop("method", None) or form.method).upper()',
            ),
        ),
        """
from src.forms import Form, FormRequest
try:
    FormRequest.from_form(Form("/login", "post"), method=None)
except AttributeError:
    print("BUG")
else:
    print("OK")
""",
        ("none", "null", "backward", "compatib"),
    ),
    Planted(
        "review/crbug-ftp-active-string",
        "src/feedstorage.py",
        (
            (
                'active=settings["FEED_STORAGE_FTP_ACTIVE"] or False',
                'active=settings.getbool("FEED_STORAGE_FTP_ACTIVE")',
            ),
        ),
        """
from src.feedstorage import FTPFeedStorage
from src.settings import Settings
settings = Settings.from_command_line(["FEED_STORAGE_FTP_ACTIVE=False"])
storage = FTPFeedStorage.from_settings(settings, "ftp.example.com", "/feeds/items.json")
print("BUG" if storage.active else "OK")
""",
        ("getbool", "string", "truthy", "=false", "bool"),
    ),
    Planted(
        "review/crbug-log-textio",
        "src/service.py",
        (
            ("import os\n", "import io\nimport os\n"),
            ("isinstance(self.log_output, TextIO)", "isinstance(self.log_output, io.IOBase)"),
        ),
        """
import pathlib, tempfile, warnings
warnings.simplefilter("ignore", ResourceWarning)
from src.service import Service
service = Service("chromedriver", log_output=str(pathlib.Path(tempfile.mkdtemp(), "driver.log")))
log = service.log_output
service.stop()
print("OK" if log.closed else "BUG")
""",
        ("textio", "iobase", "isinstance", "typing"),
    ),
    Planted(
        "review/crbug-audio-input-args",
        "src/audio.py",
        (
            (
                "        or ffmpeg_input.input_args\n",
                "        or get_ffmpeg_arg_list(ffmpeg_input.input_args)\n",
            ),
            (
                "        or ffmpeg.input_args\n",
                "        or get_ffmpeg_arg_list(ffmpeg.input_args)\n",
            ),
        ),
        """
from src.audio import get_ffmpeg_command
from src.config import CameraInput, FfmpegConfig
camera_input = CameraInput("/streams/porch-sub.mp4", ["audio"], input_args="-rtsp_transport tcp")
try:
    cmd = get_ffmpeg_command(FfmpegConfig(inputs=[camera_input]))
except TypeError:
    print("BUG")
else:
    print("OK" if cmd[cmd.index("-rtsp_transport") + 1] == "tcp" else "BUG")
""",
        ("typeerror", "concatenat", "get_ffmpeg_arg_list", "split"),
    ),
)

_BY_ID = {planted.sample_id: planted for planted in PLANTED}


def _copy_setup(sample_id: str, tmp_path: Path) -> Path:
    tree = tmp_path / sample_id
    shutil.copytree(_SAMPLES_ROOT / sample_id / "setup", tree)
    return tree


def _probe(planted: Planted, tree: Path) -> str:
    """Run ``planted.probe`` in a fresh interpreter rooted at ``tree``; ``BUG`` or ``OK``."""
    done = subprocess.run(
        [sys.executable, "-B", "-c", planted.probe],
        cwd=tree,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    lines = done.stdout.split()
    assert lines, f"{planted.sample_id}: probe printed nothing; stderr:\n{done.stderr}"
    return lines[-1]


def _apply_fix(planted: Planted, tree: Path) -> None:
    module = tree / planted.module
    source = module.read_text(encoding="utf-8")
    for old, new in planted.fix:
        assert old in source, f"{planted.sample_id}: fix anchor {old!r} not in {planted.module}"
        source = source.replace(old, new)
    module.write_text(source, encoding="utf-8")


def test_every_crbug_sample_has_a_planted_bug() -> None:
    samples = load_layer_samples(_SAMPLES_ROOT, "coding_agent_playbook")
    shipped = sorted(s.id for s in samples if s.id.startswith(_PREFIX))
    assert shipped == sorted(_BY_ID), "add the sample's planted bug to PLANTED (or remove it)"


@pytest.mark.parametrize("planted", PLANTED, ids=lambda p: p.sample_id)
def test_the_bug_reproduces_on_the_shipped_setup(planted: Planted, tmp_path: Path) -> None:
    assert _probe(planted, _copy_setup(planted.sample_id, tmp_path)) == "BUG"


@pytest.mark.parametrize("planted", PLANTED, ids=lambda p: p.sample_id)
def test_the_known_fix_removes_the_bug(planted: Planted, tmp_path: Path) -> None:
    tree = _copy_setup(planted.sample_id, tmp_path)
    _apply_fix(planted, tree)
    assert _probe(planted, tree) == "OK"


@pytest.mark.parametrize("planted", PLANTED, ids=lambda p: p.sample_id)
def test_the_request_does_not_name_the_bug(planted: Planted) -> None:
    sample = load_task_sample(
        _SAMPLES_ROOT / planted.sample_id, source_package="coding_agent_playbook"
    )
    request = sample.invocation.prompt_args.lower()
    leaked = [word for word in planted.leaks if word in request]
    assert not leaked, f"{planted.sample_id}: prompt_args gives the bug away with {leaked}"
