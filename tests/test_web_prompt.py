"""Every header the prompt generator emits must parse back to the same settings."""

import itertools

import pytest

from archi_tts.script import parse_script
from archi_tts.runtime import registry
from archi_tts.web import build_prompt, script_header


def _roundtrip(voice, emotion, speed, pitch, volume):
    line = f"{script_header(voice, emotion, speed, pitch, volume)} Câu thử."
    (seg,) = parse_script(line, registry.resolve, registry.default)
    return seg


@pytest.mark.parametrize("speed, pitch, volume", list(itertools.product(
    [0.5, 0.75, 1.0, 1.15, 2.0], [-6, -2.5, 0, 0.5, 6], [-12, -3, 0, 4, 12])))
def test_header_roundtrip_numbers(speed, pitch, volume):
    seg = _roundtrip("ngoc_huyen", None, speed, pitch, volume)
    assert (seg.voice, seg.speed, seg.pitch, seg.volume) == ("ngoc_huyen", speed, pitch, volume)


@pytest.mark.parametrize("voice", ["lan", "tung"])
@pytest.mark.parametrize("emotion", ["trung_tinh", "vui", "buon", "tuc_gian"])
def test_header_roundtrip_emotion(voice, emotion):
    seg = _roundtrip(voice, emotion, 1.1, -1, 2)
    assert seg.voice == voice
    assert (seg.emotion or "trung_tinh") == emotion


def test_prompt_script_parses_and_modes():
    one = build_prompt([{"voice": "lan", "emotion": "vui", "speed": 1.1}], text="Xin chào.")
    assert one["mode"] == "speak"
    assert one["prompt"] == "Dùng archi-tts đọc đoạn sau, giọng lan, cảm xúc vui, speed=1.1. Gửi mình file MP3.\n\nXin chào.\n"
    multi = build_prompt([{"voice": "ngoc_huyen"}, {"voice": "tung", "emotion": "buon", "pitch": -1}],
                         text="Xin chào.")
    assert multi["mode"] == "script" and multi["script"] in multi["prompt"]
    segs = parse_script(multi["script"], registry.resolve, registry.default)
    assert [s.voice for s in segs] == ["ngoc_huyen", "tung"]
    assert segs[1].emotion == "buon" and segs[1].pitch == -1


def test_vieneu_drops_emotion():
    r = build_prompt([{"voice": "pham_tuyen", "emotion": "vui"}])
    assert r["headers"] == ["[pham_tuyen]"]


def test_prompt_from_script_verbatim():
    script = "[ngoc_huyen] Chào bạn.\n[lan | vui | speed=1.1] Tuyệt quá!\n[ngoc_huyen] Tạm biệt."
    r = build_prompt(script=script)
    assert r["mode"] == "script" and r["script"] == script
    assert r["prompt"] == f"Dùng archi-tts đọc kịch bản sau. Gửi mình file MP3.\n\n```\n{script}\n```\n"
    assert r["headers"] == ["[ngoc_huyen]", "[lan | vui | speed=1.1]"]
