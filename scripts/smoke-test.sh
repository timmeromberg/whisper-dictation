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

# Step 5: Dictation flow test — simulate hold-to-dictate via DictationApp
echo "[smoke] Dictation flow test..."
"$PYTHON" -c "
import sys, os, time, threading
os.chdir('$SCRIPT_DIR')
from pathlib import Path
from dictation import DictationApp, load_config

config = load_config(Path('$SMOKE_CONFIG'))
# Disable audio feedback to keep it quiet
config.audio_feedback.volume = 0.0

app = DictationApp(config)

# Mock paster to prevent actual Cmd+V into the terminal
app.paster.paste = lambda text, auto_send=False: None

# Track state changes
states = []
app.on_state_change = lambda state, text: states.append((state, text))

# Simulate hold start (starts recording)
app._on_hold_start()
assert app.recorder._stream is not None, 'Recorder stream not started'
print('  Hold start: recording active')

time.sleep(0.5)

# Simulate hold end (stops recording, triggers pipeline)
# Patch transcriber to avoid real API call — return canned text
app.transcriber.transcribe = lambda audio_bytes, **kw: 'smoke test hello world'
app._on_hold_end()

# Wait briefly for pipeline thread to finish
time.sleep(1.0)

# Verify pipeline ran (state should have gone through transcribing → idle)
state_names = [s[0] for s in states]
assert 'recording' in state_names, f'Never entered recording state: {state_names}'
assert 'idle' in state_names, f'Never returned to idle: {state_names}'
print(f'  Hold end: states = {state_names}')

# Verify the cleaned text was produced (pasting will fail without accessibility, that's OK)
final_texts = [s[1] for s in states if s[1]]
print(f'  Pipeline output: {final_texts}')

app.stop()
print('[smoke] Dictation flow: passed')
" 2>&1

if [ $? -ne 0 ]; then
  echo "[smoke] FAIL: dictation flow test failed"
  rm -f "$SMOKE_CONFIG"
  exit 1
fi

# Step 6: CLI argument parsing test
echo "[smoke] CLI test..."
"$PYTHON" "$SCRIPT_DIR/dictation.py" --help >/dev/null 2>&1
"$PYTHON" "$SCRIPT_DIR/dictation.py" status --help >/dev/null 2>&1
"$PYTHON" "$SCRIPT_DIR/dictation.py" set --help >/dev/null 2>&1
echo "[smoke] CLI: passed"

# Step 7: Text commands and cleaner coverage
echo "[smoke] Text commands test..."
"$PYTHON" -c "
from cleaner import TextCleaner

c = TextCleaner(text_commands=True)

# Punctuation commands
cases = [
    ('Hello period', 'Hello.'),
    ('Hello comma world', 'Hello, world'),
    ('Hello question mark', 'Hello?'),
    ('Hello exclamation mark', 'Hello!'),
    ('Hello exclamation point', 'Hello!'),
    ('Hello semicolon world', 'Hello; world'),
    ('Hello colon world', 'Hello: world'),
    ('Hello full stop', 'Hello.'),
]
for inp, expected in cases:
    got = c.clean(inp)
    assert got == expected, f'{inp!r} => {got!r}, expected {expected!r}'

# Formatting commands
assert '\n\n' in c.clean('Hello new paragraph world')
assert '\n' in c.clean('Hello new line world')
assert '\t' in c.clean('Hello tab world')

# Filler removal
fillers = ['um', 'uh', 'ah', 'erm', 'hmm', 'basically', 'literally', 'actually']
for f in fillers:
    cleaned = c.clean(f'Hello {f} world')
    assert f not in cleaned.lower(), f'Filler {f!r} not removed from {cleaned!r}'

# Multi-word fillers
assert 'you know' not in c.clean('Hello you know world').lower()
assert 'I mean' not in c.clean('Hello I mean world')
assert 'sort of' not in c.clean('Hello sort of world').lower()
assert 'kind of' not in c.clean('Hello kind of world').lower()

# Repeated word removal
assert c.clean('I I think') == 'I think'
assert c.clean('the the world') == 'The world'

# Empty / whitespace input
assert c.clean('') == ''
assert c.clean('   ') == '   '

# Text commands disabled
c_no_cmds = TextCleaner(text_commands=False)
assert 'period' in c_no_cmds.clean('Hello period').lower()

c.close()
c_no_cmds.close()
print('[smoke] Text commands: passed (all cases)')
" 2>&1

if [ $? -ne 0 ]; then
  echo "[smoke] FAIL: text commands test failed"
  rm -f "$SMOKE_CONFIG"
  exit 1
fi

# Step 8: Config edge cases
echo "[smoke] Config test..."
"$PYTHON" -c "
import os, tempfile, tomllib
from pathlib import Path
os.chdir('$SCRIPT_DIR')
from dictation import load_config

# Default config loads without error
config = load_config(Path('$SMOKE_CONFIG'))
assert config.hotkey.key is not None, 'Hotkey key is None'
assert config.recording.sample_rate > 0, 'Invalid sample rate'
assert config.recording.min_duration > 0, 'Invalid min_duration'
assert config.recording.max_duration > config.recording.min_duration, 'max <= min'
assert config.whisper.provider in ('local', 'groq'), f'Unknown provider: {config.whisper.provider}'
print(f'  Default config: OK (provider={config.whisper.provider}, hotkey={config.hotkey.key})')

# Minimal config (empty file) loads with sane defaults
minimal = tempfile.NamedTemporaryFile(suffix='.toml', mode='w', delete=False)
minimal.write('')
minimal.close()
config2 = load_config(Path(minimal.name))
assert config2.hotkey.key is not None, 'Empty config: no default hotkey'
assert config2.recording.sample_rate > 0, 'Empty config: no default sample rate'
os.unlink(minimal.name)
print(f'  Empty config: OK (defaults applied)')

print('[smoke] Config: passed')
" 2>&1

if [ $? -ne 0 ]; then
  echo "[smoke] FAIL: config test failed"
  rm -f "$SMOKE_CONFIG"
  exit 1
fi

# Step 9: Error path test — transcriber failure doesn't crash the app
echo "[smoke] Error path test..."
"$PYTHON" -c "
import sys, os, time
os.chdir('$SCRIPT_DIR')
from pathlib import Path
from dictation import DictationApp, load_config

config = load_config(Path('$SMOKE_CONFIG'))
config.audio_feedback.volume = 0.0

app = DictationApp(config)
app.paster.paste = lambda text, auto_send=False: None

states = []
app.on_state_change = lambda state, text: states.append((state, text))

# Make transcriber raise an exception
def _fail(audio_bytes, **kw):
    raise RuntimeError('Simulated transcription failure')
app.transcriber.transcribe = _fail

app._on_hold_start()
time.sleep(0.5)
app._on_hold_end()
time.sleep(2.0)

state_names = [s[0] for s in states]
assert 'recording' in state_names, f'Never entered recording: {state_names}'
assert 'idle' in state_names, f'Never returned to idle after error: {state_names}'
assert not app.stopped, 'App stopped unexpectedly'

app.stop()
print('[smoke] Error path: passed')
" 2>&1

if [ $? -ne 0 ]; then
  echo "[smoke] FAIL: error path test failed"
  rm -f "$SMOKE_CONFIG"
  exit 1
fi

# Step 10: Auto-send flow test
echo "[smoke] Auto-send test..."
"$PYTHON" -c "
import sys, os, time
os.chdir('$SCRIPT_DIR')
from pathlib import Path
from dictation import DictationApp, load_config

config = load_config(Path('$SMOKE_CONFIG'))
config.audio_feedback.volume = 0.0
config.paste.auto_send = True

app = DictationApp(config)

paste_calls = []
def mock_paste(text, auto_send=False):
    paste_calls.append({'text': text, 'auto_send': auto_send})
app.paster.paste = mock_paste

app.transcriber.transcribe = lambda audio_bytes, **kw: 'hello world'

app._on_hold_start()
time.sleep(0.5)
app._on_hold_end()
time.sleep(2.0)

assert len(paste_calls) > 0, f'Paster.paste was never called'
assert paste_calls[0]['auto_send'] is True, f'auto_send not True: {paste_calls[0]}'
print(f'  Paste called with auto_send={paste_calls[0][\"auto_send\"]}')

app.stop()
print('[smoke] Auto-send: passed')
" 2>&1

if [ $? -ne 0 ]; then
  echo "[smoke] FAIL: auto-send test failed"
  rm -f "$SMOKE_CONFIG"
  exit 1
fi

# Step 11: Provider switch test
echo "[smoke] Provider switch test..."
"$PYTHON" -c "
import sys, os, shutil, tempfile
os.chdir('$SCRIPT_DIR')
from pathlib import Path
from dictation import DictationApp, load_config, set_config_value
from transcriber import create_transcriber, LocalWhisperTranscriber, GroqWhisperTranscriber

tmp = tempfile.NamedTemporaryFile(suffix='.toml', delete=False)
tmp.close()
shutil.copy2('$SMOKE_CONFIG', tmp.name)
cfg_path = Path(tmp.name)

config = load_config(cfg_path)
assert config.whisper.provider == 'local'
t1 = create_transcriber(config.whisper)
assert isinstance(t1, LocalWhisperTranscriber), f'Expected Local, got {type(t1)}'
t1.close()

set_config_value(cfg_path, 'whisper.provider', 'groq')
set_config_value(cfg_path, 'whisper.groq.api_key', 'test-key-smoke')
config2 = load_config(cfg_path)
t2 = create_transcriber(config2.whisper)
assert isinstance(t2, GroqWhisperTranscriber), f'Expected Groq, got {type(t2)}'
t2.close()

set_config_value(cfg_path, 'whisper.provider', 'local')
config3 = load_config(cfg_path)
t3 = create_transcriber(config3.whisper)
assert isinstance(t3, LocalWhisperTranscriber), f'Expected Local after switch back, got {type(t3)}'
t3.close()

os.unlink(tmp.name)
print('[smoke] Provider switch: passed')
" 2>&1

if [ $? -ne 0 ]; then
  echo "[smoke] FAIL: provider switch test failed"
  rm -f "$SMOKE_CONFIG"
  exit 1
fi

rm -f "$SMOKE_CONFIG"
echo "[smoke] All checks passed."
