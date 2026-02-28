#!/bin/bash
# Smoke test: lint, compile, startup, and dictation pipeline check.
# Usage: ./scripts/smoke-test.sh
# Exit 0 = pass, Exit 1 = fail

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "[smoke] SKIP: no .venv found (smoke test requires venv)"
  exit 0
fi

# Step 1: Compile check
echo "[smoke] Compile check..."
if ! "$PYTHON" -m compileall -q "$SCRIPT_DIR"/*.py; then
  echo "[smoke] FAIL: compile error"
  exit 1
fi

# Step 2: Ruff lint
if "$PYTHON" -m ruff check "$SCRIPT_DIR" --quiet 2>/dev/null; then
  echo "[smoke] Lint: passed"
else
  echo "[smoke] FAIL: ruff lint errors"
  exit 1
fi

# Step 3: Startup test — app must start and stay alive for 3 seconds
pkill -f "dictation.py menubar.*--config.*/tmp/smoke" 2>/dev/null || true
sleep 0.5

SMOKE_CONFIG="/tmp/smoke-test-whisper-dic.toml"
cp "$SCRIPT_DIR/config.example.toml" "$SMOKE_CONFIG" 2>/dev/null || true

echo "[smoke] Starting menubar app..."
"$PYTHON" "$SCRIPT_DIR/dictation.py" menubar --config "$SMOKE_CONFIG" >/dev/null 2>&1 &
PID=$!

sleep 3

if kill -0 "$PID" 2>/dev/null; then
  echo "[smoke] Startup: passed (PID $PID)"
  kill -9 "$PID" 2>/dev/null
  wait "$PID" 2>/dev/null || true
  sleep 0.5
else
  wait "$PID" 2>/dev/null
  EXIT_CODE=$?
  echo "[smoke] FAIL: app exited with code $EXIT_CODE within 3 seconds"
  rm -f "$SMOKE_CONFIG"
  exit 1
fi

# Step 4: Dictation pipeline test — record, transcribe, clean
echo "[smoke] Pipeline test..."
"$PYTHON" -c "
import sys, os
os.chdir('$SCRIPT_DIR')

# Test recorder: start/stop a brief recording
from recorder import Recorder
rec = Recorder(sample_rate=16000)
rec.start()
import time; time.sleep(0.5)
result = rec.stop()
assert result is not None, 'Recorder returned None'
assert result.duration_seconds > 0, 'Recording has zero duration'
assert len(result.audio_bytes) > 0, 'Recording has zero bytes'
print(f'  Recorder: {result.duration_seconds:.2f}s, {len(result.audio_bytes)} bytes')

# Test transcriber creation (don't actually call API — just verify wiring)
from pathlib import Path
from dictation import load_config
from transcriber import create_transcriber
config = load_config(Path('$SMOKE_CONFIG'))
t = create_transcriber(config.whisper)
assert t is not None, 'Transcriber is None'
t.close()
print(f'  Transcriber: {config.whisper.provider} created OK')

# Test cleaner
from cleaner import TextCleaner
c = TextCleaner(text_commands=True)
cleaned = c.clean('Hello um period new line world')
assert 'um' not in cleaned.lower(), 'Filler not removed'
c.close()
print(f'  Cleaner: \"{cleaned.strip()}\"')

print('[smoke] Pipeline: passed')
" 2>&1

if [ $? -ne 0 ]; then
  echo "[smoke] FAIL: pipeline test failed"
  rm -f "$SMOKE_CONFIG"
  exit 1
fi

rm -f "$SMOKE_CONFIG"
echo "[smoke] All checks passed."
