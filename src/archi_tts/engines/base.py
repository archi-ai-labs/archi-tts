from __future__ import annotations

import contextlib
import sys
import threading
from abc import ABC, abstractmethod

import numpy as np

from ..voices import Voice


@contextlib.contextmanager
def quiet_stdout():
    """Route library prints/progress bars to stderr: stdout carries MCP stdio."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


class Engine(ABC):
    name: str
    sample_rate: int
    native_speed: bool = False
    version: str = "1"   # bump to invalidate the cache

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False

    def ensure_loaded(self) -> None:
        with self._lock:
            if not self._loaded:
                with quiet_stdout():
                    self._load()
                self._loaded = True

    @property
    def loaded(self) -> bool:
        return self._loaded

    @abstractmethod
    def _load(self) -> None: ...

    @abstractmethod
    def _synth(self, text: str, voice: Voice, emotion: str | None, speed: float) -> np.ndarray: ...

    def cache_key_parts(self, voice: Voice, emotion: str | None) -> list[str]:
        return [self.name, self.version, voice.id]

    def synth(self, text: str, voice: Voice, emotion: str | None, speed: float = 1.0) -> np.ndarray:
        self.ensure_loaded()
        with self._lock, quiet_stdout():
            audio = self._synth(text, voice, emotion, speed)
        return np.asarray(audio, dtype=np.float32).reshape(-1)
