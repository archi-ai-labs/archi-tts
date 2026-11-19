# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-19

### Added

- MCP server for local Vietnamese (Northern accent) text-to-speech: VieNeu-TTS v3 Turbo
  for built-in voices, OmniVoice (Vietnamese fine-tune) for voices cloned from reference clips.
- Tools: `list_voices`, `speak`, `synthesize_script`, `job_status`, `preview_voice`,
  `check_text`, `add_lexicon_entry`, `add_voice`.
- Multi-voice dubbing scripts with emotions, pauses, emphasis, speed, pitch and volume;
  WAV (48 kHz, −16 LUFS), MP3 and SRT export; per-sentence cache; background job queue.
- Number/date/abbreviation normalization (sea-g2p) and a per-engine pronunciation lexicon.
- Claude Code plugin: installs disabled (`defaultEnabled: false`); a SessionStart hook sets up
  `~/.archi-tts` in the background on first enabled session; `setup` skill; MCP launcher.
- `install.sh` for cloned repos: Claude Desktop registration and an optional shared HTTP server.
