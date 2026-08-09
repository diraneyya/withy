"""
cli.py — python3 -m dictation <command>

  transcribe <wav>            stages 1-2 only; print the raw transcript
  run <wav> [--dry]           full pipeline: transcribe → correct → inject
  correct --text "..."        run the correction stage on given text
  build-vocab                 (re)generate the vocabulary index + bias prompt
  history [list|copy|copy-raw|show|purge] [n]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from . import config, history
from .correct import correct as correct_text
from .correct import vocab
from .inject import inject
from .log import log, set_state
from .transcribe import transcribe


def _cmd_transcribe(args: list[str]) -> int:
    if not args:
        print("usage: transcribe <wav>", file=sys.stderr)
        return 2
    text, lang = transcribe(Path(args[0]).expanduser())
    if not text:
        return 1
    print(f"[{lang}] {text}")
    return 0


def _cmd_run(args: list[str]) -> int:
    dry = "--dry" in args
    args = [a for a in args if not a.startswith("--")]
    if not args:
        print("usage: run <wav> [--dry]", file=sys.stderr)
        return 2

    set_state("transcribing")
    raw, lang = transcribe(Path(args[0]).expanduser())
    if not raw:
        set_state("idle")
        return 0

    final, meta = correct_text(raw, lang) if config.CORRECTION_ENABLED else (raw, {"lang": lang})
    log(f"[{lang}] raw={raw!r} final={final!r} swaps={meta.get('swaps')}")

    # Written BEFORE injection: if injection fails the text still exists.
    history.append(raw, final, meta)

    if dry:
        set_state("idle")
        print(final)
        return 0

    # Dismiss any overlay before typing, so it cannot cover the target field and
    # focus visibly belongs to the user's text box.
    set_state("idle")
    if not inject(final):
        log("injection failed — text preserved in history for manual recovery")
        print("injection failed; recover with: dictation history copy 1", file=sys.stderr)
        return 1
    return 0


def _cmd_correct(args: list[str]) -> int:
    if not args or args[0] != "--text":
        print('usage: correct --text "some text"', file=sys.stderr)
        return 2
    final, meta = correct_text(" ".join(args[1:]).strip())
    print(final)
    if meta["removed"]:
        print(f"  removed: {meta['removed']}", file=sys.stderr)
    for s in meta["swaps"]:
        print(f"  [{s['method']}] '{s['span']}' → {s['to']}", file=sys.stderr)
    return 0


def _cmd_build_vocab(_args: list[str]) -> int:
    if not config.CORPUS_ROOTS:
        print("DICTATION_CORPUS is unset — nothing to index.\n"
              "  export DICTATION_CORPUS=~/work/docs:~/work/runbooks", file=sys.stderr)
        return 2
    entries, terms = vocab.rebuild()
    if not entries:
        print("No terms extracted — check DICTATION_CORPUS and DICTATION_CORPUS_GLOBS.",
              file=sys.stderr)
        return 1
    print(f"{entries} index entries → {config.VOCAB_INDEX_FILE}")
    print(f"{terms} bias terms    → {config.VOCAB_PROMPT_FILE}")
    return 0


def _cmd_history(args: list[str]) -> int:
    sub = args[0] if args else "list"
    recs = history.recent()

    if sub == "list":
        n = int(args[1]) if len(args) > 1 else 10
        if not recs:
            print("(no dictations yet)")
            return 0
        for i, r in enumerate(recs[:n], 1):
            text = " ".join(r["final"].split())
            print(f"{i:3}  {r['ts'][11:]}  {text[:77] + '...' if len(text) > 80 else text}")
        return 0

    if sub == "purge":
        days = int(args[1]) if len(args) > 1 else 0
        print(f"removed {history.purge(days)} record(s)")
        return 0

    if sub in ("copy", "copy-raw", "show"):
        if len(args) < 2:
            print(f"usage: history {sub} <n>", file=sys.stderr)
            return 2
        idx = int(args[1]) - 1
        if idx < 0 or idx >= len(recs):
            print(f"no item {args[1]} (history has {len(recs)})", file=sys.stderr)
            return 1
        r = recs[idx]
        if sub == "show":
            print(f"ts:    {r['ts']}")
            print(f"raw:   {r['raw']}")
            print(f"final: {r['final']}")
            print(f"meta:  {r.get('meta')}")
            return 0
        text = r["raw"] if sub == "copy-raw" else r["final"]
        subprocess.run(["pbcopy"], input=text.encode("utf-8"))
        print(f"copied #{args[1]} → clipboard: {text[:57] + '...' if len(text) > 60 else text}")
        return 0

    print(__doc__, file=sys.stderr)
    return 2


COMMANDS = {
    "transcribe": _cmd_transcribe,
    "run": _cmd_run,
    "correct": _cmd_correct,
    "build-vocab": _cmd_build_vocab,
    "history": _cmd_history,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd not in COMMANDS:
        print(f"unknown command: {cmd}\n{__doc__}", file=sys.stderr)
        return 2
    return COMMANDS[cmd](argv[1:])
