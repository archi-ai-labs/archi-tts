# archi-tts

TTS tiếng Việt (giọng Bắc) chạy hoàn toàn trên máy, dùng để lồng tiếng video, gọi qua MCP.

- **Giọng có sẵn**: VieNeu-TTS v3 Turbo, 15 giọng Bắc. Nhanh (~4 phút cho 15 phút audio trên M1 Pro), nhưng không đổi được cảm xúc và đôi khi sai thanh điệu.
- **Giọng clone**: OmniVoice (bản fine-tune tiếng Việt `danhcao/v-omnivoice`). Mỗi cảm xúc một clip tham chiếu 3–10s. Chậm hơn (~40 phút cho 15 phút audio) nhưng ít lỗi thanh điệu nhất trong benchmark.
- Xuất WAV 48 kHz (−16 LUFS), MP3 và SRT vào `~/archi-tts-output/<tên>/`.

Kết quả so sánh 4 engine nằm trong `bench/` (mở `bench/results/index.html` qua `python3 -m http.server --directory bench`).

## Cài đặt (Claude Code)

Nói với Claude Code:

> Cài plugin archi-tts từ https://github.com/archi-ai-labs/archi-tts

Hoặc gõ tay:

```
/plugin marketplace add archi-ai-labs/agent-marketplace
/plugin install archi-tts@archi-ai-labs
/plugin enable archi-tts@archi-ai-labs
```

Hoặc dùng installer của marketplace (đăng ký catalog và bật plugin ở mức user):

```bash
curl -fsSL https://archi-ai-labs.github.io/agent-marketplace/install.sh | bash -s -- --plugins archi-tts
```

Rồi mở phiên mới. Phiên đầu tiên tự cài ở nền (thư viện Homebrew, môi trường Python, ~4.5 GB model; khoảng 5–15 phút, xem `~/.archi-tts/setup.log`). Xong thì các tool `archi-tts` dùng được; nếu chưa thấy, gõ `/mcp` và kết nối lại `archi-tts`. Skill `/archi-tts:setup` để kiểm tra, sửa lỗi, đăng ký Claude Desktop hoặc gỡ cài đặt.

**Plugin cài ở trạng thái tắt** (`defaultEnabled: false`), vì nó có hook `SessionStart` (cài đặt nền) và một MCP server. Bật bằng `/plugin enable archi-tts@archi-ai-labs` (hoặc `claude plugin enable archi-tts@archi-ai-labs`). Máy đã cài và bật từ trước không bị ảnh hưởng: giá trị đã ghi trong `enabledPlugins` luôn được ưu tiên hơn mặc định. Cần Claude Code ≥ v2.1.154; bản cũ hơn bỏ qua trường này và bật plugin ngay khi cài.

**Chi phí context luôn bật** (đo, không ước đoán): skill `setup` đóng (`disable-model-invocation: true`), nên phần mô tả skill nạp sẵn là **0 token** (lệnh đo ở mục 6.2 của chuẩn plugin archi-ai-labs). Khi plugin được bật, MCP server thêm 8 tool: định nghĩa tool dài 6.2k ký tự (~1.5k token) cộng 336 ký tự hướng dẫn server.

> **Dành cho Claude khi được yêu cầu cài plugin này:** chạy
> `claude plugin marketplace add archi-ai-labs/agent-marketplace` (bỏ qua nếu `claude plugin marketplace list` đã có `archi-ai-labs`),
> rồi `claude plugin install archi-tts@archi-ai-labs` và `claude plugin enable archi-tts@archi-ai-labs`.
> Sau đó chạy `bash "$(ls -d ~/.claude/plugins/cache/archi-ai-labs/archi-tts/*/ | tail -1)bin/archi-tts-bootstrap"`
> ở nền để cài ngay mà không phải chờ phiên mới, báo người dùng mở phiên mới hoặc `/mcp` khi log báo "sẵn sàng".
> Cần Homebrew; nếu máy chưa có, đưa lệnh cài từ https://brew.sh cho người dùng tự chạy.

Yêu cầu: Mac Apple Silicon, ≥16 GB RAM, Homebrew, ~6 GB ổ trống.

### Dữ liệu nằm ở đâu

| Thư mục | Nội dung |
|---|---|
| `~/.archi-tts/venv/` | Môi trường Python (tự dựng lại khi plugin cập nhật) |
| `~/.archi-tts/home/` | `voices/` + `lexicon.yaml` của bạn: copy từ bản mặc định ở lần đầu, sau đó plugin không ghi đè |
| `~/.archi-tts/setup.log` | Log cài đặt |
| `~/.cache/huggingface/` | Model |
| `~/archi-tts-output/` | File xuất ra |

## Cài từ repo (Claude Desktop, server HTTP chung)

```bash
git clone https://github.com/archi-ai-labs/archi-tts && cd archi-tts
./install.sh            # cài, chạy thử, rồi hỏi đăng ký Claude Code / Claude Desktop / server HTTP chung
./install.sh --uninstall
```

Claude Desktop không dùng được plugin của Claude Code, nên đăng ký bằng `install.sh` (hoặc skill `/archi-tts:setup`). Cả plugin, `install.sh` và Claude Desktop đều chạy server qua `bin/archi-tts-mcp`, dùng chung `~/.archi-tts`.

Mỗi client stdio tự khởi động một server riêng, mỗi server giữ ~5 GB RAM sau khi nạp model. Nếu dùng cùng lúc nhiều client (Claude Code + Claude Desktop), nên chạy **một** server HTTP (`./install.sh --http`, chạy nền bằng LaunchAgent) rồi trỏ client vào `http://127.0.0.1:8766/mcp`. Server tự chạy offline khi model đã có trong cache; đặt `HF_HUB_OFFLINE=0` nếu cần tải thêm. Đường dẫn `ffmpeg`/`rubberband` được tự tìm ở `/opt/homebrew/bin`, nên client khởi động từ giao diện (không có PATH của Homebrew) vẫn chạy được.

## Web thử giọng

Mở **http://127.0.0.1:8770**. Không cần chạy server riêng: chính server MCP `archi-tts` (do Claude Code/Claude Desktop tự bật, hoặc `archi-tts --http`) phục vụ luôn trang này, dùng chung model và hàng đợi với các tool MCP. Đổi cổng bằng `--web-port` hoặc `ARCHI_TTS_WEB_PORT`, `0` để tắt. Nếu có nhiều server MCP cùng chạy, chỉ server đầu tiên mở web, các server sau bỏ qua.

Một trang, đi từ trên xuống:

1. Nhập câu (bấm "Máy sẽ đọc thành gì?" để xem số, ngày, viết tắt được đọc thế nào).
2. Chọn giọng: đổi giọng là tự phát file mẫu có sẵn (bấm 🔈 để nghe lại), không cần tạo. Mẫu VieNeu nằm ở `voices/samples/`, tạo lại bằng `uv run python scripts/make_samples.py --force`; giọng clone phát clip tham chiếu của cảm xúc đang chọn.
3. Chọn cảm xúc, tốc độ, giọng trầm/cao, âm lượng bằng nút bấm; "Chỉnh chi tiết" có thanh trượt.
4. Bấm **Đọc thử**. Mỗi bản nghe thử có nút "+ Thêm vào kịch bản" để ghép nhiều giọng.
5. Phần **Prompt cho Claude** tự cập nhật theo lựa chọn (một giọng → `speak`, kịch bản → `synthesize_script`), bấm Copy rồi dán vào Claude. Tag sinh ra được kiểm tra parse ngược trong `tests/test_web_prompt.py`.

## Tools

| Tool | Việc |
|---|---|
| `list_voices` | Danh sách giọng, engine, cảm xúc có clip |
| `speak` | Một đoạn ngắn (≤800 ký tự), một giọng → file |
| `synthesize_script` | Kịch bản nhiều giọng → job chạy nền, trả `job_id` |
| `job_status` | Tiến độ, ETA, đường dẫn file khi xong |
| `preview_voice` | Nghe thử một giọng |
| `check_text` | Xem mỗi engine sẽ đọc văn bản thành gì (số, ngày, viết tắt, từ điển) |
| `add_lexicon_entry` | Dạy cách đọc một từ, chung hoặc riêng từng engine (ghi vào `lexicon.yaml`) |
| `add_voice` | Thêm giọng clone / clip cảm xúc từ file audio |

## Kịch bản

```
[ngoc_huyen] Hôm nay, ngày 15/8/2025, chúng ta tìm hiểu về chip AI.
[mai_anh | speed=1.1] Nó nhanh *gấp đôi* thế hệ trước! [ngắt 0.6s]
[lan | buon] Tiếc là giá lên tới 25 triệu đồng.

[pham_tuyen | pitch=-1 | volume=+2] Vậy có nên mua không?
```

- `[giọng | cảm_xúc | speed= | pitch= | volume=]` ở đầu dòng; dòng không có tag giữ cài đặt dòng trước.
- Cảm xúc: `trung_tinh`, `vui`, `buon`, `tuc_gian`. Chỉ áp dụng cho giọng clone (`lan` ở ví dụ trên là giọng bạn tự thêm, xem dưới).
- `[ngắt 0.8s]` khoảng lặng, `*từ*` nhấn, `[cười]` `[thở dài]` âm phi ngôn ngữ (thử nghiệm). Dòng trống = ngắt đoạn.

### Thêm giọng clone

Repo chỉ kèm 15 giọng VieNeu, không kèm giọng clone nào. Thêm giọng của bạn bằng tool `add_voice` (hoặc nói với Claude "thêm giọng lan từ file ~/clip.wav"): mỗi cảm xúc một clip 3–10 s, giọng sạch, một người nói, kèm lời thoại đúng từng chữ (thiếu lời thoại thì Whisper tự nghe, tải thêm ~1.6 GB). Giọng được ghi vào `~/.archi-tts/home/voices/`. Chỉ clone giọng bạn có quyền sử dụng.

Mỗi câu được cache, nên sửa một dòng rồi xuất lại thì chỉ sinh lại dòng đó. Đổi `speed`/`pitch`/`volume` không cần sinh lại (xử lý hậu kỳ).

## Các điều khiển hoạt động thế nào (đã đo)

Đo bằng `scripts/control_check.py` trên cùng một câu, cả hai engine:

| Điều khiển | Cách làm | Kết quả đo |
|---|---|---|
| Tốc độ | Rubber Band co giãn thời gian, giữ cao độ (cả hai engine; tham số `speed` của OmniVoice không tỉ lệ nên không dùng) | `speed=0.8` → dài ×1.25, `1.25` → ×0.80, cao độ giữ nguyên |
| Cao độ | Rubber Band, ±6 nửa cung (±2–3 còn tự nhiên) | `pitch=±3` → ±2.9–3.3 nửa cung, độ dài giữ nguyên |
| Âm lượng | Cân mức từng câu về cùng một mức, cộng gain `volume`, rồi một gain tĩnh cho cả file + limiter chặn đỉnh | `-6` → −6.0 dB; `+6` → +5.1–5.7 dB (limiter chặn đỉnh) |
| Cân giọng | Mọi câu được đưa về cùng mức trước khi trộn | VieNeu và OmniVoice lệch 4 dB → lệch 0.1 dB |
| Loudness file | Gain tĩnh tới −16 LUFS, đỉnh ≤ −1.4 dBFS | −15.8 đến −16.8 LUFS |
| Ngắt nghỉ | Chèn khoảng lặng chính xác | đúng như ghi |
| Nhấn từ | Thêm dấu phẩy trước từ để engine ngắt nhẹ rồi nhấn lại | **VieNeu**: có ngắt rõ (câu dài thêm 0.36 s). **OmniVoice**: không có tác dụng đo được (+0.06 s); model này bỏ qua dấu câu khi tính nhịp, thử cả `...`, `—`, `.` đều không ngắt |
| Cảm xúc | Clip tham chiếu theo cảm xúc (giọng clone). Giọng VieNeu giữ phong cách cố định | Cùng một câu, chỉ đổi clip (hai giọng clone thử nghiệm): giọng nữ vui +2.6 nửa cung, buồn −1.8 nửa cung và chậm hơn 21%, tức giận cao và nhanh; giọng nam ngữ điệu biến thiên mạnh hơn khi vui/buồn (3.8 → 5.0 nửa cung), tức giận nhanh hơn 26%. Nghe mẫu ở `~/archi-tts-output/expressive_check_*` |
| Phụ đề | Mỗi câu một mốc thời gian, chia dòng ≤84 ký tự theo tỉ lệ độ dài | Khớp mốc Whisper trong ~0.1 s |

## Từ điển phát âm

`lexicon.yaml` (sửa trực tiếp hoặc dùng tool `add_lexicon_entry`). Cách đọc được gửi nguyên văn tới engine, không qua bộ chuẩn hóa. Mỗi từ có thể đọc chung cho cả hai engine, hoặc riêng cho từng engine:

```yaml
AI: ây-ai                                  # cả hai engine
GPU: {vieneu: GPU, omnivoice: gi-pi-iu}    # riêng từng engine
```

Lý do có hai cách: VieNeu học song ngữ nên đọc **GPU, CPU, Pro** viết nguyên tốt hơn phiên âm (phiên âm "gi pi iu" bị nghe thành "PU", "prô" thành "Pero"). OmniVoice thì cần phiên âm, và gạch nối giúp đọc liền mạch ("ây ai" bị nghe thành "AAI" 3/4 lần, "ây-ai" đúng 2/2). Với VieNeu, gạch nối tự đổi thành dấu cách.

Với từ điển hiện tại, cả 4 giọng thử (`ngoc_huyen`, `pham_tuyen` và hai giọng clone) đều đọc đúng câu "Các ứng dụng AI và GPU, chiếc iPhone 16 Pro giá 25 triệu đồng, CPU cũng nhanh hơn" (kiểm tra bằng Whisper). Dùng `check_text` để xem trước mỗi engine sẽ đọc thành gì.

## Tài nguyên (M1 Pro 16 GB)

- Model: VieNeu ~1.2 GB, OmniVoice ~3.3 GB; Whisper ~1.6 GB tải thêm khi `add_voice` không kèm transcript.
- RAM đỉnh của server khi dùng cả hai engine: ~7.6 GB (OmniVoice chạy trên GPU qua MPS); ~5 GB lúc nghỉ sau khi đã nạp model.
- Job 6 phút audio, 5 giọng: sinh trong 7 phút, tốc độ không chậm dần (RTF đầu/cuối: VieNeu 0.28/0.28, OmniVoice 2.68/2.69).
- Chạy được hoàn toàn offline sau lần tải model đầu tiên (`HF_HUB_OFFLINE=1`).

## Giọng & bản quyền

- Repo không kèm clip giọng của bên thứ ba. Benchmark trong `bench/` clone từ clip giọng tổng hợp Gemini của dataset `slexisvn/emotion-tts-vietnamese-sample`; các clip đó không kèm theo (tải lại bằng `bench/common/pick_refs.py`), chỉ giữ file nghe kết quả để so sánh.
- VieNeu: Apache-2.0. OmniVoice fine-tune: Apache-2.0; bộ mã hóa audio đi kèm theo Boson Higgs Audio 2 Community License.
- Dùng cho mục đích cá nhân. Chỉ clone giọng khi có quyền sử dụng giọng đó.

## Phát triển

```bash
uv sync                               # .venv cho repo, dùng voices/ và lexicon.yaml trong repo
uv run --group dev pytest             # unit test
uv run python scripts/mcp_smoke.py    # end-to-end qua MCP stdio (cần model)
ARCHI_TTS_HOME=~/.archi-tts/home uv run python scripts/control_check.py   # các script đo cần giọng clone
ARCHI_TTS_SMOKE_CMD=bin/archi-tts-mcp uv run python scripts/mcp_smoke.py   # qua launcher của plugin
```

### Nhánh và phát hành

- `main`: chỉ chứa bản đã phát hành, là thứ người cài plugin nhận được. Không commit thẳng.
- `develop`: làm việc hằng ngày ở đây. Push lên `develop` không chạy CI.
- Phát hành: tăng `version` trong `.claude-plugin/plugin.json` (chỗ duy nhất chứa version) và cập nhật `CHANGELOG.md` trên `develop`, mở PR `develop → main` (CI chạy một lần), merge khi xanh, rồi gắn tag `vX.Y.Z` trên `main` (CI kiểm tra tag khớp version).
