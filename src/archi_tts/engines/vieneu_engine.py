"""VieNeu-TTS v3 Turbo: built-in preset voices, ONNX on CPU (fast)."""

from __future__ import annotations

import re

import numpy as np

from ..voices import Voice
from .base import Engine

# OmniVoice-style English tags -> VieNeu's Vietnamese cues; unknown tags dropped.
TAG_MAP = {"[laughter]": "[cười]", "[sigh]": "[thở dài]"}
SUPPORTED_TAGS = {"[cười]", "[thở dài]", "[hắng giọng]"}


class VieNeuEngine(Engine):
    name = "vieneu"
    sample_rate = 48000
    native_speed = False

    def _load(self) -> None:
        from vieneu import Vieneu

        self._tts = Vieneu()

    def _prepare(self, text: str) -> str:
        for k, v in TAG_MAP.items():
            text = text.replace(k, v)
        return re.sub(r"\[[^\[\]]+\]", lambda m: m.group(0) if m.group(0) in SUPPORTED_TAGS else "", text).strip()

    def _synth(self, text: str, voice: Voice, emotion: str | None, speed: float) -> np.ndarray:
        return self._tts.infer(self._prepare(text), voice=voice.preset, show_progress=False)
