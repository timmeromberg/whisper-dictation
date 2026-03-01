# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in whisper-dic, please report it responsibly:

1. **Do NOT open a public issue.**
2. Use [GitHub Security Advisories](https://github.com/timmeromberg/whisper-dic/security/advisories/new) to report privately.
3. Include steps to reproduce, impact assessment, and any suggested fix.

We aim to acknowledge reports within 48 hours and provide a fix within 7 days for critical issues.

## Sensitive Data

whisper-dic's config file (`~/.config/whisper-dic/config.toml`) may contain API keys (e.g., Groq). The file is automatically set to `0600` permissions on creation.

**Never commit your config.toml to version control.** It is listed in `.gitignore` by default.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.9.x   | Yes       |
| < 0.9   | No        |
