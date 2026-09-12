"""
cli.py — the command surface.

Withy is a menubar application; a user never needs to type any of this.
It exists because the Hammerspoon front-end drives it, the installer verifies
itself with it, and every part of the pipeline has to be testable without a
microphone or a hotkey.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import time
import time
from pathlib import Path

from . import capture, config, correct, format as fmt, history, inject, pipeline, vocab
from .log import log


def _emit(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def cmd_start(a) -> int:
    capture.start()
    return 0


def cmd_stop(a) -> int:
    rec = pipeline.stop_and_process()
    if a.json:
        _emit({"ok": bool(rec), "final": rec.get("final", "")})
    return 0


def cmd_cancel(a) -> int:
    capture.cancel()
    return 0


def cmd_run(a) -> int:
    """Process a WAV, or a literal string, without recording."""
    if a.text is not None:
        terms = vocab.load()
        corrected, meta = correct.clean(a.text, terms,
                                        disfluency=not config.settings()["postprocess"])
        final, fmeta = fmt.format_text(corrected, terms)
        if a.dry:
            print(final)
        else:
            history.append(a.text, corrected, final, {"format": fmeta})
            inject.inject(final)
        return 0
    rec = pipeline.process(Path(a.wav).expanduser(), type_it=not a.dry)
    if a.dry and rec:
        print(rec["final"])
    return 0 if rec else 1


def cmd_history(a) -> int:
    recs = history.recent(a.limit)
    if a.json:
        _emit([{"i": i, "ts": r["ts"], "final": r.get("final", ""),
                "raw": r.get("raw", ""), "wav": r.get("wav")}
               for i, r in enumerate(recs)])
        return 0
    if not recs:
        print("(no dictations yet)")
        return 0
    for i, r in enumerate(recs):
        print(f"[{i}] {r['ts']}  {r.get('final','')[:100]}")
    return 0


def cmd_copy(a) -> int:
    recs = history.recent()
    if a.index >= len(recs):
        print(f"no history item {a.index}", file=sys.stderr)
        return 1
    r = recs[a.index]
    inject.copy(r.get("raw" if a.raw else "final", ""))
    return 0


def cmd_retype(a) -> int:
    recs = history.recent()
    if a.index >= len(recs):
        return 1
    inject.inject(recs[a.index].get("raw" if a.raw else "final", ""))
    return 0


def cmd_retry(a) -> int:
    """Re-run the pipeline from a stored take — the fix for a bad transcription
    or a formatting pass that got thrown away."""
    recs = history.recent()
    if a.index >= len(recs):
        return 1
    wav = recs[a.index].get("wav")
    if not wav or not Path(wav).exists():
        print("audio for that dictation is no longer on disk", file=sys.stderr)
        return 1
    return 0 if pipeline.process(Path(wav), type_it=not a.dry) else 1


def cmd_settings(a) -> int:
    if not a.assign:
        _emit(config.settings(reload=True))
        return 0
    updates = {}
    for pair in a.assign:
        k, _, v = pair.partition("=")
        if k not in config.DEFAULTS:
            print(f"unknown setting {k!r}; known: {', '.join(config.DEFAULTS)}",
                  file=sys.stderr)
            return 2
        cur = config.DEFAULTS[k]
        if isinstance(cur, bool):
            v = v.lower() in ("1", "true", "yes", "on")
        elif isinstance(cur, int) and not isinstance(cur, bool):
            v = int(v)
        elif isinstance(cur, float):
            v = float(v)
        updates[k] = v
    _emit(config.save_settings(updates))
    return 0


def cmd_vocab(a) -> int:
    vocab.ensure_file()
    if a.action == "path":
        print(config.VOCAB_FILE)
    elif a.action == "edit":
        subprocess.run(["open", "-t", str(config.VOCAB_FILE)])
    else:
        terms = vocab.load()
        print(f"{len(terms)} terms in {config.VOCAB_FILE}")
        print(" ".join(terms))
    return 0


def cmd_prompt(a) -> int:
    fmt.ensure_prompt_file()
    if a.action == "path":
        print(config.PROMPT_FILE)
    elif a.action == "edit":
        subprocess.run(["open", "-t", str(config.PROMPT_FILE)])
    else:
        print(config.PROMPT_FILE.read_text(encoding="utf-8"))
    return 0


def cmd_set_key(a) -> int:
    """Store a hosted provider's API key.

    Read from stdin when no argument is given, so the key never has to appear
    in a command line. Written 0600, and deliberately NOT into settings.json —
    that file is rewritten by the menu and printed by `withy settings`.
    """
    if a.provider not in fmt.PROVIDERS:
        print(f"unknown provider {a.provider!r}", file=sys.stderr)
        return 2
    key = (a.key if a.key else sys.stdin.read()).strip()
    if len(key) < 10:
        print("that does not look like a key", file=sys.stderr)
        return 1
    config.ensure_dirs()
    f = fmt.key_path(a.provider)
    f.write_text(key, encoding="utf-8")
    f.chmod(0o600)
    print(f"saved {a.provider} key to {f}")
    return 0


def cmd_remove_key(a) -> int:
    if a.provider not in fmt.PROVIDERS:
        print(f"unknown provider {a.provider!r}", file=sys.stderr)
        return 2
    f = fmt.key_path(a.provider)
    existed = f.exists()
    f.unlink(missing_ok=True)
    print(f"{'removed' if existed else 'no stored key for'} {a.provider}")
    # An exported environment variable would still be picked up; say so rather
    # than letting the user believe the key is gone.
    if fmt.has_key(a.provider):
        env = ", ".join(fmt.PROVIDERS[a.provider]["env"])
        print(f"note: a key is still visible via the environment ({env})",
              file=sys.stderr)
    return 0


def cmd_keys(a) -> int:
    out = {p: {"stored": fmt.key_path(p).exists(),
               "usable": fmt.has_key(p),
               "label": fmt.PROVIDERS[p]["label"]}
           for p in fmt.PROVIDERS}
    if a.json:
        _emit(out)
    else:
        for p, v in out.items():
            print(f"  {v['label']:8} {'available' if v['usable'] else 'needed'}")
    return 0


def cmd_set_command(a) -> int:
    """Set the local CLI used for polishing, e.g. `claude -p`."""
    # Taken as ONE string and split here: argparse would otherwise swallow the
    # flags the command needs ("-p" becomes an unrecognised option), and a
    # quoted string is also what a GUI prompt naturally returns.
    raw = a.command if a.command else sys.stdin.read()
    argv = shlex.split(raw.strip())
    if not argv:
        print("no command given", file=sys.stderr)
        return 1
    if not shutil.which(argv[0]):
        print(f"warning: {argv[0]!r} is not on PATH", file=sys.stderr)
    config.save_settings({"polish_command": argv})
    print("polish command: " + " ".join(argv))
    return 0


PROBE_IN = "Add punctuation and return only the corrected text: hello there how are you"
PROBE_WANT = ("hello", "there", "how", "are", "you")


def cmd_test_command(a) -> int:
    """Check that the configured CLI actually behaves like a polisher.

    A wrong command fails silently and safely — polishing just never happens —
    which is the right failure mode but a terrible experience, because nothing
    tells you why. So the command is exercised once, when it is set.

    Three things can be wrong and each is reported separately: the command does
    not exist, it errors, or it 'works' but prints a banner / spinner / preamble
    around the answer, which would be typed into the user's document.
    """
    argv = fmt.detect_cli()
    if not argv:
        configured = fmt.configured_cli()
        if configured:
            msg = (f"`{configured[0]}` is not installed, or not on PATH.\n\n"
                   f"That is the command Withy has been told to use, so polishing "
                   f"is doing nothing at all. Check the spelling, or set a "
                   f"different one.")
        else:
            msg = ("No command-line assistant found. Set one with: "
                   'withy set-command "claude -p"')
        _emit({"ok": False, "reason": "not-found", "message": msg}) if a.json else print(msg)
        return 1

    t0 = time.time()
    try:
        res = subprocess.run(argv, input=PROBE_IN, capture_output=True,
                             text=True, timeout=a.timeout)
    except subprocess.TimeoutExpired:
        msg = (f"`{' '.join(argv)}` produced nothing within {a.timeout}s. "
               "It may be waiting for input, or the model is very slow.")
        _emit({"ok": False, "reason": "timeout", "message": msg}) if a.json else print(msg)
        return 1
    except OSError as e:
        msg = f"Could not run `{argv[0]}`: {e}"
        _emit({"ok": False, "reason": "exec", "message": msg}) if a.json else print(msg)
        return 1

    took = time.time() - t0
    out = res.stdout.strip()
    if res.returncode != 0:
        msg = (f"`{' '.join(argv)}` exited {res.returncode}.\n"
               f"{(res.stderr or '').strip()[:300]}")
        _emit({"ok": False, "reason": "exit", "message": msg}) if a.json else print(msg)
        return 1
    if not out:
        msg = f"`{' '.join(argv)}` printed nothing."
        _emit({"ok": False, "reason": "empty", "message": msg}) if a.json else print(msg)
        return 1

    low = out.lower()
    missing = [w for w in PROBE_WANT if w not in low]
    # A polisher returns roughly what it was given. Much more than that means
    # banners, reasoning, or an explanation — all of which would be typed out.
    noisy = len(out.split()) > 3 * len(PROBE_WANT)

    if missing or noisy:
        why = ("it did not echo the words back"
               if missing else "it printed a lot of extra text around the answer")
        msg = (f"`{' '.join(argv)}` ran in {took:.1f}s but {why}. "
               "Withy needs a command that prints ONLY the corrected text — "
               "look for a quiet or print-only flag.\n\nIt returned:\n"
               + out[:300])
        _emit({"ok": False, "reason": "noisy", "message": msg}) if a.json else print(msg)
        return 1

    msg = f"Works. `{' '.join(argv)}` replied in {took:.1f}s:\n{out[:200]}"
    if took > 20:
        msg += ("\n\nThat is slow for something that runs on every dictation. "
                "If the tool has a fast-model flag, add it — measured elsewhere, "
                "a default model took 76.7s where a fast one took 16.6s.")
    _emit({"ok": True, "seconds": round(took, 1), "message": msg}) if a.json else print(msg)
    return 0


def cmd_mics(a) -> int:
    mics = capture.list_mics()
    if a.json:
        _emit({"mics": mics, "resolved": capture.resolve_mic()})
        return 0
    for m in mics:
        print(("* " if m == capture.resolve_mic() else "  ") + m)
    return 0


def cmd_purge(a) -> int:
    n = history.purge(a.keep_days)
    w = capture.purge_audio(a.keep_days)
    print(f"removed {n} history record(s) and {w} audio file(s)")
    return 0


def cmd_diagnose(a) -> int:
    """Check the install, and optionally measure microphone start latency.

    The latency measurement records ~2 seconds of audio. It is OFF by default
    and enabled with --mic, because a dictation tool should never open the
    microphone as a side effect of a health check.
    """
    s = config.settings(reload=True)
    ok = True

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and good
        print(f"  [{'ok' if good else 'FAIL'}] {label}{'  ' + detail if detail else ''}")

    print("binaries")
    for label, path in (("ffmpeg", config.FFMPEG_BIN),
                        ("whisper-cli", config.WHISPER_BIN)):
        good = config.usable(path)
        check(label, good, path if good else f"{path} — NOT RESOLVED (PATH problem)")
    check("hammerspoon (hs)", config.usable(inject.HS_BIN),
          inject.HS_BIN or "not found — falling back to osascript")

    print("model")
    mp = Path(str(s["whisper_model"]))
    check("whisper model", mp.exists(), str(mp))

    print("audio")
    mics = capture.list_mics()
    check("input devices", bool(mics), f"{len(mics)} found; using {capture.resolve_mic()!r}")

    print("formatting")
    if not s["postprocess"]:
        print("  [--] disabled in settings")
    else:
        t0 = time.time()
        r = fmt._ollama(s["llm_model"], "Reply with the single word: ready", 20)
        check(f"ollama model {s['llm_model']}", bool(r), f"{time.time()-t0:.1f}s")

    if a.mic:
        print("microphone start latency")
        # The window must be measured from BEFORE start() to the moment the
        # recorder is cut — and must NOT include stop()'s teardown, which waits
        # up to 3s for ffmpeg to flush the WAV header. An earlier version timed
        # the teardown too and reported ~3,700 ms of "lost speech" for what was
        # really ~560 ms: the instrument was measuring itself.
        WINDOW = 2.0
        t0 = time.time()
        capture.start()
        time.sleep(WINDOW)
        t_cut = time.time()
        wav = capture.stop()
        if wav:
            from . import transcribe as tr
            dur = tr.clip_duration(wav)
            window = t_cut - t0
            lost = max(0.0, window - dur)
            print(f"  window {window:.2f}s, captured {dur:.2f}s "
                  f"-> ~{lost*1000:.0f} ms lost before the device opened")
            print("  (speech spoken in that gap never reaches the model)")
            print("  (that gap is speech spoken before the device opened)")
            wav.unlink(missing_ok=True)
        else:
            check("capture", False, "no audio recorded")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="withy", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("start", help="begin recording").set_defaults(fn=cmd_start)
    q = sub.add_parser("stop", help="end recording and type the result")
    q.add_argument("--json", action="store_true")
    q.set_defaults(fn=cmd_stop)
    sub.add_parser("cancel", help="discard the in-flight recording").set_defaults(fn=cmd_cancel)

    q = sub.add_parser("run", help="process a WAV or a literal string")
    q.add_argument("wav", nargs="?")
    q.add_argument("--text")
    q.add_argument("--dry", action="store_true", help="print, do not type")
    q.set_defaults(fn=cmd_run)

    q = sub.add_parser("history")
    q.add_argument("--limit", type=int, default=10)
    q.add_argument("--json", action="store_true")
    q.set_defaults(fn=cmd_history)

    q = sub.add_parser("copy", help="copy a past dictation to the clipboard")
    q.add_argument("index", type=int, nargs="?", default=0)
    q.add_argument("--raw", action="store_true")
    q.set_defaults(fn=cmd_copy)

    q = sub.add_parser("retype", help="type a past dictation again")
    q.add_argument("index", type=int, nargs="?", default=0)
    q.add_argument("--raw", action="store_true")
    q.set_defaults(fn=cmd_retype)

    q = sub.add_parser("retry", help="re-run the pipeline from the stored audio")
    q.add_argument("index", type=int, nargs="?", default=0)
    q.add_argument("--dry", action="store_true")
    q.set_defaults(fn=cmd_retry)

    q = sub.add_parser("settings")
    q.add_argument("assign", nargs="*", help="key=value")
    q.set_defaults(fn=cmd_settings)

    q = sub.add_parser("vocab")
    q.add_argument("action", nargs="?", default="show",
                   choices=["show", "path", "edit"])
    q.set_defaults(fn=cmd_vocab)

    q = sub.add_parser("prompt", help="the polishing instructions")
    q.add_argument("action", nargs="?", default="show",
                   choices=["show", "path", "edit"])
    q.set_defaults(fn=cmd_prompt)

    q = sub.add_parser("set-key", help="store a hosted provider's API key")
    q.add_argument("provider", choices=["openai", "anthropic"])
    q.add_argument("key", nargs="?", help="omit to read from stdin")
    q.set_defaults(fn=cmd_set_key)

    q = sub.add_parser("remove-key", help="delete a stored API key")
    q.add_argument("provider", choices=["openai", "anthropic"])
    q.set_defaults(fn=cmd_remove_key)

    q = sub.add_parser("keys", help="which providers have a key")
    q.add_argument("--json", action="store_true")
    q.set_defaults(fn=cmd_keys)

    q = sub.add_parser("set-command", help="the local CLI used for polishing")
    q.add_argument("command", nargs="?", help='one string, e.g. "claude -p"')
    q.set_defaults(fn=cmd_set_command)

    q = sub.add_parser("test-command", help="check the local CLI actually works")
    q.add_argument("--json", action="store_true")
    q.add_argument("--timeout", type=int, default=90)
    q.set_defaults(fn=cmd_test_command)

    q = sub.add_parser("mics")
    q.add_argument("--json", action="store_true")
    q.set_defaults(fn=cmd_mics)

    q = sub.add_parser("purge")
    q.add_argument("keep_days", type=int, nargs="?", default=0)
    q.set_defaults(fn=cmd_purge)

    q = sub.add_parser("diagnose")
    q.add_argument("--mic", action="store_true",
                   help="also measure microphone start latency (records ~2s)")
    q.set_defaults(fn=cmd_diagnose)

    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except Exception as e:                                   # noqa: BLE001
        log(f"cli {a.cmd} CRASHED: {type(e).__name__}: {e}")
        print(f"withy: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
