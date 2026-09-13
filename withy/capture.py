"""
capture.py — microphone to a Whisper-ready WAV.

16 kHz mono is Whisper's native input. Resample at capture, not later.

THE DEVICE-SELECTION TRAP, which costs everyone a day: `-i ":0"` looks correct
and is wrong. Index 0 is the first ENUMERATED device, not the system default.
On any machine with BlackHole, Loopback, Krisp or an aggregate device installed
— most developer laptops — index 0 is often a multi-channel aggregate. ffmpeg
refuses to auto-downmix an unknown high-channel layout and writes a ZERO-BYTE
WAV with exit code 0. The symptom is "dictation does nothing", with no error
anywhere. So devices are always resolved by name, and the result is verified.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from pathlib import Path

from . import config
from .log import log, set_state

_DEV_RE = re.compile(r"^\[AVFoundation.*?\]\s*\[(\d+)\]\s*(.+)$")
# Ordered preference when picking a microphone automatically. Built-in hardware
# first; virtual/aggregate devices are what the zero-byte trap is made of.
_PREFERRED = ("macbook", "built-in", "internal", "imac", "studio display")


def list_mics() -> list[str]:
    """Audio input device names, in enumeration order."""
    res = subprocess.run(
        [config.FFMPEG_BIN, "-hide_banner", "-f", "avfoundation",
         "-list_devices", "true", "-i", ""],
        capture_output=True, text=True,
    )
    names, in_audio = [], False
    for line in res.stderr.splitlines():
        if "AVFoundation audio devices" in line:
            in_audio = True
            continue
        if "AVFoundation video devices" in line:
            in_audio = False
            continue
        m = _DEV_RE.match(line.strip())
        if in_audio and m:
            names.append(m.group(2).strip())
    return names


def _pick_mic() -> str:
    """Enumerate devices and choose one. SLOW — 0.15-1.0s, because it spins up
    the whole AVFoundation stack. Never call this on the recording path."""
    mics = list_mics()
    want = str(config.settings()["mic"])
    if want and want != "default":
        for n in mics:
            if want.lower() in n.lower():
                return n
        log(f"configured mic {want!r} not found; falling back")
    for pref in _PREFERRED:
        for n in mics:
            if pref in n.lower():
                return n
    return mics[0] if mics else "default"


def resolve_mic(refresh: bool = False) -> str:
    """The device name to record from — cached, because enumerating costs up to
    a second and that second is speech the user has already started saying.

    This was measured: device enumeration on every key-press was the dominant
    part of the gap between pressing the key and audio actually being captured,
    and it is what made the first few words of a dictation disappear.
    """
    s = config.settings()
    want = str(s["mic"])
    if not refresh:
        if want and want != "default":
            return want          # ffmpeg matches the name as a substring
        cached = str(s.get("resolved_mic") or "")
        if cached:
            return cached
    name = _pick_mic()
    config.save_settings({"resolved_mic": name})
    return name


def is_recording() -> bool:
    if not config.PID_FILE.exists():
        return False
    try:
        os.kill(int(config.PID_FILE.read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def start() -> None:
    """Begin recording.

    The cancel() first is a safety net, not a feature: push-to-talk means the
    previous recorder has already been stopped by the key release, so this only
    fires when a key-up was lost and a recorder was left running. Pressing the
    key again does NOT discard a finished take — that take is already saved and
    transcribing, which is what makes back-to-back dictation work.
    """
    cancel()
    config.ensure_dirs()
    config.CURRENT_WAV.unlink(missing_ok=True)
    mic = resolve_mic()
    log(f"record start mic={mic!r}")
    proc = subprocess.Popen(
        [config.FFMPEG_BIN, "-hide_banner", "-loglevel", "error", "-nostdin",
         "-f", "avfoundation", "-i", f":{mic}",
         "-ar", "16000", "-ac", "1", "-y", str(config.CURRENT_WAV)],
        stdout=subprocess.DEVNULL,
        stderr=config.LOG_FILE.open("a"),
        start_new_session=True,
    )
    config.PID_FILE.write_text(str(proc.pid))
    set_state("recording")


def stop() -> Path | None:
    """End recording and return the WAV, or None if there is nothing usable."""
    if not config.PID_FILE.exists():
        log("stop: nothing recording")
        set_state("idle")
        return None
    try:
        pid = int(config.PID_FILE.read_text().strip())
    except ValueError:
        pid = 0
    config.PID_FILE.unlink(missing_ok=True)

    if pid:
        try:
            # SIGINT, not SIGKILL: ffmpeg must flush the WAV header. A killed
            # recorder leaves a header-less file whisper cannot read at all.
            os.kill(pid, signal.SIGINT)
            for _ in range(30):
                time.sleep(0.1)
                os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    wav = config.CURRENT_WAV
    if not wav.exists() or wav.stat().st_size == 0:
        log("stop: WAV empty — stale input device? clearing the cached mic")
        config.save_settings({"resolved_mic": ""})
        set_state("idle")
        return None

    # Keep the take: this is what makes a failed dictation retryable.
    kept = config.AUDIO_DIR / f"take-{time.strftime('%Y%m%d-%H%M%S')}.wav"
    try:
        wav.replace(kept)
    except OSError:
        kept = wav
    return kept


def cancel() -> None:
    if config.PID_FILE.exists():
        try:
            os.kill(int(config.PID_FILE.read_text().strip()), signal.SIGKILL)
        except (OSError, ValueError):
            pass
        config.PID_FILE.unlink(missing_ok=True)
    set_state("idle")


def purge_audio(keep_days: int) -> int:
    """Delete kept takes older than `keep_days`. Returns the count removed."""
    if keep_days <= 0:
        return 0
    cutoff = time.time() - keep_days * 86400
    n = 0
    for f in config.AUDIO_DIR.glob("take-*.wav"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                n += 1
        except OSError:
            pass
    return n
