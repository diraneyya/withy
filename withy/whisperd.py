"""
whisperd.py — a resident whisper.cpp server, so a take does not load the model.

Measured on this pipeline's own recordings (large-v3-turbo, M-series): each
`whisper-cli` run spends ~1.6 s loading the model before it hears anything, and
a take with language detection runs it twice. A 5 s take took 4.5 s to
transcribe; the same take on a server with the model already loaded took 0.7 s
plus 0.8 s for detection. The price is ~1.8 GB held while the server lives.

The server is started on key-down (`warm`), detached, so it outlives the
process that started it and every later take finds it ready. Anything wrong
with it — not up yet, a different model configured, a request that fails —
returns None and the caller falls back to `whisper-cli`. A dictation must never
depend on the server being healthy.

Two server quirks handled here:
  - it can join tokens with a space inside contractions ("haven 't"): always
    with `response_format=json`, and with `text` where a segment ends mid-word.
  - detection reports the language by name ("english"); the codes are in
    `language_probabilities`.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

from . import config
from .log import log

PORT = int(os.environ.get("WITHY_WHISPER_PORT", "8178"))
INFO_FILE = Path(f"/tmp/{config.APP}-whisper-server.json")
SERVER_LOG = Path(f"/tmp/{config.APP}-whisper-server.log")
_URL = f"http://127.0.0.1:{PORT}"
_SPLIT_CONTRACTION = re.compile(r"(\w)\s+['’](t|s|re|ve|ll|d|m)\b")


def _server_bin() -> str | None:
    cli = Path(config.WHISPER_BIN)
    cand = cli.with_name("whisper-server") if cli.is_absolute() else None
    if cand and cand.exists():
        return str(cand)
    for d in ("/opt/homebrew/bin", "/usr/local/bin"):
        p = Path(d) / "whisper-server"
        if p.exists():
            return str(p)
    return None


def _info() -> dict:
    try:
        return json.loads(INFO_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def _wanted(model: str) -> dict:
    return {"model": model, "vad_model": str(config.VAD_MODEL), "port": PORT}


def _ready() -> bool:
    try:
        urllib.request.urlopen(_URL + "/", timeout=0.3).read()
        return True
    except Exception:
        return False


def enabled() -> bool:
    return bool(config.settings().get("whisper_server", True)) \
        and _server_bin() is not None and config.VAD_MODEL.exists()


def warm() -> None:
    """Make sure a server for the configured model is running. Never blocks."""
    if not enabled():
        return
    model = str(config.settings()["whisper_model"])
    info = _info()
    pid = info.get("pid")
    if _alive(pid) and {k: info.get(k) for k in _wanted(model)} == _wanted(model):
        return
    if _alive(pid):
        log(f"whisper server: settings changed, restarting (pid {pid})")
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    if not Path(model).exists():
        return
    proc = subprocess.Popen(
        [_server_bin(), "-m", model, "--host", "127.0.0.1", "--port", str(PORT),
         "-mc", "0", "--vad", "-vm", str(config.VAD_MODEL)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=SERVER_LOG.open("w"), start_new_session=True,
    )
    INFO_FILE.write_text(json.dumps({"pid": proc.pid, **_wanted(model)}))
    log(f"whisper server: started pid {proc.pid} on port {PORT}")


def _usable(model: str) -> bool:
    if not enabled():
        return False
    info = _info()
    if info.get("model") != model or not _alive(info.get("pid")):
        return False
    # Just started on this key-down: loading takes ~1.5 s, less than the
    # fallback would spend loading the same model itself.
    deadline = time.monotonic() + 3.0
    while not _ready():
        if time.monotonic() > deadline or not _alive(info.get("pid")):
            return False
        time.sleep(0.05)
    return True


def _post(wav: Path, fields: dict, timeout: float) -> bytes:
    bnd = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"'
                 f"\r\n\r\n{v}\r\n").encode("utf-8")
    body += (f'--{bnd}\r\nContent-Disposition: form-data; name="file"; '
             f'filename="take.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode()
    body += wav.read_bytes() + f"\r\n--{bnd}--\r\n".encode()
    req = urllib.request.Request(
        _URL + "/inference", body,
        {"Content-Type": f"multipart/form-data; boundary={bnd}"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def detect_language(wav: Path, model: str) -> tuple[str, float] | None:
    if not _usable(model):
        return None
    try:
        d = json.loads(_post(wav, {"detect_language": "true",
                                   "response_format": "verbose_json"}, 60))
        probs = d.get("language_probabilities") or {}
        lang = max(probs, key=probs.get)
        return lang, float(probs[lang])
    except Exception as e:
        log(f"whisper server: detect failed ({e}) — using whisper-cli")
        return None


def transcribe(wav: Path, lang: str, model: str, prompt: str | None) -> str | None:
    """Raw transcript, or None to have the caller use whisper-cli instead."""
    if not _usable(model):
        return None
    fields = {"language": lang, "response_format": "text"}
    if lang == "en" and prompt:
        fields["prompt"] = prompt
    try:
        text = _post(wav, fields, 600).decode("utf-8", errors="replace")
        return _SPLIT_CONTRACTION.sub(r"\1'\2", text)
    except Exception as e:
        log(f"whisper server: transcribe failed ({e}) — using whisper-cli")
        return None
