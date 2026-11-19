# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Two editions. **lite** (new default): the 15 built-in VieNeu voices only, ~1.3 GB on disk and
  ~1.4 GB of RAM, no torch. **full**: adds OmniVoice voice cloning, emotion clips and `add_voice`
  (~5.3 GB). Switch with `archi-tts-bootstrap --full` / `--lite` or `install.sh --full` / `--lite`.
- `list_voices` reports the `edition`; in lite, cloned voices and `add_voice` return an error that
  says how to install full.

### Changed

- OmniVoice moved to the optional `full` extra (`uv sync --extra full`).
- Installs made before editions existed keep OmniVoice (detected as full).
- Scripts are validated before a job is queued, so errors return at once.
- `install.sh --uninstall` removes the plugin by its marketplace id `archi-tts@archi-ai-labs`.

- CI runs only on pull requests into `main` and on version tags, and skips docs- and
  benchmark-only changes; day-to-day work happens on `develop`.

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
