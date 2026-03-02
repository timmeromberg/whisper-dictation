# Troubleshooting

Start with diagnostics first:

```bash
whisper-dic doctor
```

`doctor` checks config validity, provider reachability, Groq API key (when needed), microphone availability, accessibility permissions (macOS), and local whisper.cpp install.

## View Logs

```bash
# last 200 lines
whisper-dic logs -n 200

# live follow (macOS/Linux)
whisper-dic logs -n f
```

Common log file paths:

- macOS: `~/Library/Logs/whisper-dictation.log`
- Windows: `%LOCALAPPDATA%/whisper-dictation/whisper-dictation.log`

## Hotkey Not Working

- macOS: grant Accessibility permission in **System Settings > Privacy & Security > Accessibility**.
- Confirm no other app is consuming your configured hotkey.
- If using macOS with Python 3.14, switch to Python 3.12/3.13 for stability.
- As a last resort, bypass runtime guard with `WHISPER_DIC_ALLOW_PY314=1` (not recommended).

## Transcription Fails

- Run `whisper-dic doctor`.
- For Groq: verify `whisper.groq.api_key` is set and valid.
- For local: confirm whisper.cpp server is running at your configured URL.
- Check logs for timeout, rate-limit, or connectivity errors.

## Text Does Not Appear at Cursor

- macOS: Accessibility permission is required for simulated paste/shortcuts.
- Windows: try running terminal as Administrator if input simulation is blocked.
- Confirm the target app has keyboard focus and a text field is active.

## No Start/Stop Beep

- Check:

```toml
[audio_feedback]
enabled = true
volume = 0.2
```

- Increase `audio_feedback.volume`.

## Long Dictations Fail Intermittently

- Audio is compressed before upload, and transient network errors are retried automatically.
- If failures continue, test shorter clips and verify network/provider stability.
- Consider local provider to reduce cloud/network dependency.

## Wrong Microphone

- List devices:

```bash
whisper-dic devices
```

- Set explicit device:

```bash
whisper-dic set recording.device "Your Microphone Name"
```

- In macOS menubar mode, switch microphone live from the **Microphone** submenu.

## Local Provider Is Unreachable

- Run:

```bash
whisper-dic setup-local
```

- Start the generated server script.
- Verify endpoint responds:

```bash
curl http://localhost:2022/
```

## Groq Rate Limits or API Errors

- Increase `recording.preview_interval` if live preview is enabled.
- Disable `recording.streaming_preview` temporarily.
- Switch to local provider when doing long sessions.
