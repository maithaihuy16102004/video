# AI Clip Studio

Frontend + hosted planning API for turning Vietnamese scripts into short-video jobs.

## Run locally

```powershell
# Một lệnh: mở backend + frontend + trình duyệt
.\start-studio.ps1

# Hoặc chạy riêng từng phần
# Terminal 1: hosted-style frontend
npm run dev

# Terminal 2: local Remotion/FFmpeg worker
cd D:\Agent
python pipeline\studio_api.py
```

The frontend talks only to its own `/api/*` routes. Those routes use
`RENDER_BACKEND_URL` and default to `http://127.0.0.1:8787`, so the same code can use
a local renderer now and a remote renderer later without changing the frontend.

## Voice clarity chain

`edge-tts → high-pass 85 Hz → low-pass 12.5 kHz → speech compressor → loudnorm
-16 LUFS / -1.2 dBTP → mono 44.1 kHz`. The processed voice is generated before
visual rendering and background music is mixed afterward.
