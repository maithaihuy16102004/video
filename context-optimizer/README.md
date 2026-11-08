# context-optimizer — Tối ưu Token & Context cho pipeline video AI

Bộ công cụ thực thi **chiến lược 4 lớp chống "vung tay quá trán" token** khi đưa
log của các tiến trình render video (FFmpeg, Whisper, motion graphics) vào LLM.

Mục tiêu: **giảm 70–90% token rác**, tận dụng **Context Caching** để chỉ trả ~1/10
giá input cho phần dữ liệu lặp lại, và sinh **báo cáo daily** từ log mà không
làm phình cửa sổ ngữ cảnh.

---

## 4 lớp chiến lược

| Lớp | Tên | Module | Hiệu quả |
|---|---|---|---|
| 1 | Chunking & Map-Reduce | `chunker.py`, `report.py` | Giảm context tích tụ, không phải đọc lại log thừa |
| 2 | Regex filter (pre-processing) | `filter.py` | Cắt **70–90%** token rác |
| 3 | Context Caching | `cache.py`, `client.py` | Phần tĩnh chỉ ~**1/10** giá input |
| 4 | Metadata JSON (ffprobe) | `metadata.py` | Không nạp dữ liệu nhị phân vào context |

---

## Cài đặt

Không cần thư viện ngoài (chỉ dùng `urllib`, `json`, `re`, `subprocess` của stdlib).

```bash
# chỉ cần Python 3.10+ và FFmpeg trong PATH (cho metadata)
```

Để gọi API sinh báo cáo, đặt API key:

```bash
# Windows PowerShell
$env:DEEPSEEK_API_KEY = "sk-..."

# Linux/macOS
export DEEPSEEK_API_KEY="sk-..."
```

## Cách dùng

```bash
cd D:\Agent\context-optimizer

# 1) Lọc log rác (Layer 2)
python optimize.py filter samples/ffmpeg.log -o output/cleaned.log

# 2) Trích metadata video (Layer 4)
python optimize.py metadata video_goc.mp4 -o output/meta.json

# 3) Thống kê token rác (không cần API)
python optimize.py stats samples/ffmpeg.log

# 4) Sinh báo cáo daily (Layer 1+2+3, cần API key)
python optimize.py report samples/ffmpeg.log -o output/daily_report.md --chunk by_time
```

## Chi tiết từng lớp

### Lớp 1 — Chunking & Map-Reduce (`chunker.py`, `report.py`)

Thay vì ném cả file log cả ngày (hàng chục nghìn dòng) vào LLM:

1. **Map**: chia log thành các đoạn nhỏ theo 3 chiến lược:
   - `by_time` — theo khung giờ (VD mỗi 1 giờ)
   - `by_process` — theo tiến trình (cắt video / whisper / render)
   - `by_lines` — theo số dòng cố định
   - `auto` — tự chọn (log nhỏ thì 1 chunk duy nhất)
2. Gửi từng đoạn lấy tóm tắt gạch đầu dòng (Map).
3. **Reduce**: gom các tóm tắt lại thành báo cáo Markdown hoàn chỉnh.

```python
from report import generate_daily_report
from client import DeepSeekClient

client = DeepSeekClient()  # đọc DEEPSEEK_API_KEY
result = generate_daily_report(raw_log, client, project_name="AI Video Editor",
                               chunk_strategy="by_process")
print(result["report"])
print(result["cache_summary"])   # thống kê cache hit/miss
```

### Lớp 2 — Regex filter (`filter.py`)

Xóa các dòng tiến trình vô giá trị (`frame=`, `size=`, `bitrate=`, `[progress]`,
`NN% done`, `time=`, `speed=`) và chỉ giữ dòng có **mốc thời gian, tên file,
lỗi (Error/Warning), sự kiện Completed/Started**.

```python
from filter import filter_log

clean = filter_log(raw_log_text)   # 22 dòng -> 10 dòng (giảm 51% ở mẫu nhỏ;
                                   # log thật render video giảm 70-90%)
```

### Lớp 3 — Context Caching (`cache.py`, `client.py`)

DeepSeek hỗ trợ **Context Caching on Disk**: phần input lặp lại được lấy từ cache
với giá `$0.014/M token` (cache hit) thay vì `$0.14/M` (cache miss) — **tiết kiệm 90%**.

> Quy tắc vàng: cache chỉ **HIT khi phần đầu (prefix) khớp chính xác từ token 0**.
> Vì vậy `cache.py` đặt phần TĨNH (system prompt + template) ở ĐẦU, phần ĐỘNG
> (dữ liệu log) ở CUỐI, và giữ phần tĩnh byte-identical qua các lần gọi.

```python
from cache import build_report_system_prompt, build_messages

system_prompt = build_report_system_prompt("AI Video Editor")  # TĨNH, giữ nguyên
msgs = build_messages(system_prompt, dynamic_content=clean_log)  # ĐỘNG ở cuối
resp = client.chat(msgs)
print(resp["cache_hit_ratio"])   # tỉ lệ token được cache
print(resp["cost_usd"])          # chi phí ước tính
```

### Lớp 4 — Metadata JSON (`metadata.py`)

Dùng `ffprobe` trích thông số cốt lõi thành JSON siêu nhẹ thay vì gửi dữ liệu
video thô/nhị phân vào context:

```json
{
  "file_name": "demo_ai.mp4",
  "size_mb": 1.19,
  "duration": "00:00:22",
  "resolution": "1080x1920",
  "fps": 30.0,
  "video_codec": "h264"
}
```

```bash
python optimize.py metadata video_goc.mp4 -o output/meta.json
# hoặc quét cả thư mục
python optimize.py metadata ./output/ -o output/all_meta.json
```

---

## Lưu ý quan trọng về model

Tài liệu gốc nhắc đến `"deepseek-flash"` / `"DeepSeek V4.1 Flash"` — đây **không
phải tên model thật** của DeepSeek API. Các model hiện có:
- `deepseek-chat` — DeepSeek-V3 (mặc định, rẻ, phù hợp tóm tắt log)
- `deepseek-reasoner` — DeepSeek-R1 (suy luận sâu, đắt hơn)

Thay đổi model bằng `--model` hoặc trong `config/default.json`. Giá token trong
`client.py` có thể cập nhật theo [bảng giá chính thức](https://api-docs.deepseek.com/quick_start/pricing).

---

## Nguồn tham khảo (đã đối chiếu)

**Context Caching (Lớp 3):**
- [DeepSeek API introduces Context Caching on Disk — tài liệu chính thức](https://api-docs.deepseek.com/news/news0802) — cache hit `$0.014/M` vs miss `$0.14/M`, tiết kiệm tới 90%; 2 field `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`.
- [DeepSeek Context Caching guide (kv_cache)](https://api-docs.deepseek.com/guides/kv_cache) — quy tắc hit: prefix phải khớp **đầy đủ** một "cache prefix unit" từ token 0; cơ chế persistence ở biên request, phát hiện prefix chung, và mốc token cố định.
- Anthropic Prompt Caching (cùng nguyên lý prefix-cache, được thảo luận rộng rãi trên r/ClaudeAI và r/LocalLLaMA): đặt nội dung tĩnh ở đầu, nội dung động ở cuối để cache hit — [tổng hợp prompt-caching best practices](https://github.com/e-t-y-b/etyb-skills/blob/main/stacks/anthropic-claude/prompt-caching.md).

**Map-Reduce cho log (Lớp 1):**
- [Corelight — Leveraging Map-Reduce & LLMs for Network Detection](https://corelight.com/blog/map-reduce-llms-cybersecurity-network-detection) — mô hình chia log lớn thành chunk rồi map-reduce qua LLM.

**Log filtering / pre-processing (Lớp 2):**
- [VersusControl — "Learn Normal, Flag New" (AI agent for monitoring)](https://raw.githubusercontent.com/VersusControl/devops-ai-guidelines/refs/heads/main/04-ai-agent-for-monitoring/04-learn-normal-flag-new.md) — lọc log giữ dòng bất thường, bỏ dòng lặp vô giá trị trước khi nạp LLM.

> Trên X (Twitter) và Reddit, các thảo luận phổ biến về chủ đề này tập trung ở
> `r/LocalLLaMA`, `r/ClaudeAI`, `r/LLMDevs` (prompt caching), và các thread của
> cộng đồng DeepSeek về "context caching on disk". Nguyên tắc được lặp lại nhiều
> nhất: **prefix ổn định → cache hit → giảm 90% chi phí input**.
