"""Point archi-tts at a throwaway home: the repo's built-in voices plus two fake clone voices
(`lan`, `tung`), so tests can exercise OmniVoice script features without shipping clone clips."""

import os
import shutil
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
_home = Path(tempfile.mkdtemp(prefix="archi-tts-test-"))
(_home / "voices").mkdir()
shutil.copy(ROOT / "lexicon.yaml", _home / "lexicon.yaml")

_data = yaml.safe_load((ROOT / "voices" / "voices.yaml").read_text(encoding="utf-8"))
for vid, name, gender in (("lan", "Lan", "nữ"), ("tung", "Tùng", "nam")):
    _data["voices"][vid] = {
        "engine": "omnivoice", "name": name, "gender": gender, "accent": "Bắc",
        "refs": {emo: {"wav": f"{vid}/{emo}.wav", "text": "Câu tham chiếu."}
                 for emo in ("trung_tinh", "vui", "buon", "tuc_gian")},
    }
(_home / "voices" / "voices.yaml").write_text(yaml.safe_dump(_data, allow_unicode=True), encoding="utf-8")

os.environ["ARCHI_TTS_HOME"] = str(_home)
os.environ.setdefault("ARCHI_TTS_OUTPUT", str(_home / "output"))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _full_edition(monkeypatch):
    """Tests run as the full edition even where OmniVoice isn't installed (CI); a test can override."""
    from archi_tts import config

    monkeypatch.setattr(config, "has_omnivoice", lambda: True)
