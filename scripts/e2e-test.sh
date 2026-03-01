#!/bin/bash
# End-to-end test: onboarding + transcription pipeline.
# Runs in Docker (Linux), GitHub Actions (macOS/Windows), or locally.
# Usage: ./scripts/e2e-test.sh
# Exit 0 = pass, Exit 1 = fail

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASSED=0
FAILED=0
SERVER_PID=""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

pass() { echo "  [PASS] $1"; PASSED=$((PASSED + 1)); }
fail() { echo "  [FAIL] $1"; FAILED=$((FAILED + 1)); }

cleanup() {
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Determine data dir (matches local_setup.py logic)
if [ "$(uname -s)" = "Darwin" ] || [ "$(uname -s)" = "Linux" ]; then
    DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/whisper-dic"
    SERVER_BIN="$DATA_DIR/bin/whisper-server"
    START_SCRIPT="$DATA_DIR/start-server.sh"
else
    DATA_DIR="${LOCALAPPDATA:-$USERPROFILE/AppData/Local}/whisper-dic"
    SERVER_BIN="$DATA_DIR/bin/whisper-server.exe"
    START_SCRIPT="$DATA_DIR/start-server.bat"
fi

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/whisper-dic"
CONFIG="$CONFIG_DIR/config.toml"
TEST_AUDIO="$SCRIPT_DIR/tests/e2e/test_audio.flac"

# Ensure config exists (setup-local needs it)
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG" ]; then
    cp "$SCRIPT_DIR/src/whisper_dic/config.example.toml" "$CONFIG"
fi

echo ""
echo "=== whisper-dic E2E Test ==="
echo "  Platform: $(uname -s) $(uname -m)"
echo "  Data dir: $DATA_DIR"
echo "  Config:   $CONFIG"
echo ""

# ---------------------------------------------------------------------------
# Step 1: setup-local
# ---------------------------------------------------------------------------

echo "--- Step 1: setup-local ---"

whisper-dic setup-local --model tiny
echo ""

if [ -f "$SERVER_BIN" ]; then
    pass "Server binary exists: $SERVER_BIN"
else
    fail "Server binary not found: $SERVER_BIN"
fi

if ls "$DATA_DIR"/models/ggml-tiny.bin >/dev/null 2>&1; then
    pass "Model downloaded: ggml-tiny.bin"
else
    fail "Model not found: $DATA_DIR/models/ggml-tiny.bin"
fi

if [ -f "$START_SCRIPT" ]; then
    pass "Start script created: $START_SCRIPT"
else
    fail "Start script not found: $START_SCRIPT"
fi

# ---------------------------------------------------------------------------
# Step 2: Start server
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 2: Start server ---"

"$START_SCRIPT" > /tmp/whisper-e2e-server.log 2>&1 &
SERVER_PID=$!
echo "  Server PID: $SERVER_PID"

# Poll for health
HEALTHY=false
for i in $(seq 1 60); do
    if curl -sf http://localhost:2022/ > /dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    sleep 1
done

if [ "$HEALTHY" = true ]; then
    pass "Server healthy after ${i}s"
else
    fail "Server not reachable after 60s"
    echo "  Server log:"
    cat /tmp/whisper-e2e-server.log 2>/dev/null | tail -20
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 3: doctor
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 3: doctor ---"

DOCTOR_OUTPUT=$(whisper-dic doctor 2>&1 || true)
echo "$DOCTOR_OUTPUT"

if echo "$DOCTOR_OUTPUT" | grep -q "\[ok\].*Config file"; then
    pass "Doctor: config check passed"
else
    fail "Doctor: config check failed"
fi

if echo "$DOCTOR_OUTPUT" | grep -q "\[ok\].*Provider"; then
    pass "Doctor: provider check passed"
else
    fail "Doctor: provider check failed"
fi

if echo "$DOCTOR_OUTPUT" | grep -q "\[ok\].*Local install"; then
    pass "Doctor: local install check passed"
else
    fail "Doctor: local install check failed"
fi

# ---------------------------------------------------------------------------
# Step 4: CLI commands
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 4: CLI commands ---"

STATUS_OUTPUT=$(whisper-dic status 2>&1 || true)
if echo "$STATUS_OUTPUT" | grep -q "provider=local"; then
    pass "Status: shows provider=local"
else
    fail "Status: expected provider=local"
fi

whisper-dic set whisper.language nl 2>&1
LANG_CHECK=$(whisper-dic status 2>&1 || true)
if echo "$LANG_CHECK" | grep -q "language=nl"; then
    pass "Set: language changed to nl"
else
    fail "Set: language change not reflected"
fi

# Restore
whisper-dic set whisper.language en 2>&1

VERSION_OUTPUT=$(whisper-dic version 2>&1 || true)
if [ -n "$VERSION_OUTPUT" ]; then
    pass "Version: $VERSION_OUTPUT"
else
    fail "Version: no output"
fi

# ---------------------------------------------------------------------------
# Step 5: Transcription
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 5: Transcription ---"

if [ -f "$TEST_AUDIO" ]; then
    RESPONSE=$(curl -sf -X POST http://localhost:2022/v1/audio/transcriptions \
        -F "file=@$TEST_AUDIO;type=audio/flac" \
        -F "model=tiny" \
        -F "language=en" 2>&1 || echo "CURL_FAILED")

    if [ "$RESPONSE" = "CURL_FAILED" ]; then
        fail "Transcription: curl failed"
    elif echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'text' in d" 2>/dev/null; then
        TEXT=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['text'])")
        pass "Transcription: got response: \"$TEXT\""
    else
        fail "Transcription: unexpected response: $RESPONSE"
    fi
else
    fail "Transcription: test audio not found: $TEST_AUDIO"
fi

# ---------------------------------------------------------------------------
# Step 6: Stop server
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 6: Cleanup ---"

if kill "$SERVER_PID" 2>/dev/null; then
    wait "$SERVER_PID" 2>/dev/null || true
    SERVER_PID=""
    pass "Server stopped"
else
    fail "Server already stopped"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [ "$FAILED" -gt 0 ]; then
    exit 1
fi

echo ""
echo "All E2E tests passed."
exit 0
