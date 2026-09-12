#!/usr/bin/env python3
"""
run_eval.py — measure the post-processing stage against real dictations.

The formatting stage cannot be unit-tested into correctness: there is no single
right answer for "where does a paragraph break go". What CAN be measured, and
what actually matters, is the safety property:

    how often does the gate reject, and why?

A high rejection rate means the model is inventing words and the formatting is
silently not happening. A zero rejection rate on a small model is more likely to
mean the gate is broken than that the model is perfect.

Usage:
    python3 eval/run_eval.py --limit 50
    python3 eval/run_eval.py --model qwen2.5:3b --limit 100 --show 5
    python3 eval/run_eval.py --input my-transcripts.jsonl     # field: "raw"
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

DEFAULT_INPUT = pathlib.Path.home() / ".local/share/brain-dictate/history.jsonl"


def load(path: pathlib.Path, limit: int, seed: int) -> list[str]:
    if not path.exists():
        sys.exit(f"no transcript corpus at {path} — pass --input")
    raws = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = (r.get("raw") or "").strip()
        if t:
            raws.append(t)
    random.Random(seed).shuffle(raws)
    return raws[:limit] if limit else raws


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=pathlib.Path, default=DEFAULT_INPUT)
    ap.add_argument("--model", default=None, help="ollama model to evaluate")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--show", type=int, default=3, help="sample outputs to print")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--vocab", type=pathlib.Path, default=None)
    args = ap.parse_args()

    if args.model:
        os.environ["WITHY_LLM_MODEL"] = args.model
    from withy import config, correct, format as fmt   # noqa: E402

    terms = []
    if args.vocab and args.vocab.exists():
        terms = args.vocab.read_text(encoding="utf-8").split()

    texts = load(args.input, args.limit, args.seed)
    model = config.settings(reload=True)["llm_model"]
    print(f"model={model}  corpus={args.input}  n={len(texts)}\n")

    rejected, times, shown, total_words = [], [], [], 0
    for i, raw in enumerate(texts, 1):
        pre, _ = correct.clean(raw, terms, disfluency=False)
        t0 = time.time()
        out, meta = fmt.format_text(pre, terms)
        dt = time.time() - t0
        times.append(dt)
        total_words += len(raw.split())
        for why in meta.get("rejected") or []:
            rejected.append((why, raw[:70]))
        if len(shown) < args.show and meta.get("applied"):
            shown.append((raw, out))
        print(f"\r  {i}/{len(texts)}  {dt:5.1f}s", end="", flush=True)
    print("\n")

    n = len(texts)
    print(f"gate  : {n - len({r[1] for r in rejected})}/{n} dictations fully accepted")
    print(f"time  : {sum(times)/n:.2f}s mean, {max(times):.1f}s worst, "
          f"{sum(times):.0f}s total for {total_words} words")
    if rejected:
        print(f"\nrejections ({len(rejected)}):")
        for why, snippet in rejected[:12]:
            print(f"  · {why}\n      {snippet}…")
    for raw, out in shown:
        print("\n" + "─" * 70)
        print("RAW :", raw[:300])
        print("FMT :", out[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
