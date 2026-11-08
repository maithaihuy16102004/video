"""Các engine TTS (pluggable) — v2 robust.

- EdgeTTSEngine : edge-tts — giọng neural Việt, miễn phí. Cần internet.
  Tích hợp retry thông minh + adaptive delay để vượt rate-limit Microsoft.
- MeloTTSEngine : MeloTTS — offline, nhanh trên CPU.
- XTTSEngine    : XTTS v2 — voice cloning từ 1 file mẫu ~3s.
"""

import abc
import subprocess
import sys
import time
import os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class TTSEngine(abc.ABC):
    """Giao diện chung cho mọi engine TTS."""
    name = "base"

    @abc.abstractmethod
    def available(self) -> bool: ...

    @abc.abstractmethod
    def synthesize(self, text, voice, out_path, **kwargs): ...


def _generate_silent_audio(out_path: str, duration: float = 3.0):
    """Tạo audio im lặng bằng FFmpeg làm fallback cuối cùng."""
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=mono",
        "-t", str(duration),
        "-c:a", "libmp3lame", "-b:a", "128k",
        out_path
    ], check=True, capture_output=True)


class EdgeTTSEngine(TTSEngine):
    """edge-tts với retry thông minh + adaptive cooldown."""

    name = "edge-tts"
    # Cooldown tối thiểu giữa các lần gọi (class-level) để tránh rate-limit
    _last_call_time = 0.0
    _min_cooldown = 3.0  # giây

    def available(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except Exception:
            return False

    def _wait_cooldown(self):
        """Đợi đủ cooldown giữa các lần gọi edge-tts."""
        elapsed = time.time() - EdgeTTSEngine._last_call_time
        if elapsed < EdgeTTSEngine._min_cooldown:
            wait = EdgeTTSEngine._min_cooldown - elapsed
            time.sleep(wait)

    def synthesize(self, text, voice, out_path, rate=None, pitch=None,
                   volume=None, **kwargs):
        import asyncio
        import edge_tts

        def _fmt(v, suffix, default):
            if not v:
                return default
            s = str(v).strip()
            low = s.lower()
            if suffix.lower() not in low:
                s += suffix
            if s[0] not in "+-":
                s = "+" + s
            return s

        # Chuẩn hoá text
        clean_text = text.replace("%", " phần trăm ")
        clean_text = clean_text.replace("&", " và ")
        clean_text = clean_text.replace("<", " ").replace(">", " ")

        kwargs_comm = {}
        if rate:
            kwargs_comm["rate"] = _fmt(rate, "%", "+0%")
        if pitch:
            kwargs_comm["pitch"] = _fmt(pitch, "Hz", "+0Hz")
        if volume:
            kwargs_comm["volume"] = _fmt(volume, "%", "+0%")

        # Giọng dự phòng
        voices = [voice]
        if voice != "vi-VN-NamMinhNeural":
            voices.append("vi-VN-NamMinhNeural")
        if voice != "vi-VN-HoaiMyNeural":
            voices.append("vi-VN-HoaiMyNeural")

        async def _try_one(v):
            """Thử 1 giọng, retry 4 lần với backoff 3/5/8/12s."""
            delays = [3, 5, 8, 12]
            for attempt in range(len(delays) + 1):
                try:
                    comm = edge_tts.Communicate(clean_text, v, **kwargs_comm)
                    await comm.save(out_path)
                    # Kiểm tra file thực sự có audio (>1KB)
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                        return True
                    raise RuntimeError("File audio quá nhỏ (<1KB)")
                except Exception as e:
                    if attempt < len(delays):
                        w = delays[attempt]
                        print(f"  [tts] Retry {attempt+1} giọng {v} "
                              f"({type(e).__name__}), chờ {w}s...")
                        await asyncio.sleep(w)
                    else:
                        print(f"  [tts] Giọng {v} thất bại hoàn toàn.")
            return False

        async def _try_without_rate(v):
            """Thử lại không truyền rate/pitch (đề phòng rate format lỗi)."""
            try:
                comm = edge_tts.Communicate(clean_text, v)
                await comm.save(out_path)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                    return True
            except Exception:
                pass
            return False

        async def _run():
            for v in voices:
                if await _try_one(v):
                    return
            # Thử lại không truyền rate/pitch
            if kwargs_comm:
                print("  [tts] Thử lại không rate/pitch...")
                for v in voices:
                    if await _try_without_rate(v):
                        return
            # Fallback cuối → audio im lặng
            print("  [tts] ⚠ Tạo audio placeholder (edge-tts rate-limited).")
            est_dur = max(2.0, len(text) * 0.07)
            _generate_silent_audio(out_path, duration=est_dur)

        self._wait_cooldown()
        asyncio.run(_run())
        EdgeTTSEngine._last_call_time = time.time()
        return out_path


class MeloTTSEngine(TTSEngine):
    """MeloTTS — offline, nhanh trên CPU."""
    name = "melo"

    def available(self) -> bool:
        try:
            import melo  # noqa: F401
            return True
        except Exception:
            return False

    def synthesize(self, text, voice, out_path, rate=None, **kwargs):
        from melo.api import TTS
        speed = 1.0
        if rate is not None:
            s = str(rate).replace("%", "")
            try:
                speed = 1.0 + float(s) / 100.0
            except ValueError:
                speed = 1.0
        model = TTS(language="VI", device=kwargs.get("device", "cpu"))
        speaker_ids = model.hps.data.spk2id
        spk = voice if voice in speaker_ids else next(iter(speaker_ids))
        model.tts_to_file(text, spk, out_path, speed=speed)
        return out_path


class XTTSEngine(TTSEngine):
    """XTTS v2 — voice cloning."""
    name = "xtts"

    def available(self) -> bool:
        try:
            from TTS.api import TTS  # noqa: F401
            return True
        except Exception:
            return False

    def synthesize(self, text, voice, out_path, sample_wav=None, **kwargs):
        if not sample_wav:
            raise ValueError("XTTS cần sample_wav.")
        from TTS.api import TTS
        model = kwargs.get("model") or "tts_models/multilingual/multi-dataset/xtts_v2"
        tts = TTS(model)
        tts.tts_to_file(text=text, speaker_wav=sample_wav,
                        language=kwargs.get("language", "vi"),
                        file_path=out_path)
        return out_path


class VieNeuTTSEngine(TTSEngine):
    """VieNeu-TTS v3 Turbo (48kHz) — studio-grade on-device neural TTS & voice cloning cho tiếng Việt."""
    name = "vieneu"
    _instance = None
    _VOICE_ALIASES = {
        "Minh Quân": "Hải Đăng",
        "Ái Hân": "Thùy Dung",
        "Hữu Quân": "Xuân Vĩnh",
        "Anh Khôi": "Thiện Minh",
        "Mạnh Dũng": "Phạm Tuyên",
        "Xuân Tiên": "Mai Anh",
        "vi-VN-NamMinhNeural": "Thiện Minh",
        "namminh": "Thiện Minh",
        "vi-VN-HoaiMyNeural": "Thùy Dung",
        "hoaimy": "Thùy Dung",
    }

    def available(self) -> bool:
        try:
            import vieneu  # noqa: F401
            return True
        except Exception:
            return False

    @classmethod
    def get_model(cls):
        if cls._instance is None:
            from pathlib import Path
            from vieneu import Vieneu
            from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine, _CODEC_REPO

            root_models = Path(__file__).resolve().parents[1] / "models"
            v3_dir = root_models / "v3turbo_int8"
            codec_dir = root_models / "moss_codec"

            if v3_dir.exists() and codec_dir.exists():
                orig_fetch = OnnxV3LiteEngine._fetch
                OnnxV3LiteEngine._fetch = staticmethod(
                    lambda repo, files, sub: codec_dir if repo == _CODEC_REPO else orig_fetch(repo, files, sub)
                )
                cls._instance = Vieneu(mode="v3turbo", onnx_dir=str(v3_dir), threads=6)
                for old_name, target_name in cls._VOICE_ALIASES.items():
                    cls._instance._register_aliases(target_name, [old_name])
            else:
                cls._instance = Vieneu(mode="v3nano")
        return cls._instance

    def synthesize(self, text, voice, out_path, sample_wav=None, **kwargs):
        v_name = voice.replace("vieneu-", "").strip() if voice.startswith("vieneu-") else voice
        v_name = self._VOICE_ALIASES.get(v_name, v_name) or "Thiện Minh"

        tts = self.get_model()
        ref_audio = sample_wav or kwargs.get("ref_audio")
        temperature = float(kwargs.get("temperature", 0.78))
        top_k = int(kwargs.get("top_k", 25))
        if ref_audio:
            audio = tts.infer(text=text, ref_audio=ref_audio, temperature=temperature, top_k=top_k)
        else:
            if hasattr(tts, "resolve_voice_name") and not tts.resolve_voice_name(v_name):
                v_name = "Thiện Minh"
            audio = tts.infer(text=text, voice=v_name, temperature=temperature, top_k=top_k)
        tts.save(audio, str(out_path))
        return out_path


def get_engine(name="edge-tts") -> TTSEngine:
    key = (name or "edge-tts").strip().lower()
    if key in ("vieneu", "vieneu-tts"):
        return VieNeuTTSEngine()
    if key in ("edge-tts", "edge", "default"):
        return EdgeTTSEngine()
    if key == "melo":
        return MeloTTSEngine()
    if key in ("xtts", "xtts-v2", "clone"):
        return XTTSEngine()
    raise ValueError(f"Engine không xác định: {name}")
