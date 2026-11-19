"""OmniVoice (Vietnamese fine-tune): zero-shot cloning on Apple MPS."""

from __future__ import annotations

import re

import numpy as np

from .. import config
from ..voices import Voice
from .base import Engine

TAG_MAP = {"[cười]": "[laughter]", "[thở dài]": "[sigh]", "[hắng giọng]": ""}
SUPPORTED_TAGS = {
    "[laughter]", "[sigh]", "[confirmation-en]", "[dissatisfaction-hnn]", "[question-ah]", "[question-ei]",
    "[question-en]", "[question-oh]", "[question-yi]", "[surprise-ah]", "[surprise-oh]", "[surprise-wa]", "[surprise-yo]",
}


class OmniVoiceEngine(Engine):
    name = "omnivoice"
    sample_rate = 24000
    # The model's own speed= is not proportional (0.8 gave x1.11 duration),
    # so tempo is applied afterwards with Rubber Band like VieNeu.
    native_speed = False

    def __init__(self) -> None:
        super().__init__()
        self._prompts: dict[tuple[str, float], object] = {}
        self.version = f"1-{config.OMNIVOICE_MODEL}-{config.OMNIVOICE_STEPS}"

    def _load(self) -> None:
        import torch
        from omnivoice import OmniVoice

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        dtype = torch.float16 if device == "mps" else torch.float32
        self._model = OmniVoice.from_pretrained(config.OMNIVOICE_MODEL, device_map=device, dtype=dtype)

    def cache_key_parts(self, voice: Voice, emotion: str | None) -> list[str]:
        ref, _ = voice.ref_for(emotion)
        stat = ref.wav.stat()
        return [self.name, self.version, voice.id, str(ref.wav), str(stat.st_mtime_ns), ref.text or ""]

    def _prompt(self, voice: Voice, emotion: str | None):
        ref, _ = voice.ref_for(emotion)
        key = (str(ref.wav), ref.wav.stat().st_mtime)
        if key not in self._prompts:
            self._prompts[key] = self._model.create_voice_clone_prompt(ref_audio=str(ref.wav), ref_text=ref.text)
        return self._prompts[key]

    def transcribe(self, path: str) -> str:
        """Whisper (large-v3-turbo, downloaded on first use) for clips added without
        a transcript. The ASR model is dropped afterwards to free memory."""
        from .base import quiet_stdout

        self.ensure_loaded()
        with self._lock, quiet_stdout():
            import torch

            self._model.load_asr_model()
            try:
                return self._model.transcribe(path).strip()
            finally:
                self._model._asr_pipe = None
                if torch.backends.mps.is_available():
                    torch.mps.empty_cache()

    def _prepare(self, text: str) -> str:
        for k, v in TAG_MAP.items():
            text = text.replace(k, v)
        return re.sub(r"\[[^\[\]]+\]", lambda m: m.group(0) if m.group(0) in SUPPORTED_TAGS else "", text).strip()

    def _synth(self, text: str, voice: Voice, emotion: str | None, speed: float) -> np.ndarray:
        out = self._model.generate(text=self._prepare(text), voice_clone_prompt=self._prompt(voice, emotion),
                                   num_step=config.OMNIVOICE_STEPS, speed=speed)
        return out[0]
