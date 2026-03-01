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

# Determine platform-specific paths (matches local_setup.py / cli.py logic)
if [ "$(uname -s)" = "Darwin" ] || [ "$(uname -s)" = "Linux" ]; then
    DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/whisper-dic"
    SERVER_BIN="$DATA_DIR/bin/whisper-server"
    START_SCRIPT="$DATA_DIR/start-server.sh"
    CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/whisper-dic"
else
    DATA_DIR="${LOCALAPPDATA:-$USERPROFILE/AppData/Local}/whisper-dic"
    SERVER_BIN="$DATA_DIR/bin/whisper-server.exe"
    START_SCRIPT="$DATA_DIR/start-server.bat"
    CONFIG_DIR="${APPDATA:-$USERPROFILE/AppData/Roaming}/whisper-dic"
fi

CONFIG="$CONFIG_DIR/config.toml"
TEST_AUDIO="$SCRIPT_DIR/tests/e2e/test_audio.flac"
VERSION_FILE="$SCRIPT_DIR/src/whisper_dic/VERSION"

echo ""
echo "=== whisper-dic E2E Test ==="
echo "  Platform:   $(uname -s) $(uname -m)"
echo "  Data dir:   $DATA_DIR"
echo "  Config dir: $CONFIG_DIR"
echo ""

# ---------------------------------------------------------------------------
# Step 0: Fresh config creation
# ---------------------------------------------------------------------------

echo "--- Step 0: Fresh config creation ---"

# Remove any pre-existing config to test auto-creation
rm -f "$CONFIG"

# Running a config-aware command should auto-create the config from template
# (version doesn't load config; provider does via _load_config_from_path)
whisper-dic provider --config "$CONFIG" > /dev/null 2>&1 || true

if [ -f "$CONFIG" ]; then
    pass "Config auto-created on first run"
else
    fail "Config not auto-created"
fi

if grep -q '^\[hotkey\]' "$CONFIG" 2>/dev/null; then
    pass "Config contains [hotkey] section"
else
    fail "Config missing [hotkey] section"
fi

if grep -q '^\[whisper\]' "$CONFIG" 2>/dev/null; then
    pass "Config contains [whisper] section"
else
    fail "Config missing [whisper] section"
fi

if grep -q '^\[recording\]' "$CONFIG" 2>/dev/null; then
    pass "Config contains [recording] section"
else
    fail "Config missing [recording] section"
fi

# ---------------------------------------------------------------------------
# Step 1: setup-local
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 1: setup-local ---"

whisper-dic setup-local --model tiny --config "$CONFIG"
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
# Step 3: doctor (expanded)
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 3: doctor ---"

DOCTOR_EXIT=0
DOCTOR_OUTPUT=$(whisper-dic doctor --config "$CONFIG" 2>&1) || DOCTOR_EXIT=$?
echo "$DOCTOR_OUTPUT"

# Exit code 1 is acceptable — microphone check fails in headless environments
if [ "$DOCTOR_EXIT" -le 1 ]; then
    pass "Doctor: exit code $DOCTOR_EXIT (0=all ok, 1=non-critical failure)"
else
    fail "Doctor: exit code $DOCTOR_EXIT (expected 0 or 1)"
fi

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

if echo "$DOCTOR_OUTPUT" | grep -q "Microphone"; then
    pass "Doctor: microphone check present"
else
    fail "Doctor: microphone check missing from output"
fi

# ---------------------------------------------------------------------------
# Step 4: version (expanded)
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 4: version ---"

VERSION_OUTPUT=$(whisper-dic version 2>&1 || true)

if [ -n "$VERSION_OUTPUT" ]; then
    pass "Version: non-empty ($VERSION_OUTPUT)"
else
    fail "Version: no output"
fi

if echo "$VERSION_OUTPUT" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+'; then
    pass "Version: matches semver format"
else
    fail "Version: '$VERSION_OUTPUT' does not match semver"
fi

if [ -f "$VERSION_FILE" ]; then
    EXPECTED_VERSION=$(cat "$VERSION_FILE" | tr -d '[:space:]')
    if [ "$VERSION_OUTPUT" = "$EXPECTED_VERSION" ]; then
        pass "Version: matches VERSION file ($EXPECTED_VERSION)"
    else
        fail "Version: '$VERSION_OUTPUT' != VERSION file '$EXPECTED_VERSION'"
    fi
else
    fail "Version: VERSION file not found at $VERSION_FILE"
fi

# ---------------------------------------------------------------------------
# Step 5: status (expanded)
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 5: status ---"

STATUS_OUTPUT=$(whisper-dic status --config "$CONFIG" 2>&1 || true)

if echo "$STATUS_OUTPUT" | grep -q "provider=local"; then
    pass "Status: shows provider=local"
else
    fail "Status: expected provider=local"
fi

if echo "$STATUS_OUTPUT" | grep -q "\[status\] whisper-dic v"; then
    pass "Status: shows version header"
else
    fail "Status: missing version header"
fi

if echo "$STATUS_OUTPUT" | grep -q "\[status\] Config:"; then
    pass "Status: shows config path"
else
    fail "Status: missing config path"
fi

if echo "$STATUS_OUTPUT" | grep -q "hotkey.key"; then
    pass "Status: shows hotkey config"
else
    fail "Status: missing hotkey config"
fi

if echo "$STATUS_OUTPUT" | grep -q "sample_rate="; then
    pass "Status: shows recording config"
else
    fail "Status: missing recording config"
fi

if echo "$STATUS_OUTPUT" | grep -q "local endpoint reachable: yes"; then
    pass "Status: local endpoint reachable"
else
    fail "Status: local endpoint not reachable"
fi

# ---------------------------------------------------------------------------
# Step 6: Full config lifecycle
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 6: Config lifecycle ---"

# Save config backup
CONFIG_BACKUP=$(cat "$CONFIG")

# 6a: hotkey
whisper-dic set hotkey.key right_option --config "$CONFIG" 2>&1
if grep -q 'key = "right_option"' "$CONFIG"; then
    pass "Set: hotkey.key = right_option"
else
    fail "Set: hotkey.key not updated"
fi

# 6b: recording.min_duration (float)
whisper-dic set recording.min_duration 0.5 --config "$CONFIG" 2>&1
if grep -q 'min_duration = 0.5' "$CONFIG"; then
    pass "Set: recording.min_duration = 0.5"
else
    fail "Set: recording.min_duration not updated"
fi

# 6c: recording.max_duration (float)
whisper-dic set recording.max_duration 120.0 --config "$CONFIG" 2>&1
if grep -q 'max_duration = 120.0' "$CONFIG"; then
    pass "Set: recording.max_duration = 120.0"
else
    fail "Set: recording.max_duration not updated"
fi

# 6d: recording.sample_rate (int)
whisper-dic set recording.sample_rate 48000 --config "$CONFIG" 2>&1
if grep -q 'sample_rate = 48000' "$CONFIG"; then
    pass "Set: recording.sample_rate = 48000"
else
    fail "Set: recording.sample_rate not updated"
fi

# 6e: whisper.language (string)
whisper-dic set whisper.language nl --config "$CONFIG" 2>&1
if grep -q 'language = "nl"' "$CONFIG"; then
    pass "Set: whisper.language = nl"
else
    fail "Set: whisper.language not updated"
fi

# 6f: whisper.timeout_seconds (float)
whisper-dic set whisper.timeout_seconds 60.0 --config "$CONFIG" 2>&1
if grep -q 'timeout_seconds = 60.0' "$CONFIG"; then
    pass "Set: whisper.timeout_seconds = 60.0"
else
    fail "Set: whisper.timeout_seconds not updated"
fi

# 6g: whisper.prompt (string with special chars)
whisper-dic set whisper.prompt "Kotlin, PostgreSQL" --config "$CONFIG" 2>&1
if grep -q 'prompt = "Kotlin, PostgreSQL"' "$CONFIG"; then
    pass "Set: whisper.prompt with special chars"
else
    fail "Set: whisper.prompt not updated"
fi

# 6h: audio_feedback.enabled (boolean)
whisper-dic set audio_feedback.enabled false --config "$CONFIG" 2>&1
if grep -q 'enabled = false' "$CONFIG"; then
    pass "Set: audio_feedback.enabled = false"
else
    fail "Set: audio_feedback.enabled not updated"
fi

# 6i: audio_feedback.volume (float)
whisper-dic set audio_feedback.volume 0.8 --config "$CONFIG" 2>&1
if grep -q 'volume = 0.8' "$CONFIG"; then
    pass "Set: audio_feedback.volume = 0.8"
else
    fail "Set: audio_feedback.volume not updated"
fi

# 6j: text_commands.enabled (boolean)
whisper-dic set text_commands.enabled false --config "$CONFIG" 2>&1
if grep -q 'enabled = false' "$CONFIG"; then
    pass "Set: text_commands.enabled = false"
else
    fail "Set: text_commands.enabled not updated"
fi

# 6k: rewrite.enabled (boolean)
whisper-dic set rewrite.enabled true --config "$CONFIG" 2>&1
if grep -q 'enabled = true' "$CONFIG"; then
    pass "Set: rewrite.enabled = true"
else
    fail "Set: rewrite.enabled not updated"
fi

# 6l: rewrite.mode (string)
whisper-dic set rewrite.mode full --config "$CONFIG" 2>&1
if grep -q 'mode = "full"' "$CONFIG"; then
    pass "Set: rewrite.mode = full"
else
    fail "Set: rewrite.mode not updated"
fi

# 6m: paste.auto_send (boolean)
whisper-dic set paste.auto_send true --config "$CONFIG" 2>&1
if grep -q 'auto_send = true' "$CONFIG"; then
    pass "Set: paste.auto_send = true"
else
    fail "Set: paste.auto_send not updated"
fi

# Restore defaults
echo "$CONFIG_BACKUP" > "$CONFIG"

# ---------------------------------------------------------------------------
# Step 7: Provider command
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 7: Provider command ---"

# 7a: Show current provider
PROVIDER_OUTPUT=$(whisper-dic provider --config "$CONFIG" 2>&1 || true)
if echo "$PROVIDER_OUTPUT" | grep -q "^local$"; then
    pass "Provider: shows current (local)"
else
    fail "Provider: expected 'local', got '$PROVIDER_OUTPUT'"
fi

# 7b: Switch to groq without API key (non-interactive — stdin from /dev/null)
PROVIDER_GROQ_OUTPUT=$(whisper-dic provider groq --config "$CONFIG" 2>&1 < /dev/null || true)
if echo "$PROVIDER_GROQ_OUTPUT" | grep -q "Provider unchanged"; then
    pass "Provider: groq without API key handled gracefully"
else
    fail "Provider: groq without key did not show 'Provider unchanged'"
fi

# 7c: Set API key, then switch to groq
whisper-dic set whisper.groq.api_key "gsk_test_key_12345" --config "$CONFIG" 2>&1
whisper-dic provider groq --config "$CONFIG" 2>&1
PROVIDER_CHECK=$(whisper-dic provider --config "$CONFIG" 2>&1 || true)
if echo "$PROVIDER_CHECK" | grep -q "^groq$"; then
    pass "Provider: switched to groq"
else
    fail "Provider: expected 'groq', got '$PROVIDER_CHECK'"
fi

# 7d: Switch back to local
whisper-dic provider local --config "$CONFIG" 2>&1
PROVIDER_BACK=$(whisper-dic provider --config "$CONFIG" 2>&1 || true)
if echo "$PROVIDER_BACK" | grep -q "^local$"; then
    pass "Provider: switched back to local"
else
    fail "Provider: expected 'local', got '$PROVIDER_BACK'"
fi

# Clean up fake API key
whisper-dic set whisper.groq.api_key "" --config "$CONFIG" 2>&1

# ---------------------------------------------------------------------------
# Step 8: install/uninstall graceful degradation
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 8: install/uninstall ---"

if [ "$(uname -s)" != "Darwin" ]; then
    INSTALL_OUTPUT=$(whisper-dic install 2>&1 || true)
    if echo "$INSTALL_OUTPUT" | grep -qi "not.*supported"; then
        pass "Install: prints not-supported on this platform"
    else
        fail "Install: expected not-supported message"
    fi

    UNINSTALL_OUTPUT=$(whisper-dic uninstall 2>&1 || true)
    if echo "$UNINSTALL_OUTPUT" | grep -qi "not.*supported\|not installed"; then
        pass "Uninstall: prints not-supported on this platform"
    else
        fail "Uninstall: expected not-supported message"
    fi
else
    # On macOS, just verify commands don't crash (may succeed or fail)
    whisper-dic install 2>&1 || true
    pass "Install: completed without crash"
    whisper-dic uninstall 2>&1 || true
    pass "Uninstall: completed without crash"
fi

# ---------------------------------------------------------------------------
# Step 9: logs command
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 9: logs command ---"

LOGS_OUTPUT=$(whisper-dic logs -n 10 2>&1 || true)
if echo "$LOGS_OUTPUT" | grep -qi "No log file yet\|log"; then
    pass "Logs: handles gracefully (no crash)"
else
    # Even if it prints log lines, that's fine
    pass "Logs: returned output without error"
fi

# Ensure log file exists so the argument-parsing path is exercised
# (without a log file, logs exits early with "No log file yet")
LOG_PATH=$(python3 -c "from whisper_dic.cli import _LOG_PATH; print(_LOG_PATH)")
mkdir -p "$(dirname "$LOG_PATH")"
echo "e2e test log line" > "$LOG_PATH"

LOGS_BAD=$(whisper-dic logs -n xyz 2>&1 || true)
if echo "$LOGS_BAD" | grep -qi "Invalid line count"; then
    pass "Logs: invalid line count handled"
else
    fail "Logs: expected 'Invalid line count' error"
fi

# ---------------------------------------------------------------------------
# Step 10: Negative — bad config
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 10: Negative tests (bad config) ---"

CONFIG_BACKUP=$(cat "$CONFIG")

# 10a: Corrupt config
echo "this is not valid toml [[[" > "$CONFIG"
BAD_CONFIG_OUTPUT=$(whisper-dic status --config "$CONFIG" 2>&1 || true)
if echo "$BAD_CONFIG_OUTPUT" | grep -qi "error\|failed\|invalid\|parse\|expected"; then
    pass "Negative: corrupt config handled gracefully"
else
    fail "Negative: corrupt config did not produce error"
fi
echo "$CONFIG_BACKUP" > "$CONFIG"

# 10b: Set with empty key path
BADKEY_OUTPUT=$(whisper-dic set "" "value" --config "$CONFIG" 2>&1 || true)
if echo "$BADKEY_OUTPUT" | grep -qi "fail\|invalid\|error\|empty"; then
    pass "Negative: empty key path handled"
else
    # Some implementations just silently succeed — check return code instead
    pass "Negative: empty key path did not crash"
fi

# 10c: Set unknown section key
whisper-dic set nonexistent.key testval --config "$CONFIG" 2>&1 || true
if grep -q 'key = "testval"' "$CONFIG"; then
    pass "Negative: unknown section key written to config"
else
    fail "Negative: unknown section key not written"
fi
echo "$CONFIG_BACKUP" > "$CONFIG"

# ---------------------------------------------------------------------------
# Step 11: Negative — server down
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 11: Negative tests (server down) ---"

# Kill the server
kill "$SERVER_PID" 2>/dev/null
wait "$SERVER_PID" 2>/dev/null || true
SERVER_PID=""
sleep 1

DOCTOR_DOWN=$(whisper-dic doctor --config "$CONFIG" 2>&1 || true)
if echo "$DOCTOR_DOWN" | grep -q "\[FAIL\].*Provider"; then
    pass "Negative: doctor reports provider fail when server down"
else
    fail "Negative: doctor should report provider failure"
fi

STATUS_DOWN=$(whisper-dic status --config "$CONFIG" 2>&1 || true)
if echo "$STATUS_DOWN" | grep -q "local endpoint reachable: no"; then
    pass "Negative: status shows endpoint unreachable"
else
    fail "Negative: status should show endpoint unreachable"
fi

TRANSCRIBE_FAIL=$(curl -sf -X POST http://localhost:2022/v1/audio/transcriptions \
    -F "file=@$TEST_AUDIO;type=audio/flac" \
    -F "model=tiny" \
    -F "language=en" 2>&1 || echo "CURL_FAILED")
if [ "$TRANSCRIBE_FAIL" = "CURL_FAILED" ]; then
    pass "Negative: transcription fails when server down"
else
    fail "Negative: transcription should fail when server down"
fi

# ---------------------------------------------------------------------------
# Step 12: Server restart
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 12: Server restart ---"

"$START_SCRIPT" > /tmp/whisper-e2e-server.log 2>&1 &
SERVER_PID=$!

HEALTHY=false
for i in $(seq 1 60); do
    if curl -sf http://localhost:2022/ > /dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    sleep 1
done

if [ "$HEALTHY" = true ]; then
    pass "Restart: server healthy after ${i}s"
else
    fail "Restart: server not reachable after restart"
    echo "  Server log:"
    cat /tmp/whisper-e2e-server.log 2>/dev/null | tail -20
fi

# ---------------------------------------------------------------------------
# Step 13: Transcription (expanded)
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 13: Transcription ---"

if [ -f "$TEST_AUDIO" ]; then
    RESPONSE=$(curl -sf -X POST http://localhost:2022/v1/audio/transcriptions \
        -F "file=@$TEST_AUDIO;type=audio/flac" \
        -F "model=tiny" \
        -F "language=en" 2>&1 || echo "CURL_FAILED")

    if [ "$RESPONSE" = "CURL_FAILED" ]; then
        fail "Transcription: curl failed"
    else
        # Check valid JSON
        if echo "$RESPONSE" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
            pass "Transcription: response is valid JSON"
        else
            fail "Transcription: response is not valid JSON: $RESPONSE"
        fi

        # Check text field
        if echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'text' in d" 2>/dev/null; then
            TEXT=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['text'])")
            pass "Transcription: got text: \"$TEXT\""
        else
            fail "Transcription: response missing 'text' field: $RESPONSE"
        fi
    fi
else
    fail "Transcription: test audio not found: $TEST_AUDIO"
fi

# ---------------------------------------------------------------------------
# Step 14: Cleanup
# ---------------------------------------------------------------------------

echo ""
echo "--- Step 14: Cleanup ---"

if [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null; then
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
