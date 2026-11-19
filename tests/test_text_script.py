import pytest

from archi_tts import config
from archi_tts.pipeline import Gap, Item, build_plan, chunk_cues, make_srt
from archi_tts.script import Pause, ScriptError, parse_script, split_pauses
from archi_tts.text import apply_emphasis, apply_lexicon, chunk_text, normalize, subtitle_lines
from archi_tts.voices import VoiceRegistry

LEX = {"AI": "ây-ai", "GPU": "gi pi iu", "COVID-19": "cô vít mười chín", "iPhone": "ai phôn"}


@pytest.fixture(scope="module")
def registry():
    return VoiceRegistry()


# --- text ---------------------------------------------------------------------

def test_lexicon_whole_word_and_case():
    assert apply_lexicon("AI và GPU", LEX) == "ây-ai và gi pi iu"
    assert apply_lexicon("Ai đó", LEX) == "Ai đó"          # all-caps key is case-sensitive
    assert apply_lexicon("iphone mới", LEX) == "ai phôn mới"  # mixed-case key is not
    assert apply_lexicon("RAIN", LEX) == "RAIN"


@pytest.mark.parametrize("raw, expected", [
    ("Ngày 15/8/2025", "ngày mười lăm tháng tám năm hai nghìn không trăm hai mươi lăm"),
    ("tăng 12,5%", "tăng mười hai phẩy năm phần trăm"),
    ("Tại TP.HCM", "tại thành phố hồ chí minh"),
    ("lúc 14h30", "lúc mười bốn giờ ba mươi phút"),
    ("vắc xin COVID-19", "vắc xin cô vít mười chín"),
    ("ứng dụng AI", "ứng dụng ây-ai"),
])
def test_normalize(raw, expected):
    assert normalize(raw, LEX) == expected


def test_lexicon_readings_bypass_normalizer_and_keep_punctuation():
    lex = {"AI": "ây-ai", "GPU": "gi-pi-iu", "iPhone": "ai phôn", "COVID-19": "cô vít mười chín"}
    out = normalize("Ứng dụng AI và GPU, iPhone 16 giá 25 triệu.", lex)
    assert out == "ứng dụng ây-ai và gi-pi-iu, ai phôn mười sáu giá hai mươi lăm triệu."
    out = normalize("Ngày 15/8/2025, COVID-19 tại TP.HCM; tăng 30%.", lex)
    assert out == ("ngày mười lăm tháng tám năm hai nghìn không trăm hai mươi lăm, cô vít mười chín "
                   "tại thành phố hồ chí minh, tăng ba mươi phần trăm.")  # sea-g2p maps ; to ,


def test_leading_minus_and_dialogue_dash():
    assert normalize("-5 độ", LEX) == "âm năm độ"
    assert normalize("- Xin chào anh.", LEX) == "xin chào anh."
    assert normalize("Giảm -3% với AI.", LEX) == "giảm âm ba phần trăm với ây-ai."


def test_normalize_keeps_tags():
    out = normalize("Vui quá [cười] có 2 người.", LEX)
    assert "[cười]" in out and "hai người" in out


def test_emphasis_adds_comma():
    assert apply_emphasis("Bạn *phải* sao lưu.") == "Bạn, phải sao lưu."
    assert apply_emphasis("Nếu không, *toàn bộ* ảnh.") == "Nếu không, toàn bộ ảnh."


def test_chunks_respect_limit_and_keep_display_text():
    text = " ".join(["Ngày 15/8/2025 giá vàng tăng 12,5% so với cùng kỳ năm ngoái tại TP.HCM."] * 6)
    chunks = chunk_text(text, LEX)
    assert len(chunks) > 1
    assert all(len(c.norm) <= config.MAX_CHUNK_CHARS * 1.4 for c in chunks)
    assert "15/8/2025" in chunks[0].raw            # subtitles show the original
    assert "mười lăm" in chunks[0].norm            # engine reads words


def test_long_sentence_without_periods_is_split():
    text = ", ".join(["một câu rất dài không có dấu chấm nào cả"] * 12)
    chunks = chunk_text(text, LEX)
    assert len(chunks) > 1
    assert all(len(c.norm) <= config.MAX_CHUNK_CHARS * 1.4 for c in chunks)


def test_subtitle_lines():
    raw = "Chào mừng các bạn quay trở lại với kênh, hôm nay chúng ta sẽ cùng nhau tìm hiểu một chủ đề rất thú vị."
    lines = subtitle_lines(raw, 50)
    assert all(len(x) <= 50 for x in lines)
    assert " ".join(lines) == raw


# --- script ---------------------------------------------------------------------

def test_split_pauses():
    parts = split_pauses("A. [ngắt 0.8s] B. [ngắt 500ms] C.")
    assert parts == ["A.", Pause(0.8), "B.", Pause(0.5), "C."]


def test_parse_script(registry):
    script = """[ngoc_huyen] Xin chào.
Dòng tiếp theo cùng giọng.

[lan | vui | speed=1.2 | pitch=-1 | volume=+2] Hay quá!
[cười] vẫn là lan.
[Phạm Tuyên] Tên có dấu cũng được."""
    segs = parse_script(script, registry.resolve, registry.default)
    assert [s.voice for s in segs] == ["ngoc_huyen", "ngoc_huyen", "lan", "lan", "pham_tuyen"]
    assert segs[2].paragraph_break and not segs[1].paragraph_break
    assert (segs[2].emotion, segs[2].speed, segs[2].pitch, segs[2].volume) == ("vui", 1.2, -1, 2)
    assert segs[3].text_parts == ["[cười] vẫn là lan."]
    assert segs[4].emotion is None and segs[4].speed == 1.0


@pytest.mark.parametrize("bad, msg", [
    ("[khong_co | vui] x", "không có giọng"),
    ("[khong_co] x", "không có giọng"),
    ("[lan | hoang_mang] x", "không hỗ trợ"),
    ("[lan | speed=5] x", "ngoài khoảng"),
    ("[lan | foo=1] x", "không hỗ trợ"),
])
def test_parse_errors(registry, bad, msg):
    with pytest.raises(ScriptError, match=msg):
        parse_script(bad, registry.resolve, registry.default)


def test_plan_gaps_and_warnings(registry):
    segs = parse_script("[ngoc_huyen | vui] Một. Hai. [ngắt 1.5s] Ba.\n[lan] Bốn.", registry.resolve, registry.default)
    plan, warnings = build_plan(segs, registry)
    gaps = [p.seconds for p in plan if isinstance(p, Gap)]
    assert isinstance(plan[0], Item) and isinstance(plan[-1], Item)
    assert 1.5 in gaps and config.SEGMENT_GAP_S in gaps
    assert any("không đổi cảm xúc" in w for w in warnings)


# --- srt ----------------------------------------------------------------------

def test_srt_timing_is_monotonic_and_covers_chunk():
    cues = chunk_cues("Câu thứ nhất khá dài, có dấu phẩy ở giữa câu, và tiếp tục thêm một đoạn nữa cho đủ dài.", 1.0, 7.0)
    assert cues[0][0] == 1.0 and abs(cues[-1][1] - 7.0) < 1e-6
    assert all(a[1] <= b[0] + 1e-9 for a, b in zip(cues, cues[1:]))
    srt = make_srt(cues)
    assert srt.startswith("1\n00:00:01,000 --> ")


# --- per-engine lexicon ---------------------------------------------------------

def test_per_engine_lexicon(tmp_path):
    from archi_tts.text import load_lexicon, save_lexicon_entry

    p = tmp_path / "lex.yaml"
    save_lexicon_entry("AI", "ây-ai", path=p)
    save_lexicon_entry("GPU", "gi-pi-iu", path=p)
    save_lexicon_entry("GPU", "GPU", engine="vieneu", path=p)
    assert load_lexicon(p, "omnivoice") == {"AI": "ây-ai", "GPU": "gi-pi-iu"}
    # VieNeu: its own reading wins, and hyphens become spaces.
    assert load_lexicon(p, "vieneu") == {"AI": "ây ai", "GPU": "GPU"}
    assert normalize("AI và GPU, 2 con.", load_lexicon(p, "vieneu")) == "ây ai và GPU, hai con."


def test_lite_edition_rejects_cloned_voice(registry, monkeypatch):
    monkeypatch.setattr(config, "has_omnivoice", lambda: False)
    segs = parse_script("[ngoc_huyen] Một.\n[lan] Hai.", registry.resolve, registry.default)
    with pytest.raises(ScriptError, match="bản full"):
        build_plan(segs, registry)
    build_plan(segs[:1], registry)  # built-in voices still work
