# Local Setup (whisper.cpp)

The local provider connects to a whisper.cpp server that exposes an OpenAI-compatible transcription endpoint at:

- `http://localhost:2022/v1/audio/transcriptions`

## Automated Setup

Fastest path:

```bash
whisper-dic setup-local
```

What it does:

1. Resolves the latest trusted whisper.cpp release metadata.
2. Installs a server binary:
   - macOS/Linux: builds `whisper-server` from source.
   - Windows: downloads prebuilt `whisper-server.exe` and DLLs.
3. Downloads your selected Whisper model.
4. Creates a start script.
5. Updates config to `whisper.provider = "local"`.

### Optional flags

```bash
# Pick model non-interactively
whisper-dic setup-local --model large-v3-turbo

# Install local server as launchd auto-start service (macOS only)
whisper-dic setup-local --autostart
```

### Installed locations

- macOS/Linux data dir: `~/.local/share/whisper-dic/`
- Windows data dir: `%LOCALAPPDATA%/whisper-dic/`

Expected outputs include:

- Server binary in `bin/`
- Model in `models/`
- Start script:
  - macOS/Linux: `start-server.sh`
  - Windows: `start-server.bat`

## Manual Setup

If you prefer manual control, follow these steps.

### macOS

```bash
# Install build tools
xcode-select --install
brew install cmake

# Clone and build whisper.cpp
git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
mkdir build && cd build
cmake .. -DWHISPER_BUILD_SERVER=ON -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release -j

# Download model
cd ..
curl -L -o models/ggml-large-v3-turbo.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin

# Start server
./build/bin/whisper-server \
  --model models/ggml-large-v3-turbo.bin \
  --host 127.0.0.1 --port 2022 \
  --inference-path "/v1/audio/transcriptions" \
  --convert
```

### Windows

1. Download `whisper-bin-x64.zip` from the latest release: `https://github.com/ggml-org/whisper.cpp/releases/latest`
2. Extract `whisper-server.exe`.
3. Download a model from the model table below.
4. Start server:

```cmd
whisper-server.exe --model ggml-large-v3-turbo.bin --host 127.0.0.1 --port 2022 --inference-path "/v1/audio/transcriptions" --convert
```

### Linux

```bash
# Debian/Ubuntu
sudo apt install build-essential cmake git

# Fedora
sudo dnf install gcc-c++ cmake git

# Build is the same as macOS
git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
mkdir build && cd build
cmake .. -DWHISPER_BUILD_SERVER=ON -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release -j
```

## Models

| Model | Size | Quality | Speed |
|---|---:|---|---|
| tiny | 78 MB | Basic | Fastest |
| base | 148 MB | Decent | Fast |
| small | 488 MB | Good | Moderate |
| medium | 1.5 GB | Very good | Slower |
| large-v3 | 3.1 GB | Best accuracy | Slowest |
| large-v3-turbo | 1.6 GB | Near-best | Fast |

Recommended default: `large-v3-turbo`.

Download URL pattern:

- `https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model}.bin`

## Verify

```bash
# Check server endpoint
curl http://localhost:2022/

# Run diagnostics
whisper-dic doctor
```

If diagnostics pass, set local provider (if not already set):

```bash
whisper-dic set whisper.provider local
```
