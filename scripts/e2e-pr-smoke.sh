#!/bin/bash
# Fast PR integration smoke test (~1-2 minutes).
# Verifies CLI config lifecycle + provider reachability + transcription request path
# against a local mock OpenAI-compatible endpoint.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEST_AUDIO="$SCRIPT_DIR/tests/e2e/test_audio.flac"
PORT=28761
CONFIG_DIR="$(mktemp -d)"
CONFIG="$CONFIG_DIR/config.toml"
STATUS_OUT="$CONFIG_DIR/status.out"
SERVER_PID=""

cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$CONFIG_DIR"
}
trap cleanup EXIT

echo "[e2e-pr] Starting local mock whisper endpoint on port $PORT..."
python - "$PORT" <<'PY' &
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

port = int(sys.argv[1])


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"text": "smoke ok"}).encode("utf-8"))

    def log_message(self, _fmt, *_args):
        return


HTTPServer(("127.0.0.1", port), Handler).serve_forever()
PY
SERVER_PID=$!

for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done

echo "[e2e-pr] Creating config..."
whisper-dic provider --config "$CONFIG" >/dev/null
whisper-dic set whisper.provider local --config "$CONFIG" >/dev/null
whisper-dic set whisper.local.url "http://127.0.0.1:$PORT/v1/audio/transcriptions" --config "$CONFIG" >/dev/null
whisper-dic set whisper.groq.url "http://127.0.0.1:$PORT/v1/audio/transcriptions" --config "$CONFIG" >/dev/null
whisper-dic set whisper.groq.api_key "gsk_smoke_test" --config "$CONFIG" >/dev/null

echo "[e2e-pr] Running status checks..."
whisper-dic status --config "$CONFIG" >"$STATUS_OUT"
grep -q "local endpoint reachable: yes" "$STATUS_OUT"
grep -q "groq endpoint reachable: yes" "$STATUS_OUT"
grep -q "active provider (local) reachable: yes" "$STATUS_OUT"

echo "[e2e-pr] Running transcription path check..."
python - "$CONFIG" "$TEST_AUDIO" <<'PY'
import sys
from pathlib import Path

from whisper_dic.config import load_config
from whisper_dic.transcriber import create_transcriber

config_path = Path(sys.argv[1])
audio_path = Path(sys.argv[2])
cfg = load_config(config_path)
t = create_transcriber(cfg.whisper)
try:
    text = t.transcribe(audio_path.read_bytes())
finally:
    t.close()
if text != "smoke ok":
    raise SystemExit(f"Unexpected transcription: {text!r}")
PY

echo "[e2e-pr] PASS"
