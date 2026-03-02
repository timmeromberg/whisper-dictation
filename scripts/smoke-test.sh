#!/bin/bash
# Smoke test: lint, compile, startup, and dictation pipeline check.
# Usage: ./scripts/smoke-test.sh
# Exit 0 = pass, Exit 1 = fail

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python"
export PYTHONPATH="$SCRIPT_DIR/src"
# Hard guard: smoke tests must never emit real clipboard/keyboard side effects.
export WHISPER_DIC_SMOKE_NO_INPUT=1

if [ ! -x "$PYTHON" ]; then
  echo "[smoke] SKIP: no .venv found (smoke test requires venv)"
  exit 0
fi

# Step 1: Compile check
echo "[smoke] Compile check..."
if ! "$PYTHON" -m compileall -q "$SCRIPT_DIR/src/whisper_dic/"; then
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
pkill -f "whisper_dic.cli menubar.*--config.*/tmp/smoke" 2>/dev/null || true
sleep 0.5

SMOKE_CONFIG="/tmp/smoke-test-whisper-dic.toml"
cp "$SCRIPT_DIR/src/whisper_dic/config.example.toml" "$SMOKE_CONFIG" 2>/dev/null || true

SMOKE_LOG="/tmp/smoke-menubar-$$.log"
echo "[smoke] Starting menubar app..."
"$PYTHON" -m whisper_dic.cli menubar --config "$SMOKE_CONFIG" >"$SMOKE_LOG" 2>&1 &
PID=$!

sleep 3

SMOKE_STARTUP_SKIPPED=0
if kill -0 "$PID" 2>/dev/null; then
  echo "[smoke] Startup: passed (PID $PID)"
  kill -9 "$PID" 2>/dev/null
  wait "$PID" 2>/dev/null || true
  sleep 0.5
elif grep -q "already running" "$SMOKE_LOG" 2>/dev/null; then
  echo "[smoke] Startup: skipped (another instance running)"
  SMOKE_STARTUP_SKIPPED=1
else
  wait "$PID" 2>/dev/null
  EXIT_CODE=$?
  echo "[smoke] FAIL: app exited with code $EXIT_CODE within 3 seconds"
  cat "$SMOKE_LOG" 2>/dev/null
  rm -f "$SMOKE_CONFIG" "$SMOKE_LOG"
  exit 1
fi
rm -f "$SMOKE_LOG"

# Step 4: Dictation pipeline test — record, transcribe, clean
echo "[smoke] Pipeline test..."
export WHISPER_DIC_SMOKE_ALLOW_RECORDER_SKIP="$SMOKE_STARTUP_SKIPPED"
"$PYTHON" -c "
import os
import sys

# Test recorder: start/stop a brief recording (retry for transient stream startup issues)
from whisper_dic.recorder import Recorder
import time
result = None
last_error = None
for _attempt in range(3):
    rec = Recorder(sample_rate=16000)
    try:
        rec.start()
        time.sleep(0.5)
        result = rec.stop()
    except Exception as exc:
        last_error = exc
        result = None
    if result is not None and result.duration_seconds > 0 and len(result.audio_bytes) > 0:
        break
    time.sleep(0.2)
allow_skip = os.environ.get('WHISPER_DIC_SMOKE_ALLOW_RECORDER_SKIP', '0') == '1'
if result is None:
    if allow_skip:
        print('  Recorder: skipped (device busy while another instance is running)')
    else:
        raise AssertionError(f'Recorder returned None after retries (last_error={last_error})')
else:
    assert result.duration_seconds > 0, 'Recording has zero duration'
    assert len(result.audio_bytes) > 0, 'Recording has zero bytes'
    print(f'  Recorder: {result.duration_seconds:.2f}s, {len(result.audio_bytes)} bytes')

# Test transcriber creation (don't actually call API — just verify wiring)
from pathlib import Path
from whisper_dic.config import load_config
from whisper_dic.transcriber import create_transcriber
config = load_config(Path('$SMOKE_CONFIG'))
t = create_transcriber(config.whisper)
assert t is not None, 'Transcriber is None'
t.close()
print(f'  Transcriber: {config.whisper.provider} created OK')

# Test cleaner
from whisper_dic.cleaner import TextCleaner
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
if [ "$SMOKE_STARTUP_SKIPPED" -eq 1 ]; then
  echo "[smoke] Dictation flow: skipped (device busy while another instance is running)"
else
  set +e
  FLOW_OUT=$("$PYTHON" -c "
import os, sys, time, threading
from pathlib import Path
from whisper_dic.config import load_config
from whisper_dic.dictation import DictationApp

config = load_config(Path('$SMOKE_CONFIG'))
config.audio_feedback.volume = 0.0

app = DictationApp(config)
app.paster.paste = lambda text, auto_send=False, app_id=None: None

states = []
app.on_state_change = lambda state, text: states.append((state, text))

app._on_hold_start()
allow_skip = os.environ.get('WHISPER_DIC_SMOKE_ALLOW_RECORDER_SKIP', '0') == '1'
if app.recorder._stream is None:
    if allow_skip:
        app.stop()
        print('SKIP')
        raise SystemExit(0)
    raise AssertionError('Recorder stream not started')
time.sleep(0.5)

app.transcriber.transcribe = lambda audio_bytes, **kw: 'smoke test hello world'
app._on_hold_end()
time.sleep(1.0)

state_names = [s[0] for s in states]
assert 'recording' in state_names, f'Never entered recording state: {state_names}'
if 'idle' not in state_names:
    if allow_skip:
        app.stop()
        print('SKIP')
        raise SystemExit(0)
    raise AssertionError(f'Never returned to idle: {state_names}')

app.stop()
print('OK')
" 2>&1)
  FLOW_RC=$?
  set -e
  if [ $FLOW_RC -eq 0 ] && echo "$FLOW_OUT" | grep -q "^OK$"; then
    echo "[smoke] Dictation flow: passed (recording → transcribing → idle)"
  elif [ $FLOW_RC -eq 0 ] && echo "$FLOW_OUT" | grep -q "^SKIP$"; then
    echo "[smoke] Dictation flow: skipped (device busy while another instance is running)"
  else
    echo "[smoke] FAIL: dictation flow test failed"
    echo "$FLOW_OUT"
    rm -f "$SMOKE_CONFIG"
    exit 1
  fi
fi

# Step 6: CLI argument parsing test
echo "[smoke] CLI test..."
"$PYTHON" -m whisper_dic.cli --help >/dev/null 2>&1
"$PYTHON" -m whisper_dic.cli status --help >/dev/null 2>&1
"$PYTHON" -m whisper_dic.cli set --help >/dev/null 2>&1
echo "[smoke] CLI: passed"

# Step 7: Text commands and cleaner coverage
echo "[smoke] Text commands test..."
"$PYTHON" -c "
from whisper_dic.cleaner import TextCleaner

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
from whisper_dic.config import load_config

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
if [ "$SMOKE_STARTUP_SKIPPED" -eq 1 ]; then
  echo "[smoke] Error path: skipped (device busy while another instance is running)"
else
  ERROR_OUT=$("$PYTHON" -c "
import sys, time
from pathlib import Path
from whisper_dic.config import load_config
from whisper_dic.dictation import DictationApp

config = load_config(Path('$SMOKE_CONFIG'))
config.audio_feedback.volume = 0.0

app = DictationApp(config)
app.paster.paste = lambda text, auto_send=False, app_id=None: None

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
print('OK')
" 2>&1)
  if echo "$ERROR_OUT" | grep -q "^OK$"; then
    echo "[smoke] Error path: passed (error caught, app recovered)"
  else
    echo "[smoke] FAIL: error path test failed"
    echo "$ERROR_OUT"
    rm -f "$SMOKE_CONFIG"
    exit 1
  fi
fi

# Step 10: Auto-send flow test
echo "[smoke] Auto-send test..."
if [ "$SMOKE_STARTUP_SKIPPED" -eq 1 ]; then
  echo "[smoke] Auto-send: skipped (device busy while another instance is running)"
else
  SEND_OUT=$("$PYTHON" -c "
import sys, time
from pathlib import Path
from whisper_dic.config import load_config
from whisper_dic.dictation import DictationApp

config = load_config(Path('$SMOKE_CONFIG'))
config.audio_feedback.volume = 0.0
config.paste.auto_send = True

app = DictationApp(config)

paste_calls = []
def mock_paste(text, auto_send=False, app_id=None):
    paste_calls.append({'text': text, 'auto_send': auto_send})
app.paster.paste = mock_paste

app.transcriber.transcribe = lambda audio_bytes, **kw: 'hello world'

app._on_hold_start()
time.sleep(0.5)
app._on_hold_end()
time.sleep(2.0)

assert len(paste_calls) > 0, f'Paster.paste was never called'
assert paste_calls[0]['auto_send'] is True, f'auto_send not True: {paste_calls[0]}'

app.stop()
print('OK')
" 2>&1)
  if echo "$SEND_OUT" | grep -q "^OK$"; then
    echo "[smoke] Auto-send: passed (auto_send=True propagated to paster)"
  else
    echo "[smoke] FAIL: auto-send test failed"
    echo "$SEND_OUT"
    rm -f "$SMOKE_CONFIG"
    exit 1
  fi
fi

# Step 11: Provider switch test
echo "[smoke] Provider switch test..."
"$PYTHON" -c "
import sys, shutil, tempfile
from pathlib import Path
from whisper_dic.config import load_config, set_config_value
from whisper_dic.dictation import DictationApp
from whisper_dic.transcriber import create_transcriber, LocalWhisperTranscriber, GroqWhisperTranscriber

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

import os
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
