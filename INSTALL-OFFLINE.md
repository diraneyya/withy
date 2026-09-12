# Withy — installing where GitHub is blocked

This copy exists because `github.com` is not reachable from some corporate
networks. Everything needed is here; you do not need the repository.

**Withy** is local push-to-talk dictation for macOS. Hold a key, speak, release,
and the text is typed into whatever app has focus. Speech never leaves the
laptop. It replaces a paid cloud dictation tool at no per-seat cost and with no
vendor review to pass, because no audio is transmitted.

Read `README.md` for what it does and where the name comes from. This file is
only about getting it installed behind a firewall.

---

## 1. Check what the network allows — before downloading 4 GB

GitHub being blocked does not mean everything is. Run this first:

```bash
for h in ghcr.io huggingface.co registry.ollama.ai formulae.brew.sh; do
  curl -sS -o /dev/null -w "%{http_code}  $h"$'\n' --max-time 8 "https://$h" \
    || echo "UNREACHABLE  $h"
done
```

Any 2xx/3xx is fine.

| Host | Needed for | If blocked |
|---|---|---|
| `ghcr.io`, `formulae.brew.sh` | Homebrew packages | see §4 — nothing works without brew |
| `huggingface.co` | the speech model, 1.6 GB | see §3 |
| `registry.ollama.ai` | the wording clean-up model, 1.9 GB | install with `--no-llm` |

Homebrew pulls its bottles from `ghcr.io`, which is GitHub infrastructure but a
different host from `github.com` — so brew usually keeps working where the
website does not.

## 2. Install

```bash
unzip withy-*.zip
cd withy
./install.sh
```

Then grant **Hammerspoon** *Accessibility* and *Input Monitoring* in
System Settings → Privacy & Security. Hold **right Option** and speak.

Right Option is the default precisely because `fn` is usually already taken — by
Apple Dictation, and by the commercial dictation tools. Keep both installed on
different keys and compare them on the same sentences before switching.

## 3. If `huggingface.co` is blocked

The speech model is one file. Fetch it from any machine with access and copy it
across:

```bash
# on a machine with access:
curl -L -o ggml-large-v3-turbo.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin

# on the work machine:
mkdir -p "$(brew --prefix)/share/whisper-cpp"
cp ggml-large-v3-turbo.bin "$(brew --prefix)/share/whisper-cpp/"
```

Then run `./install.sh` — it skips any download whose file is already present.

`ggml-base.en.bin` (148 MB) is the small alternative: much faster, noticeably
less accurate, English only. Install it the same way and run
`./install.sh --model base.en`.

## 4. If Homebrew itself is blocked

Stop — that is a conversation with IT, not something to work around. Withy needs
`ffmpeg`, `whisper-cpp` and `hammerspoon`, all ordinary open-source packages.

## 5. What to tell a security reviewer

- **No audio or text is transmitted anywhere.** Transcription is `whisper.cpp`
  running locally; the optional wording clean-up is a local model under
  `ollama`, reached over `127.0.0.1`. There is no API key and no account.
- Dictation history is plain text at `~/.local/share/withy/history.jsonl`, and
  audio at `~/.local/share/withy/audio/`. Both local only. Set a retention
  window with `withy purge <days>`, and exclude those paths from backups if
  policy requires it.
- Licence: Apache-2.0, including the patent grant.
- The code is small and readable: the pipeline is around a thousand lines of
  Python with **no third-party dependencies**, on the Python that ships with
  macOS. `source/withy/` is the whole thing.

## 6. Verify before trusting it

```bash
~/.local/bin/withy diagnose
~/.local/bin/withy run --text "um so the the plan is to test this" --dry
```

The second should print a cleaned, punctuated sentence. If it prints the input
unchanged, the clean-up model is not reachable and everything else still works.
