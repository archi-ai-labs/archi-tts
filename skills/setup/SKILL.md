---
name: setup
description: Install, check, repair or uninstall archi-tts (models, Python env, Claude Desktop registration).
disable-model-invocation: true
---

# archi-tts setup

The plugin root is `${CLAUDE_PLUGIN_ROOT}`. All state lives in `~/.archi-tts/` (override with `ARCHI_TTS_DATA`):
`venv/` (Python env), `home/voices/` + `home/lexicon.yaml` (user voices and pronunciations), `edition`, `setup.log`, `.ready`.

Two editions: **lite** (default; 15 built-in VieNeu voices, ~1.3 GB disk, ~1.4 GB RAM) and **full** (adds OmniVoice
voice cloning and emotion clips, `add_voice`; ~5.3 GB disk, ~5–7.6 GB RAM). `--status` prints which one is installed.

## Check status

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/archi-tts-bootstrap" --status      # ready | installing | not installed
ARCHI_TTS_HOME=~/.archi-tts/home ~/.archi-tts/venv/bin/archi-tts-setup doctor
tail -n 30 ~/.archi-tts/setup.log
```

## Install or repair

Run the setup in the foreground (idempotent; installs `uv`, `ffmpeg`, `rubberband` with Homebrew if missing, builds the Python env, downloads the models (lite ~0.6 GB, full ~3.9 GB), renders a test line). It can take a few minutes (lite) to 15 minutes (full) on first run, so run it in the background and report progress from the log:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/archi-tts-bootstrap"
```

To switch edition, add `--full` (voice cloning: ~1 GB of libraries + a 3.3 GB model; ask first, it takes several
minutes) or `--lite` (removes the OmniVoice libraries; the model stays in `~/.cache/huggingface/hub/models--danhcao--v-omnivoice`,
delete it only if the user agrees). Without a flag the current edition is kept.

If another setup is already running (the SessionStart hook starts one), the command waits for it.
Homebrew itself is not installed automatically: if it is missing, give the user the command from https://brew.sh and stop.

After setup, the `archi-tts` MCP tools appear once the server reconnects: tell the user to run `/mcp` and reconnect `archi-tts` (or start a new session).

Optional, full edition only: Whisper (~1.6 GB) lets `add_voice` transcribe a clip by itself. Only fetch it if the user wants that:

```bash
ARCHI_TTS_HOME=~/.archi-tts/home HF_HUB_OFFLINE=0 ~/.archi-tts/venv/bin/archi-tts-setup download --whisper
```

## Claude Desktop

Claude Desktop does not load Claude Code plugins. Ask before editing its config, then:

```bash
~/.archi-tts/venv/bin/archi-tts-setup register-desktop --command "${CLAUDE_PLUGIN_ROOT}/bin/archi-tts-mcp"
```

It backs up `claude_desktop_config.json` first. The user must restart Claude Desktop. `--remove` undoes it.
Each client starts its own server (~5 GB RAM once models load), so on a 16 GB Mac avoid rendering from both at once.

## Uninstall

`/plugin uninstall archi-tts`, then optionally remove the Desktop entry (above, with `--remove`) and `rm -rf ~/.archi-tts` — ask first, since `home/` holds the user's own voices and lexicon. Models stay in `~/.cache/huggingface`.
