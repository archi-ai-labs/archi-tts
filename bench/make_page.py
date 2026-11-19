"""Build bench/results/index.html from metrics.json, tests.yaml and refs.json."""

from __future__ import annotations

import html
import json
from pathlib import Path

import yaml

BENCH = Path(__file__).parent
RES = BENCH / "results"

LABELS = {
    "vieneu_preset": ("VieNeu v3 Turbo · giọng có sẵn", "Ngọc Huyền (nữ) / Phạm Tuyên (nam). Không clone, không đổi cảm xúc."),
    "vieneu_clone": ("VieNeu v3 Turbo · clone", "Clone từ clip tham chiếu bên dưới."),
    "omnivoice": ("OmniVoice VN (g-omnivoice)", "Clone từ clip tham chiếu. MPS, 32 bước."),
    "f5": ("F5-TTS ViVoice", "Clone từ clip tham chiếu. MPS, 32 bước. License phi thương mại."),
}
EMO_VI = {"trung_tinh": "trung tính", "vui": "vui", "buon": "buồn", "tuc_gian": "tức giận"}


def esc(s: object) -> str:
    return html.escape(str(s))


def main() -> None:
    metrics = json.loads((RES / "metrics.json").read_text())
    tests = yaml.safe_load((BENCH / "tests.yaml").read_text())
    refs = json.loads((BENCH / "refs" / "refs.json").read_text())
    engines = [e for e in LABELS if e in metrics and "error" not in metrics[e]]
    failed = {e: m["error"] for e, m in metrics.items() if "error" in m}

    rows = []
    for e in engines:
        m = metrics[e]
        rows.append(
            f"<tr><th scope=row>{esc(LABELS[e][0])}</th><td>{m['model_gb']} GB</td><td>{m.get('peak_footprint_gb', m['peak_ram_gb'])} GB</td>"
            f"<td>{m['device'].upper()}</td><td>{m['rtf']}</td><td>{m['est_15min_video_min']} phút</td>"
            f"<td>{m['load_s']} s</td><td>{m['sample_rate'] // 1000} kHz</td>"
            f"<td>{format(m['wer_adj'], '.1%') if 'wer_adj' in m else '—'}</td></tr>"
        )

    sections = []
    for t in tests:
        players = []
        for e in engines:
            players.append(
                f"""<div class=card data-engine="{e}" data-test="{t['id']}">
  <div class=card-head><b>{esc(LABELS[e][0])}</b><span class=dur>{metrics[e]['tests'].get(t['id'], '')} s</span></div>
  <audio controls preload=none src="{e}/{t['id']}.mp3"></audio>
  <div class=score role=radiogroup aria-label="Điểm">{''.join(f'<button type=button data-v={v}>{v}</button>' for v in range(1, 6))}</div>
  <input class=note placeholder="Ghi chú (lỗi thanh điệu, nuốt chữ...)">
</div>"""
            )
        segs = "".join(
            f"<li><span class=tag>{esc(s['role'])}{' · ' + esc(EMO_VI.get(s.get('emotion', ''), '')) if s.get('emotion') else ''}</span> {esc(s['text'])}</li>"
            for s in t["segments"]
        )
        sections.append(
            f"""<section id="{t['id']}"><h2>{esc(t['title'])}</h2>
<details><summary>Văn bản</summary><ul class=segs>{segs}</ul></details>
<div class=grid>{''.join(players)}</div></section>"""
        )

    ref_cards = []
    for role, emos in refs.items():
        for emo, r in emos.items():
            audio = (f'<audio controls preload=none src="../refs/{esc(r["wav"])}"></audio>'
                     if (BENCH / "refs" / r["wav"]).exists()
                     else "<p class=small>Clip không kèm trong repo (giọng của bên thứ ba): chạy bench/common/pick_refs.py để tải.</p>")
            ref_cards.append(
                f"""<div class=card><div class=card-head><b>{'Nữ' if role == 'nu' else 'Nam'} · {esc(EMO_VI[emo])}</b><span class=dur>{r['dur']} s</span></div>
{audio}<p class=small>{esc(r['text'])}</p></div>"""
            )

    fail_html = "".join(f"<p class=warn>{esc(k)} lỗi: {esc(v)}</p>" for k, v in failed.items())
    page = TEMPLATE.replace("{{ROWS}}", "".join(rows)).replace("{{SECTIONS}}", "".join(sections))
    page = page.replace("{{REFS}}", "".join(ref_cards)).replace("{{FAILED}}", fail_html)
    page = page.replace("{{NOTES}}", "".join(f"<li><b>{esc(LABELS[e][0])}</b>: {esc(LABELS[e][1])}</li>" for e in engines))
    findings = (BENCH / "findings.html")
    page = page.replace("{{FINDINGS}}", findings.read_text(encoding="utf-8") if findings.exists() else "")
    (RES / "index.html").write_text(page, encoding="utf-8")
    print(RES / "index.html")


TEMPLATE = """<!doctype html>
<html lang=vi><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>So sánh TTS tiếng Việt</title>
<style>
:root{--bg:#fafaf8;--fg:#1c1c1a;--muted:#6b6b66;--line:#e2e1dc;--card:#fff;--accent:#2f5bd3;--accent-fg:#fff;--warn:#b3261e}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#161615;--fg:#ecebe6;--muted:#9c9b95;--line:#2e2d2a;--card:#1f1f1d;--accent:#7a9bff;--accent-fg:#111;--warn:#ff8a80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 80px}h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:40px 0 8px}
.lead,.small{color:var(--muted)}.small{font-size:13px;margin:6px 0 0}
.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;margin-top:12px;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;white-space:nowrap}thead th{color:var(--muted);font-weight:500;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.card-head{display:flex;justify-content:space-between;gap:8px;margin-bottom:8px}.dur{color:var(--muted);font-size:13px}
audio{width:100%;height:36px}.score{display:flex;gap:6px;margin-top:8px}
.score button{flex:1;border:1px solid var(--line);background:transparent;color:var(--fg);border-radius:6px;padding:4px 0;cursor:pointer;font:inherit}
.score button.on{background:var(--accent);color:var(--accent-fg);border-color:var(--accent)}
.note{width:100%;margin-top:8px;border:1px solid var(--line);background:transparent;color:var(--fg);border-radius:6px;padding:6px 8px;font:inherit;font-size:13px}
.segs{padding-left:18px}.tag{font-size:12px;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 5px;margin-right:4px}
details{margin:4px 0 12px}summary{cursor:pointer;color:var(--muted)}
.bar{position:sticky;bottom:0;background:var(--bg);border-top:1px solid var(--line);padding:10px 16px;display:flex;gap:12px;align-items:center;justify-content:center}
.bar button{border:0;background:var(--accent);color:var(--accent-fg);border-radius:8px;padding:8px 16px;font:inherit;cursor:pointer}
.warn{color:var(--warn)}ul.notes{color:var(--muted);font-size:14px;padding-left:18px}
</style></head><body><main>
<h1>So sánh TTS tiếng Việt chạy local</h1>
<p class=lead>Cùng văn bản, cùng bộ chuẩn hóa (soe-vinorm + từ điển phát âm), cùng clip tham chiếu. Máy: MacBook M1 Pro 16GB. Nghe theo từng bài, chấm 1–5, rồi bấm "Copy điểm" và dán lại cho Claude.</p>
{{FAILED}}
<div class=tablewrap><table><thead><tr><th>Engine</th><th>Model</th><th>RAM đỉnh</th><th>Chạy trên</th><th>RTF</th><th>Ước tính video 15 phút</th><th>Thời gian load</th><th>Chất lượng file</th><th>Lỗi đọc (WER)</th></tr></thead>
<tbody>{{ROWS}}</tbody></table></div>
<p class=small>RAM đỉnh = peak memory footprint (tính cả bộ nhớ GPU/MPS). RTF = thời gian sinh / độ dài audio; nhỏ hơn 1 là nhanh hơn thời gian thực. Lỗi đọc = tỉ lệ âm tiết Whisper large-v3-turbo nghe sai/thiếu/thừa, đã bỏ bài số/viết tắt (Whisper ghi số dạng ký hiệu) và gộp tr/ch, r/d/gi, s/x (Whisper viết sai chính tả giọng Bắc). Chỉ để so sánh tương đối.</p>
<ul class=notes>{{NOTES}}</ul>
{{FINDINGS}}
{{SECTIONS}}
<section><h2>Clip tham chiếu (dùng cho các engine clone)</h2>
<p class=small>Lấy từ dataset mở slexisvn/emotion-tts-vietnamese-sample; đây là giọng tổng hợp của Gemini TTS, chọn tự động theo nội dung câu. Nếu giọng hay cảm xúc chưa đúng ý, có thể thay clip khác.</p>
<div class=grid>{{REFS}}</div></section>
</main>
<div class=bar><span id=count class=small></span><button id=copy type=button>Copy điểm</button></div>
<script>
const KEY='archi-tts-bench-v1';let state={};try{state=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(state))}catch(e){};count()};
const count=()=>{const n=Object.values(state).filter(v=>v.score).length;document.getElementById('count').textContent=n+' ô đã chấm'};
document.querySelectorAll('.card[data-engine]').forEach(c=>{const k=c.dataset.engine+'/'+c.dataset.test;const s=state[k]||{};
 c.querySelectorAll('.score button').forEach(b=>{if(+b.dataset.v===s.score)b.classList.add('on');
  b.onclick=()=>{c.querySelectorAll('.score button').forEach(x=>x.classList.remove('on'));b.classList.add('on');state[k]={...state[k],score:+b.dataset.v};save()}});
 const n=c.querySelector('.note');n.value=s.note||'';n.oninput=()=>{state[k]={...state[k],note:n.value};save()}});
document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(o=>{if(o!==a)o.pause()})));
document.getElementById('copy').onclick=async()=>{const t=JSON.stringify(state,null,1);try{await navigator.clipboard.writeText(t);document.getElementById('copy').textContent='Đã copy'}catch(e){prompt('Copy:',t)}};
count();
</script></body></html>"""

if __name__ == "__main__":
    main()
