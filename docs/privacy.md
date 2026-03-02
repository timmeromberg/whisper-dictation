# Privacy and Data Handling

## Processing Location

Provider choice determines where transcription happens:

- `whisper.provider = "local"`: audio is sent to your own local whisper.cpp server.
- `whisper.provider = "groq"`: audio is sent to Groq's API endpoint.

If `whisper.failover = true`, a failed request can be retried through the other provider.

## AI Rewrite Data Flow

When `[rewrite].enabled = true`:

1. Audio is transcribed first.
2. The resulting text is cleaned locally.
3. Cleaned text is sent to Groq chat completions for rewriting.
4. Rewritten text is pasted.

AI rewrite uses your configured Groq API key (`whisper.groq.api_key`) and selected rewrite model.

## Frontmost App Metadata (Per-App Contexts)

If per-app rewrite contexts are enabled, whisper-dic captures the current frontmost app identifier (bundle ID on macOS, executable name on Windows/Linux) once per dictation.

This identifier is used locally to:

- choose the rewrite context category (coding/chat/email/writing/browser)
- tune paste behavior for known terminal apps

Data handling details:

- Frontmost app ID is not written to `history.json`.
- Frontmost app ID is not sent to the Whisper transcription API.
- Frontmost app ID is not sent directly to the Groq rewrite API.
- Logs may include app ID/context lines for operational debugging.

## Secrets and Config Storage

Config file path:

- macOS/Linux: `~/.config/whisper-dic/config.toml`
- Windows: `%APPDATA%/whisper-dic/config.toml`

Security behavior:

- Config file is created with owner-only permissions where supported.
- API keys are stored in config; keep this file private.

## History Persistence

Transcription history is persisted to:

- macOS/Linux: `~/.config/whisper-dic/history.json`
- Windows: `%APPDATA%/whisper-dic/history.json`

In macOS menubar mode, open **History** to copy recent entries or clear all history.

## Logging

- Logs contain operational events and errors.
- Full transcript text is **not** logged by default.
- Full transcript logging is only enabled when `WHISPER_DIC_LOG_TRANSCRIPTS=1` is set.

Typical log paths:

- macOS: `~/Library/Logs/whisper-dictation.log`
- Windows: `%LOCALAPPDATA%/whisper-dictation/whisper-dictation.log`

Use:

```bash
whisper-dic logs
```

## Practical Privacy Guidance

- Prefer local provider for sensitive dictation.
- Disable failover if you do not want cross-provider fallback.
- Disable AI rewrite when you do not want transcript text sent to an LLM.
- If app metadata logging is a concern, avoid per-app contexts or keep logs disabled/off-host.
