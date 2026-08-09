#!/usr/bin/env bash
# record.sh — capture the microphone to a Whisper-ready WAV.
#
#   ./record.sh /tmp/take.wav          record until Ctrl-C
#   ./record.sh start | stop | cancel  push-to-talk, for a hotkey layer to call
#
# 16 kHz mono is Whisper's native input format. Resample here, not later.

set -euo pipefail

WAV="${DICTATION_WAV:-/tmp/dictation-input.wav}"
PID_FILE="/tmp/dictation-ffmpeg.pid"
STATE_FILE="${DICTATION_STATE:-/tmp/dictation-state}"
LOG="${DICTATION_LOG:-/tmp/dictation.log}"
FFMPEG="${DICTATION_FFMPEG_BIN:-$(command -v ffmpeg)}"
FFPROBE="${DICTATION_FFPROBE_BIN:-$(command -v ffprobe)}"
MIN_CLIP="${DICTATION_MIN_CLIP:-0.3}"

# Select the microphone by NAME, never by index.
#
# `-i ":0"` picks the first ENUMERATED device, which is not the system default.
# On any machine with BlackHole / Loopback / Loom / Krisp installed — i.e. most
# developer laptops — index 0 is often an aggregate reporting 16+ channels.
# ffmpeg refuses to auto-downmix an unknown high-channel layout and writes a
# ZERO-BYTE WAV with exit code 0. The symptom is "dictation does nothing", with
# no error anywhere.
#
# List devices:  ffmpeg -f avfoundation -list_devices true -i ""
MIC="${DICTATION_MIC:-MacBook Pro Microphone}"

log() { printf '[%s] record: %s\n' "$(date '+%H:%M:%S')" "$*" >> "$LOG"; }

start_recording() {
  # Interrupt anything in flight. This is what makes "press again to cancel and
  # re-speak" work, and it means no separate cancel key is needed.
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    kill -KILL "$(cat "$PID_FILE")" 2>/dev/null || true
    log "killed stale ffmpeg"
  fi
  pkill -f 'dictation.cli' 2>/dev/null || true

  rm -f "$WAV"
  log "start mic='$MIC'"
  nohup "$FFMPEG" -hide_banner -loglevel error -nostdin \
    -f avfoundation -i ":$MIC" \
    -ar 16000 -ac 1 \
    -y "$WAV" >> "$LOG" 2>&1 &
  echo $! > "$PID_FILE"
  echo "recording" > "$STATE_FILE"
}

stop_recording() {
  [[ -f "$PID_FILE" ]] || { log "stop: nothing recording"; return 0; }
  local pid; pid="$(cat "$PID_FILE")"; rm -f "$PID_FILE"
  if kill -0 "$pid" 2>/dev/null; then
    # SIGINT, not SIGKILL — ffmpeg needs to flush the WAV header. A killed
    # recorder leaves a header-less file that whisper cannot read.
    kill -INT "$pid" 2>/dev/null || true
    for _ in $(seq 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
    kill -KILL "$pid" 2>/dev/null || true
  fi

  if [[ ! -s "$WAV" ]]; then
    log "stop: WAV empty — wrong mic device? (see MIC above)"
    echo "idle" > "$STATE_FILE"; return 1
  fi
  # Reject accidental taps: Whisper hallucinates a confident sentence out of
  # 200ms of room tone.
  local dur; dur=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$WAV" 2>/dev/null || echo 0)
  if awk -v d="$dur" -v m="$MIN_CLIP" 'BEGIN { exit !(d < m) }'; then
    log "stop: clip too short (${dur}s), discarding"
    echo "idle" > "$STATE_FILE"; return 1
  fi
  log "stop: ${dur}s captured"
  echo "$WAV"
}

case "${1:-}" in
  start)  start_recording ;;
  stop)   stop_recording ;;
  cancel) [[ -f "$PID_FILE" ]] && { kill -KILL "$(cat "$PID_FILE")" 2>/dev/null || true; rm -f "$PID_FILE"; }
          echo "idle" > "$STATE_FILE" ;;
  "")     echo "usage: $0 <output.wav> | start | stop | cancel" >&2; exit 2 ;;
  *)      WAV="$1"
          echo "recording to $WAV — Ctrl-C to stop" >&2
          exec "$FFMPEG" -hide_banner -loglevel error \
            -f avfoundation -i ":$MIC" -ar 16000 -ac 1 -y "$WAV" ;;
esac
