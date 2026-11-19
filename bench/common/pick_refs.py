"""Pick reference clips per (role, emotion) from slexisvn/emotion-tts-vietnamese-sample.

The dataset's emotion labels don't match the text, so clips are scored by
emotion keywords in the transcript instead. Speakers are Gemini TTS voices.
"""
import glob, io, json, re, sys
from pathlib import Path
import pandas as pd, pyarrow.parquet as pq, soundfile as sf
from huggingface_hub import snapshot_download

ROLES = {"nu": sys.argv[1] if len(sys.argv) > 1 else "kore", "nam": sys.argv[2] if len(sys.argv) > 2 else "charon"}
KW = {
    "vui": ["vui", "hạnh phúc", "tuyệt", "hào hứng", "vỡ òa", "sung sướng", "mừng", "rạng rỡ", "phơi phới", "!"],
    "buon": ["buồn", "nhớ", "cô đơn", "khóc", "tiếc", "đau", "lặng", "trống", "một mình", "nước mắt", "mất"],
    "tuc_gian": ["bao nhiêu lần", "đừng có", "các người", "tức", "dám", "hả", "đã bảo", "chịu nổi", "vô lý", "?"],
}
NEG = {"vui": KW["buon"][:6] + ["?"], "buon": ["vui", "hạnh phúc", "!"], "tuc_gian": ["vui", "hạnh phúc", "thương"]}

def score(text, emo):
    t = text.lower()
    if emo == "trung_tinh":
        return 3 - sum(t.count(c) for c in "!?") * 3 - sum(w in t for w in ["tao", "mày", "anh", "em", "mình"]) + ("." in t)
    return sum(w in t for w in KW[emo]) * 2 - sum(w in t for w in NEG[emo]) * 2

p = snapshot_download("slexisvn/emotion-tts-vietnamese-sample", repo_type="dataset")
df = pd.concat([pq.read_table(f).to_pandas() for f in sorted(glob.glob(p + "/data/*.parquet"))]).reset_index(drop=True)
df["dur"] = df.audio.map(lambda a: sf.info(io.BytesIO(a["bytes"])).duration)
out = Path(__file__).parents[1] / "refs"; out.mkdir(exist_ok=True)
refs = {}
for role, spk in ROLES.items():
    refs[role] = {}
    cand = df[(df.speaker == spk) & (df.dur >= 3.5) & (df.dur <= 10)]
    for emo in ["trung_tinh", "vui", "buon", "tuc_gian"]:
        best = cand.assign(s=cand.text.map(lambda t: score(t, emo)) - (cand.dur - 7).abs() * 0.2).sort_values("s", ascending=False).iloc[0]
        name = f"{role}_{emo}_{spk}.wav"
        (out / name).write_bytes(best.audio["bytes"])
        refs[role][emo] = {"wav": name, "text": best.text.strip(), "speaker": spk, "dur": round(best.dur, 1),
                           "source": "slexisvn/emotion-tts-vietnamese-sample (Gemini TTS voices)"}
        print(role, emo, spk, round(best.dur, 1), best.text.strip())
(out / "refs.json").write_text(json.dumps(refs, ensure_ascii=False, indent=1))
