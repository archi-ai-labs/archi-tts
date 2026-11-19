"""Paths and tunables. Override with environment variables."""

from __future__ import annotations

import os
from pathlib import Path

# Repo root holds the user-editable voices/ and lexicon.yaml.
HOME = Path(os.environ.get("ARCHI_TTS_HOME", Path(__file__).resolve().parents[2]))
VOICES_DIR = HOME / "voices"
VOICES_FILE = VOICES_DIR / "voices.yaml"
LEXICON_FILE = HOME / "lexicon.yaml"

OUTPUT_DIR = Path(os.environ.get("ARCHI_TTS_OUTPUT", Path.home() / "archi-tts-output")).expanduser()
CACHE_DIR = OUTPUT_DIR / ".cache"

SAMPLE_RATE = 48000          # everything is resampled to this before mixing
MAX_CHUNK_CHARS = 200        # normalized characters per synthesis call
SENTENCE_GAP_S = 0.18        # silence between chunks of one segment
SEGMENT_GAP_S = 0.45         # silence between script lines
PARAGRAPH_GAP_S = 0.9        # extra silence for a blank line in the script
TARGET_LUFS = -16.0          # podcast/video loudness
SUBTITLE_MAX_CHARS = 84      # per SRT cue

OMNIVOICE_MODEL = os.environ.get("ARCHI_TTS_OMNIVOICE_MODEL", "danhcao/v-omnivoice")
OMNIVOICE_STEPS = int(os.environ.get("ARCHI_TTS_OMNIVOICE_STEPS", "32"))
