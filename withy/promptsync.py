"""
promptsync.py — keeping your polishing instructions and ours in step.

THE PROBLEM THIS SOLVES, because it is not obvious from the code.

Withy writes `prompt.md` for you on first run, pre-filled with its own
instructions. From that moment `load_prompt()` prefers the file, so the copy in
the source code is dead — and every later improvement to the instructions
reaches nobody who has ever launched the app. That is not hypothetical: a
prompt file created one minute before a fix was committed went on overriding
that fix indefinitely.

The naive repair is to compare your file against the shipped default and
replace it when they differ. That cannot work, and the reason is worth stating:
with only two versions in hand, "you added a line" and "we deleted a line"
produce byte-identical files while demanding opposite actions. The information
needed to tell them apart simply is not present.

So we keep a third file — `prompt.base.md`, whatever Withy last wrote into
yours. With that ancestor, every paragraph can be asked who moved it, and the
answer decides:

    nobody changed it          -> leave it
    only we changed it         -> take ours; you never had an opinion here
    only you changed it        -> keep yours; we have no opinion here
    both changed it            -> a real disagreement; ask

This is the `conffile` problem, which Debian has been solving this way since
long before this tool existed, and the merge itself is done by `diff3`, which
ships with macOS. `git` is deliberately NOT used: /usr/bin/git is an Xcode shim
that pops a GUI installer on a machine without the Command Line Tools, and a
dictation tool must never do that.

TWO WAYS THIS DIFFERS FROM MERGING AN ORDINARY CONFIG FILE.

1. Lines are not independent. In `sshd_config`, one line is one setting, so
   taking one line from each side yields exactly the union of both intents.
   Prose has no such property: two edits in different paragraphs can still
   contradict each other, and the merged text is then perfectly clean and
   quietly self-defeating. (Live example: this prompt's "NEVER replace a word"
   and its vocabulary hint's "use the correct spelling" are in different
   paragraphs and disagree — measurably, in dictation quality.) A config file
   also has a weak compiler — the service refuses to start — whereas a bad
   prompt never fails, it just degrades. So a merge here is a PROPOSAL, shown
   for confirmation, never applied silently.

2. The text is hard-wrapped, so a line is a fragment of a sentence. Adding
   three words upstream re-flows a whole paragraph, and a line-wise merge then
   reports conflicts that are nothing but moved line breaks. Everything is
   therefore unwrapped to one line per unit before merging and re-wrapped
   afterwards, which makes a PARAGRAPH the unit of comparison while still using
   a stock diff3.

Silence is the goal. The overwhelmingly common case is a user who never touched
the file, and they must never see any of this.
"""

from __future__ import annotations

import difflib
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from . import config

DIFF3 = "/usr/bin/diff3"
WIDTH = 78

# Lines that are their own unit and must never be joined to a neighbour: the
# comment header, bullets, and the markers diff3 writes into a conflict.
_STANDALONE = ("#", "- ", "* ", "<<<<<<<", "=======", ">>>>>>>", "|||||||")


def _standalone(line: str) -> bool:
    return any(line.startswith(p) for p in _STANDALONE)


def unwrap(text: str) -> str:
    """One line per unit of meaning: a comment, a bullet, or a paragraph.

    This is also the canonical form used for every equality test, which means a
    user who merely re-flows their file has not "edited" it.
    """
    out: list[str] = []
    joining = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            out.append("")
            joining = False
        elif _standalone(line.lstrip()) or not joining:
            out.append(line.strip())
            joining = not line.lstrip().startswith("#")
        else:
            out[-1] = out[-1] + " " + line.strip()
    return "\n".join(out).strip() + "\n"


def rewrap(text: str) -> str:
    """Put the wrapping back, in the shape the file is written in."""
    out: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            out.append("")
        elif line.startswith("#") or line.startswith(("<<<<<<<", "=======",
                                                      ">>>>>>>", "|||||||")):
            out.append(line)
        elif line.startswith(("- ", "* ")):
            out.extend(textwrap.wrap(line, width=WIDTH, subsequent_indent="  "))
        else:
            out.extend(textwrap.wrap(line, width=WIDTH))
    return "\n".join(out).rstrip() + "\n"


def _same(a: str, b: str) -> bool:
    return unwrap(a).strip() == unwrap(b).strip()


def merge(mine: str, base: str, theirs: str) -> tuple[str, bool]:
    """Three-way merge at paragraph granularity. Returns (text, clean)."""
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for name, body in (("mine", mine), ("base", base), ("theirs", theirs)):
            p = Path(d) / name
            p.write_text(unwrap(body), encoding="utf-8")
            paths.append(str(p))
        r = subprocess.run([DIFF3, "-m", *paths], capture_output=True, text=True)
    # 0 = merged cleanly, 1 = conflicts (output still usable, with markers),
    # anything else is diff3 itself failing and must not be treated as a merge.
    if r.returncode not in (0, 1):
        raise RuntimeError(r.stderr.strip() or "diff3 failed")
    return rewrap(r.stdout), r.returncode == 0


def diff(a: str, b: str, a_label: str, b_label: str) -> str:
    return "".join(difflib.unified_diff(
        rewrap(unwrap(a)).splitlines(keepends=True),
        rewrap(unwrap(b)).splitlines(keepends=True),
        fromfile=a_label, tofile=b_label, n=2))


def _preview(candidates: list[tuple[str, str]]) -> None:
    """Score each candidate prompt against the behaviour suite.

    A text diff answers "what changed in the wording", which is hard to judge
    when the wording is prose. This answers "which one behaves better", which is
    not. Failures are printed with the actual output, because a score alone does
    not tell you whether the thing it broke is a thing you care about.
    """
    from . import format as fmt, promptcheck
    for label, body in candidates:
        results = promptcheck.run(template=fmt.prompt_template(body))
        print(f"\n  {label}: {promptcheck.summarise(results)}")
        for r in results:
            if not r.ok:
                print(f"      {r.case.id}")
                print(textwrap.fill(r.out, width=WIDTH - 8,
                                    initial_indent="        ",
                                    subsequent_indent="        "))
                for prob in r.problems:
                    print(f"        ---> {prob}")
    print()


def _ask(options: list[tuple[str, str]]) -> str:
    keys = [k for k, _ in options]
    while True:
        print()
        for k, label in options:
            print(f"    [{k}]  {label}")
        try:
            answer = input(f"\n  which? [{'/'.join(keys)}] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "k"
        if answer in keys:
            return answer


def save_base(text: str) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.PROMPT_BASE_FILE.write_text(text, encoding="utf-8")


def sync(interactive: bool | None = None) -> str:
    """Reconcile prompt.md with the instructions this version ships.

    Returns a short status string, for the caller to log or ignore. Never
    raises: a failure here must not be able to stop an install.
    """
    from . import format as fmt
    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()

    stock = fmt.PROMPT_FILE_SAMPLE
    config.ensure_dirs()

    # Nothing on disk yet: this is a first run, not a merge.
    if not config.PROMPT_FILE.exists():
        config.PROMPT_FILE.write_text(stock, encoding="utf-8")
        save_base(stock)
        return "created"

    mine = config.PROMPT_FILE.read_text(encoding="utf-8")

    # No ancestor recorded — an install that predates this mechanism. We can
    # see that the file differs from what we ship, but not whether that is the
    # user's work or our own stale default, which is exactly the ambiguity the
    # baseline exists to remove. Ask once; from then on it is answerable.
    if not config.PROMPT_BASE_FILE.exists():
        if _same(mine, stock):
            save_base(mine)
            return "adopted (matched the shipped instructions)"
        if not interactive:
            return ("customised, no ancestor recorded — run `withy prompt sync` "
                    "to reconcile")
        print("\nYour polishing instructions differ from the ones this version "
              "ships,\nand Withy has no record of what it last wrote, so it "
              "cannot tell whether\nyou edited them or they are simply old.\n")
        while True:
            a = _ask([("k", "keep mine — I wrote these"),
                      ("t", "take the new ones — mine were never edited"),
                      ("d", "show me the differences"),
                      ("p", "test both against the behaviour suite")])
            if a == "d":
                print("\n" + (diff(mine, stock, "yours", "new") or "  (identical)"))
            elif a == "p":
                _preview([("yours", mine), ("new", stock)])
            elif a == "k":
                save_base(mine)      # your text becomes the ancestor
                return "kept yours"
            else:
                config.PROMPT_FILE.write_text(stock, encoding="utf-8")
                save_base(stock)
                return "took the new instructions"

    base = config.PROMPT_BASE_FILE.read_text(encoding="utf-8")
    mine_moved = not _same(mine, base)
    ours_moved = not _same(stock, base)

    if not ours_moved:
        if not mine_moved:
            return "unchanged"
        return "yours, unchanged by us"

    # You never touched it, so there is nothing of yours to lose. This is the
    # case the whole mechanism exists for, and it must be silent.
    if not mine_moved:
        config.PROMPT_FILE.write_text(stock, encoding="utf-8")
        save_base(stock)
        return "updated"

    # Both moved. In prose that is a proposal, never an automatic answer.
    try:
        merged, clean = merge(mine, base, stock)
    except (RuntimeError, OSError) as e:
        merged, clean = "", False
        print(f"withy: could not merge ({e}) — leaving your instructions alone",
              file=sys.stderr)

    if not interactive:
        return ("both changed — run `withy prompt sync` to reconcile "
                f"({'a clean merge is available' if clean else 'they overlap'})")

    print("\nWithy's polishing instructions have changed, and so have yours.")
    print("Nothing has been altered yet." if clean else
          "Nothing has been altered yet. Your edits and ours overlap.")
    options = [("k", "keep mine — ignore the new instructions"),
               ("t", "take the new ones — discard my edits")]
    if merged:
        options.append(("m", "use the merged version — my edits AND the new "
                             "instructions" if clean else
                             "open the merged version and resolve it by hand"))
    options += [("d", "show me the differences"),
                ("p", "test both against the behaviour suite")]

    while True:
        a = _ask(options)
        if a == "d":
            print("\n--- what WE changed " + "-" * 40)
            print(diff(base, stock, "previous", "new") or "  (nothing)")
            print("--- what YOU changed " + "-" * 39)
            print(diff(base, mine, "previous", "yours") or "  (nothing)")
        elif a == "p":
            cands = [("yours", mine), ("new", stock)]
            if merged and clean:
                cands.append(("merged", merged))
            _preview(cands)
        elif a == "k":
            save_base(stock)
            return "kept yours"
        elif a == "t":
            config.PROMPT_FILE.write_text(stock, encoding="utf-8")
            save_base(stock)
            return "took the new instructions"
        elif a == "m":
            config.PROMPT_FILE.write_text(merged, encoding="utf-8")
            save_base(stock)
            if clean:
                return "merged"
            print(f"\n  Conflict markers written to {config.PROMPT_FILE}.")
            print("  Edit it, delete the markers, and save.")
            subprocess.run(["open", "-t", str(config.PROMPT_FILE)])
            return "merged with conflicts — resolve by hand"
