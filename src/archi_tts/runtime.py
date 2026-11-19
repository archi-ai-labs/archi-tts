"""Process-wide singletons shared by the MCP tools and the web UI, so both use one set of
loaded models and one job queue."""

from __future__ import annotations

from .engines.omnivoice_engine import OmniVoiceEngine
from .engines.vieneu_engine import VieNeuEngine
from .jobs import JobManager
from .pipeline import Renderer
from .voices import VoiceRegistry

registry = VoiceRegistry()
engines = {"vieneu": VieNeuEngine(), "omnivoice": OmniVoiceEngine()}
renderer = Renderer(registry, engines)
jobs = JobManager()
