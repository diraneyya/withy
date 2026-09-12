"""
speech.py — is there actually anyone talking in this recording?

Whisper hallucinates on silence. Fed 0.6 seconds of room tone it confidently
returns "Thank you." — and a dictation tool that types "Thank you." when you
said nothing is worse than one that does nothing at all.

WHY NOT A LOUDNESS THRESHOLD
An absolute dB gate only works at the noise floor it was tuned for. The same
number that correctly rejects silence in a quiet room rejects real speech in a
garden, and passes a fan in an office. The noise floor is not a constant, so it
cannot be in the test.

WHAT ACTUALLY SEPARATES SPEECH FROM NOISE
Speech is amplitude-modulated at the syllable rate — roughly 2-8 Hz of loud
bursts separated by real gaps (stops, pauses between words). Steady sound is
not: a fan, traffic, air conditioning and room tone all hold a near-constant
level. So the discriminator is the SPREAD between loud frames and quiet frames,
which is a ratio and therefore independent of where the floor sits.

Measured on real dictations from this machine:

    real speech (13 takes)          spread 16.2 - 35.9 dB
    "Thank you." on silence (2)     spread 10.3 and 10.5 dB

The default threshold sits at 13 dB, between the two groups.

CAVEAT, stated because it matters: that is thirteen positive samples and only
TWO negative ones. The threshold is therefore deliberately conservative — when
in doubt it transcribes, because typing nothing when you spoke is a worse
failure than typing something when you did not. Every measurement is logged,
so the threshold can be retuned against real data rather than re-guessed.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import config
from .log import log

# 30 ms windows at 16 kHz — roughly a phoneme, short enough to see the gaps
# between syllables and long enough not to be dominated by a single pitch pulse.
_WINDOW_SAMPLES = 480
_RMS_RE = re.compile(r"lavfi\.astats\.Overall\.RMS_level=(-?[\d.]+|-inf)")


def frame_levels(wav: Path) -> list[float]:
    """Per-window RMS in dBFS. The DSP is done by ffmpeg, so this module needs
    no numpy and no audio library."""
    res = subprocess.run(
        [config.FFMPEG_BIN, "-hide_banner", "-v", "error", "-i", str(wav),
         "-af", f"asetnsamples={_WINDOW_SAMPLES},astats=metadata=1:reset=1,"
                "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=60,
    )
    out = []
    for m in _RMS_RE.finditer(res.stdout):
        v = m.group(1)
        out.append(-120.0 if v == "-inf" else float(v))
    return out


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, int(round(p / 100.0 * (len(xs) - 1)))))
    return xs[i]


def modulation_spread(wav: Path) -> float | None:
    """dB between the loud frames (p95) and the quiet ones (p20).

    p95 rather than the maximum so one door slam cannot carry the decision, and
    p20 rather than the minimum so one digital-silence frame cannot either.
    """
    levels = frame_levels(wav)
    if len(levels) < 4:
        return None
    return _percentile(levels, 95) - _percentile(levels, 20)


def has_speech(wav: Path) -> tuple[bool, float | None]:
    """(is anyone talking, measured spread). Unmeasurable audio passes."""
    threshold = float(config.settings().get("speech_spread_db", 13.0))
    spread = modulation_spread(wav)
    if spread is None:
        log("speech: could not measure modulation — transcribing anyway")
        return True, None
    ok = spread >= threshold
    log(f"speech: modulation spread {spread:.1f} dB "
        f"(threshold {threshold:.1f}) -> {'speech' if ok else 'NO SPEECH'}")
    return ok, spread
