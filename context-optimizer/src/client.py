"""DeepSeek API client (OpenAI-compatible) dùng thư viện chuẩn urllib.

Hỗ trợ đọc thống kê Context Caching (prompt_cache_hit_tokens / miss_tokens)
để theo dõi tiết kiệm chi phí. Không cần `requests`/`httpx`.
"""

import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_BASE_URL = "https://api.deepseek.com/chat/completions"

# Giá token (USD / 1M token) — cập nhật theo bảng giá hiện tại của DeepSeek
PRICING = {
    "deepseek-chat": {
        "input": 0.14,        # cache miss
        "input_cached": 0.014,  # cache hit
        "output": 0.28,
    },
    "deepseek-reasoner": {
        "input": 0.55,
        "input_cached": 0.14,
        "output": 2.19,
    },
}


class DeepSeekClient:
    def __init__(self, api_key: str = None, base_url: str = None,
                 model: str = "deepseek-chat", timeout: int = 120):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = base_url or DEFAULT_BASE_URL
        self.model = model
        self.timeout = timeout
        # lưu lịch sử cache để thống kê tích lũy
        self.total_hit_tokens = 0
        self.total_miss_tokens = 0
        self.total_output_tokens = 0
        self.num_calls = 0

    def chat(self, messages, temperature=0.3, max_tokens=2000,
             stream=False, **extra) -> dict:
        """Gửi 1 yêu cầu chat. Trả dict: {content, usage, cost, cache_hit_ratio}."""
        if not self.api_key:
            raise RuntimeError(
                "Chưa có API key. Đặt biến môi trường DEEPSEEK_API_KEY "
                "hoặc truyền api_key khi khởi tạo DeepSeekClient.")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        payload.update(extra)

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API HTTP {e.code}: {detail}") from e

        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})

        hit = usage.get("prompt_cache_hit_tokens", 0)
        miss = usage.get("prompt_cache_miss_tokens", 0)
        out = usage.get("completion_tokens", 0)

        self.total_hit_tokens += hit
        self.total_miss_tokens += miss
        self.total_output_tokens += out
        self.num_calls += 1

        cost = self._cost(hit, miss, out)
        total_input = hit + miss
        ratio = (hit / total_input) if total_input else 0.0

        return {
            "content": content,
            "usage": usage,
            "cache_hit_tokens": hit,
            "cache_miss_tokens": miss,
            "output_tokens": out,
            "cache_hit_ratio": ratio,
            "cost_usd": cost,
        }

    def _cost(self, hit, miss, out):
        p = PRICING.get(self.model, PRICING["deepseek-chat"])
        return (hit * p["input_cached"] + miss * p["input"] +
                out * p["output"]) / 1_000_000

    def summary(self) -> dict:
        """Thống kê tích lũy cache + chi phí ước tính."""
        p = PRICING.get(self.model, PRICING["deepseek-chat"])
        total_cost = (self.total_hit_tokens * p["input_cached"] +
                      self.total_miss_tokens * p["input"] +
                      self.total_output_tokens * p["output"]) / 1_000_000
        return {
            "calls": self.num_calls,
            "hit_tokens": self.total_hit_tokens,
            "miss_tokens": self.total_miss_tokens,
            "output_tokens": self.total_output_tokens,
            "cache_hit_ratio": (self.total_hit_tokens /
                                max(1, self.total_hit_tokens + self.total_miss_tokens)),
            "estimated_cost_usd": round(total_cost, 6),
        }
