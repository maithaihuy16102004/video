"""Provider seams for AI Affiliate Studio — Shopee Edition.

This module defines the documented boundaries between the affiliate
pipeline and the outside world: downloading, OCR, text-to-speech, and
Gemini. Mai's backend quality bar requires clean organization with
reusable, upgradeable code: each seam is a small interface (a
``typing.Protocol``) with an explicit contract, a thin adapter over
the existing Phase-1 implementation, a fake for tests, and a registry
entry. Orchestration/wrapping only — zero duplicated business logic.
The adapters import the real implementations; they never re-implement
them.

Seams
-----
``downloader``
    Fetch a remote video file to disk. Contract: ``fetch(url,
    dest_dir)`` returns a :class:`DownloadResult` (file path +
    metadata) or raises a structured :class:`DownloadFailure` with a
    stable reason code. No cookies/credentials support exists in the
    interface — by design. The concrete implementation is
    :class:`YtDlpDownloader` (subprocess ``yt-dlp``); the ingest gate
    in ``video/ingest.py`` still runs BEFORE any downloader call, and
    ``link_input.handle_link_submit`` enforces that ordering.

``ocr``
    Chinese text recognition + temporal tracking. Thin adapter over
    Subagent A's ``video/ocr.py`` (``get_ocr_engine`` /
    ``track_detections``). Imported, never duplicated.

``tts``
    Vietnamese speech synthesis. Thin adapter over Subagent B's
    ``voice.py`` (which itself uses the shared ``tts_cli_provider``
    seam on this VM and real VieNeu on Mai's machine). Imported,
    never duplicated.

``gemini``
    Translation/script calls. The DEFAULT implementation while no
    Gemini key exists is :class:`UnavailableGeminiClient`: it never
    calls any API, returns ``needs_human_review=True`` and zero
    fabricated segments. :class:`TranslationGeminiClient` is the thin
    adapter over ``translation.translate_segments`` for use once a
    key is wired; ALL key handling lives in ``translation.py``
    (``api_key`` parameter / the ``GEMINI_API_KEY`` read that module
    already performs) — this module adds no new secret paths and
    reads no credentials. When Mai stores the key through the
    connector flow, the connector doc wires the backend to use it and
    Stage 2 swaps the registry default from
    ``labelled_unavailable`` to ``translation_adapter``; no pipeline
    code changes.

Registry
--------
``REGISTRY`` / :func:`get_provider` resolve ``(seam, name)`` to a
fresh provider instance. Defaults: ``downloader`` -> ``yt-dlp``,
``ocr`` -> ``default``, ``tts`` -> ``voice``, ``gemini`` ->
``labelled_unavailable``. Every seam also registers a ``fake``
implementation for tests. Fakes are TEST-ONLY and say so in their
names/docstrings; they must never be wired into a production path.

No module in this file touches the network except through the
injected/concrete downloader, and no code here invents product
facts, prices, links, or testimonials.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

# ---------------------------------------------------------------------
# Downloader seam
# ---------------------------------------------------------------------

# Stable DownloadFailure reason codes.
REASON_UNSUPPORTED_URL = "UNSUPPORTED_URL"
REASON_COOKIES_REQUIRED = "COOKIES_REQUIRED"
REASON_AUTH_REQUIRED = "AUTH_REQUIRED"
REASON_NETWORK_ERROR = "NETWORK_ERROR"
REASON_NOT_FOUND = "NOT_FOUND"
REASON_NOT_AVAILABLE = "NOT_AVAILABLE"
REASON_DOWNLOAD_FAILED = "DOWNLOAD_FAILED"

DOWNLOAD_FAILURE_REASONS = (
    REASON_UNSUPPORTED_URL,
    REASON_COOKIES_REQUIRED,
    REASON_AUTH_REQUIRED,
    REASON_NETWORK_ERROR,
    REASON_NOT_FOUND,
    REASON_NOT_AVAILABLE,
    REASON_DOWNLOAD_FAILED,
)

# Fallback yt-dlp location when the binary is not on PATH (the venv
# used by the Douyin fetch probes on this VM). Checked only when the
# explicit path and PATH resolution both miss, and only when the file
# actually exists — absence is an honest NOT_AVAILABLE, never a crash.
_VENV_YTDLP = Path("/home/hatch/workspace/.venvs/ytdlp/bin/yt-dlp")


class DownloadFailure(Exception):
    """Structured download failure.

    ``reason`` is one of the ``REASON_*`` codes above; ``detail`` is
    a short human-readable explanation (a truncated tool message),
    safe to log and to show to the user alongside the mapped
    Vietnamese explanation in ``link_input``. Raising this instead of
    returning a partial/empty result is what keeps a failed fetch
    from ever being reported as a success.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)

    def to_dict(self) -> dict[str, str]:
        return {"reason": self.reason, "detail": self.detail}


@dataclass
class DownloadResult:
    """A completed download: the file on disk + honest metadata.

    ``metadata`` carries only measured/observed facts (the URL that
    was fetched, the binary used, the file size). It never carries
    product facts, titles claimed without evidence, or anything the
    downloader did not actually observe.
    """

    path: str
    downloader_name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Downloader(Protocol):
    """Download one remote video file to a directory.

    Contract:
      * Inputs: ``url`` (http/https, already gate-checked by the
        caller — the downloader never decides authorization) and
        ``dest_dir`` (created when missing).
      * Output: a :class:`DownloadResult` whose ``path`` is an
        existing file on success.
      * Errors: raises :class:`DownloadFailure` with a stable reason
        code on every failure mode (unsupported URL, cookies/auth
        required, network error, not found, tool unavailable). It
        never returns a path to a missing/partial file, and never
        silently succeeds.
      * No cookies, no credentials, no login: the interface has no
        way to supply them, by design.
    """

    name: str

    def fetch(self, url: str, dest_dir: str | Path) -> DownloadResult:
        """Fetch ``url`` into ``dest_dir``. See the class contract."""
        ...

    def status(self) -> dict[str, Any]:
        """Availability report: at least ``available`` (bool) and
        ``status`` (``"AVAILABLE"`` / ``"NOT_AVAILABLE"``). Never
        raises for a missing tool."""
        ...


def resolve_ytdlp_binary(explicit: str | Path | None = None) -> str | None:
    """Resolve the yt-dlp binary path.

    Resolution order: explicit path > ``PATH`` lookup > the venv
    binary ``/home/hatch/workspace/.venvs/ytdlp/bin/yt-dlp`` when it
    exists. Returns ``None`` only when nothing resolves; an explicit
    path is returned verbatim so callers can report exactly what was
    configured (availability is checked separately).
    """
    if explicit:
        return str(explicit)
    on_path = shutil.which("yt-dlp")
    if on_path:
        return on_path
    if _VENV_YTDLP.is_file():
        return str(_VENV_YTDLP)
    return None


class YtDlpDownloader:
    """Concrete downloader: the ``yt-dlp`` CLI via subprocess.

    Command shape (fixed, no cookies/credentials flags ever):
    ``yt-dlp --no-playlist --no-warnings -o <dest>/download.%(ext)s
    <url>``. The binary path is configurable; the default resolution
    is :func:`resolve_ytdlp_binary`. A missing binary is reported by
    :meth:`status` as ``NOT_AVAILABLE`` and makes :meth:`fetch`
    raise ``DownloadFailure(NOT_AVAILABLE)`` — never a crash, never
    a fake success.

    This class also implements the ``video/ingest.py`` downloader
    callable shape — ``__call__(url, target_path)`` — by fetching
    into the target's directory and moving the result onto the
    target path, so it can be injected into ``ingest_source``
    directly or through :func:`as_ingest_downloader`.
    """

    name = "yt-dlp"

    def __init__(self, binary: str | Path | None = None,
                 timeout_sec: int = 600) -> None:
        self._explicit = str(binary) if binary else None
        self._binary = resolve_ytdlp_binary(binary)
        self._timeout_sec = timeout_sec
        if self._explicit is not None:
            self._resolution = "explicit"
        elif self._binary and shutil.which("yt-dlp") == self._binary:
            self._resolution = "PATH"
        elif self._binary:
            self._resolution = "venv"
        else:
            self._resolution = "none"

    @property
    def binary(self) -> str | None:
        """The resolved binary path (``None`` when unresolvable)."""
        return self._binary

    @property
    def available(self) -> bool:
        """True only when the resolved binary exists and is runnable."""
        return bool(self._binary) and Path(self._binary).is_file() and (
            os.access(self._binary, os.X_OK))

    def status(self) -> dict[str, Any]:
        """Honest availability report; never raises, never crashes."""
        return {
            "available": self.available,
            "status": "AVAILABLE" if self.available else "NOT_AVAILABLE",
            "binary": self._binary,
            "resolution": self._resolution,
            "detail": ("yt-dlp binary found"
                       if self.available else
                       "yt-dlp binary not found: explicit path > PATH > "
                       "/home/hatch/workspace/.venvs/ytdlp/bin/yt-dlp"),
        }

    @staticmethod
    def classify_stderr(stderr: str) -> str:
        """Map yt-dlp stderr text to a DownloadFailure reason code.

        The two Douyin outcomes measured on 2026-11-12 are covered
        first: ``Unsupported URL`` (share URL form) and ``Fresh
        cookies ... are needed`` (canonical URL form).
        """
        text = (stderr or "").lower()
        if "unsupported url" in text:
            return REASON_UNSUPPORTED_URL
        if ("cookies" in text or "log in" in text
                or "login required" in text or "sign in" in text
                or "authentication" in text or "please log in" in text):
            return REASON_COOKIES_REQUIRED
        if ("http error 404" in text or "404 not found" in text
                or "video unavailable" in text
                or "this video is unavailable" in text
                or "not found" in text and "error" in text):
            return REASON_NOT_FOUND
        if ("network" in text or "connection" in text
                or "timed out" in text or "timeout" in text
                or "name resolution" in text
                or "temporary failure" in text
                or "unable to download" in text
                or "urlopen error" in text):
            return REASON_NETWORK_ERROR
        return REASON_DOWNLOAD_FAILED

    def fetch(self, url: str, dest_dir: str | Path) -> DownloadResult:
        """Fetch ``url`` with yt-dlp. See the Downloader contract."""
        if not self.available:
            raise DownloadFailure(
                REASON_NOT_AVAILABLE,
                "yt-dlp binary not found "
                f"(configured: {self._binary or 'none'}); no download "
                "was attempted")
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        template = str(dest / "download.%(ext)s")
        command = [str(self._binary), "--no-playlist", "--no-warnings",
                   "-o", template, url]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True,
                timeout=self._timeout_sec)
        except subprocess.TimeoutExpired as exc:
            raise DownloadFailure(
                REASON_NETWORK_ERROR,
                f"yt-dlp timed out after {self._timeout_sec}s") from exc
        except OSError as exc:
            raise DownloadFailure(
                REASON_NOT_AVAILABLE,
                f"could not run yt-dlp binary {self._binary}: {exc}") from exc
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        if result.returncode != 0:
            raise DownloadFailure(
                self.classify_stderr(combined),
                (result.stderr or result.stdout or "").strip()[-300:])
        produced = [p for p in sorted(dest.glob("download.*"))
                    if p.is_file()
                    and p.suffix.lower() not in (".part", ".ytdl", ".json")
                    and not p.name.endswith(".part")]
        if not produced:
            raise DownloadFailure(
                REASON_DOWNLOAD_FAILED,
                "yt-dlp exited successfully but produced no video file")
        # Prefer the largest produced file (a merged download beats a
        # stray sidecar when several outputs appear).
        chosen = max(produced, key=lambda p: p.stat().st_size)
        return DownloadResult(
            path=str(chosen),
            downloader_name=self.name,
            metadata={"url": url, "binary": self._binary,
                      "file_size_bytes": chosen.stat().st_size})

    def __call__(self, url: str, target: Path) -> Path:
        """Ingest-callable shape: ``(url, target_path) -> Path``.

        Fetches into the target's directory, then moves the result
        onto ``target`` (``ingest_source`` probes and re-homes the
        file from there). Raises the same DownloadFailure codes as
        :meth:`fetch`.
        """
        result = self.fetch(url, Path(target).parent)
        produced = Path(result.path)
        target = Path(target)
        if produced.resolve() != target.resolve():
            os.replace(produced, target)
        return target


def as_ingest_downloader(downloader: Any) -> Callable[[str, Path], Path]:
    """Adapt a fetch-style Downloader to the ``ingest_source``
    callable contract ``(url, target_path) -> Path``.

    Plain callables (the ``video/ingest.py`` ``Downloader`` shape,
    including test fakes) pass through unchanged. Objects exposing
    ``fetch`` are wrapped: fetch into the target's directory, move
    the result onto the target path. DownloadFailure propagates
    unchanged so the caller can map reason codes honestly.
    """
    if hasattr(downloader, "fetch"):
        def _call(url: str, target: Path) -> Path:
            result = downloader.fetch(url, Path(target).parent)
            produced = Path(result.path)
            target = Path(target)
            if produced.resolve() != target.resolve():
                import os
                os.replace(produced, target)
            return target
        return _call
    return downloader


class FakeDownloader:
    """TEST-ONLY fake downloader: copies a local fixture file.

    ``fixture_path`` is the file every fetch returns (copied into the
    destination directory). Calls are recorded in ``calls``. Never
    touches the network. Must never be wired into a production path.
    """

    name = "fake-test"

    def __init__(self, fixture_path: str | Path) -> None:
        self.fixture_path = Path(fixture_path)
        self.calls: list[str] = []

    def fetch(self, url: str, dest_dir: str | Path) -> DownloadResult:
        self.calls.append(url)
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / "download.mp4"
        shutil.copyfile(self.fixture_path, target)
        return DownloadResult(
            path=str(target), downloader_name=self.name,
            metadata={"url": url, "fixture": str(self.fixture_path),
                      "file_size_bytes": target.stat().st_size})

    def status(self) -> dict[str, Any]:
        return {"available": True, "status": "AVAILABLE",
                "binary": None, "resolution": "fake",
                "detail": "test-only fake downloader"}


class FailingDownloader:
    """TEST-ONLY downloader that always raises one DownloadFailure.

    Used to prove the failure mapping in ``link_input`` without any
    network access. ``reason``/``detail`` are the exact failure the
    fake reports on every call.
    """

    name = "failing-test"

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail or reason
        self.calls: list[str] = []

    def fetch(self, url: str, dest_dir: str | Path) -> DownloadResult:
        self.calls.append(url)
        raise DownloadFailure(self.reason, self.detail)

    def status(self) -> dict[str, Any]:
        return {"available": True, "status": "AVAILABLE",
                "binary": None, "resolution": "fake",
                "detail": "test-only failing downloader"}


# ---------------------------------------------------------------------
# OCR seam (thin adapter over affiliate/video/ocr.py)
# ---------------------------------------------------------------------

@runtime_checkable
class OCREngine(Protocol):
    """Chinese OCR + temporal tracking, behind one seam.

    Contract:
      * ``recognize(image_path)`` returns the engine's detections
        for one image file (the ``OCRDetection`` objects from
        ``video/ocr.py``). Raises ``RuntimeError`` with the honest
        engine status when no OCR engine is available — never an
        empty list presented as "no text found".
      * ``track(detections_by_time, frame_size, **kwargs)`` groups
        per-frame detections into tracked regions (the
        ``TrackingResult`` from ``video/ocr.py``) with the same
        arguments ``track_detections`` accepts. Pure grouping; it
        needs no engine instance.
      * ``status()`` reports availability without claiming results
        that were never produced.
    """

    name: str

    def recognize(self, image_path: str | Path) -> list[Any]:
        """Detect + recognize text in one image file."""
        ...

    def track(self, detections_by_time: dict[float, list[Any]],
              frame_size: tuple[int, int], **kwargs: Any) -> Any:
        """Group per-frame detections into tracked TextRegions."""
        ...

    def status(self) -> dict[str, Any]:
        """Availability report from the underlying engine probe."""
        ...


class DelegatingOCREngine:
    """Thin adapter over ``video/ocr.py``'s engine selection.

    The underlying engine is instantiated LAZILY (first
    :meth:`recognize` call) through ``get_ocr_engine`` — never at
    import or construction time, because instantiating RapidOCR may
    download models. :meth:`track` delegates directly to
    ``track_detections`` (pure logic, no engine needed). No OCR logic
    is duplicated here: recognition, tracking, classification, and
    the review queue all stay in ``video/ocr.py``.
    """

    name = "ocr-default"

    def __init__(self, preference: tuple[str, ...] = ("paddleocr",
                                                      "rapidocr_onnxruntime")) -> None:
        self._preference = preference
        self._engine: Any = None
        self._status: dict[str, Any] | None = None

    def _ensure_engine(self) -> Any:
        if self._engine is None and self._status is None:
            from .video.ocr import get_ocr_engine
            self._engine, self._status = get_ocr_engine(self._preference)
        if self._engine is None:
            raise RuntimeError(
                "no OCR engine available: "
                f"{(self._status or {}).get('attempts', [])}")
        return self._engine

    def recognize(self, image_path: str | Path) -> list[Any]:
        """Delegate to the lazily-selected underlying engine."""
        return self._ensure_engine().recognize(image_path)

    def track(self, detections_by_time: dict[float, list[Any]],
              frame_size: tuple[int, int], **kwargs: Any) -> Any:
        """Delegate to ``video/ocr.py::track_detections``."""
        from .video.ocr import track_detections
        return track_detections(detections_by_time, frame_size, **kwargs)

    def status(self) -> dict[str, Any]:
        """Last probed status, or an honest not-yet-probed report."""
        if self._status is not None:
            return dict(self._status)
        return {"engine": None, "available": False, "attempts": [],
                "detail": "OCR engine not probed yet; probing happens "
                          "lazily on the first recognize() call"}


class FakeOCREngine:
    """TEST-ONLY OCR fake: canned detections keyed by file name.

    ``recognize`` returns the canned detections for the image's file
    name (empty list when nothing was canned — test data, not a
    claim about real images). ``track`` delegates to the REAL
    ``track_detections`` so tracking behaviour is never faked.
    """

    name = "fake-test"

    def __init__(self, canned: dict[str, list[Any]] | None = None) -> None:
        self._canned = dict(canned or {})
        self.calls: list[str] = []

    def recognize(self, image_path: str | Path) -> list[Any]:
        self.calls.append(str(image_path))
        return list(self._canned.get(Path(image_path).name, []))

    def track(self, detections_by_time: dict[float, list[Any]],
              frame_size: tuple[int, int], **kwargs: Any) -> Any:
        from .video.ocr import track_detections
        return track_detections(detections_by_time, frame_size, **kwargs)

    def status(self) -> dict[str, Any]:
        return {"engine": "fake-test", "available": True, "attempts": [],
                "detail": "test-only fake OCR engine"}


# ---------------------------------------------------------------------
# TTS seam (thin adapter over affiliate/voice.py)
# ---------------------------------------------------------------------

@runtime_checkable
class TTSProvider(Protocol):
    """Vietnamese speech synthesis, behind one seam.

    Contract:
      * ``presets`` exposes the real preset table (preset name ->
        voice spec); ``preset_config(name)`` resolves one preset or
        raises ``VoiceError`` on an unknown name.
      * ``synthesize_script(script, job_dir, config)`` synthesises
        one real WAV per approved script segment (per-speaker
        dubbing via ``config.speaker_voices``) and returns the WAV
        paths aligned with the script segments. Raises on any
        failure — never a silent placeholder, never an English
        fallback.
      * ``preview(config, out_dir)`` synthesises the fixed preview
        phrase and returns its WAV path.
    """

    name: str

    @property
    def presets(self) -> dict[str, dict]:
        """The real preset table (see ``voice.VOICE_PRESETS``)."""
        ...

    def preset_config(self, preset: str) -> Any:
        """VoiceConfig for a preset name; raises on unknown presets."""
        ...

    def synthesize_script(self, script: Any, job_dir: Path,
                          config: Any) -> list[Path]:
        """One real WAV per approved script segment, in order."""
        ...

    def preview(self, config: Any, out_dir: Path) -> Path:
        """Synthesise the fixed preview phrase; return its WAV."""
        ...


class VoiceTTSProvider:
    """Thin adapter over ``affiliate/voice.py``.

    Every method delegates to ``voice.py`` unchanged: the preset
    table, per-speaker resolution, the shared ``tts_cli_provider``
    on this VM, and the real VieNeu binding on Mai's machine all
    stay owned by ``voice.py``. This adapter exists so pipeline code
    depends on the :class:`TTSProvider` seam (swappable, fakeable)
    instead of on module-level functions.
    """

    name = "voice"

    @property
    def presets(self) -> dict[str, dict]:
        from .voice import VOICE_PRESETS
        return VOICE_PRESETS

    def preset_config(self, preset: str) -> Any:
        from .voice import preset_config
        return preset_config(preset)

    def synthesize_script(self, script: Any, job_dir: Path,
                          config: Any) -> list[Path]:
        from .voice import synthesize_script
        return synthesize_script(script, Path(job_dir), config=config)

    def preview(self, config: Any, out_dir: Path) -> Path:
        from .voice import preview_voice
        return preview_voice(config, Path(out_dir))


class FakeTTSProvider:
    """TEST-ONLY TTS fake: records calls, writes placeholder files.

    The placeholder WAVs are empty files that only prove path/shape
    plumbing in tests — they are NOT audio and must never be
    presented as synthesized speech. The preset table is the REAL
    one (imported from ``voice.py``) so preset-name validation in
    tests exercises real data.
    """

    name = "fake-test"

    def __init__(self) -> None:
        self.synthesize_calls: list[dict[str, Any]] = []
        self.preview_calls: list[dict[str, Any]] = []

    @property
    def presets(self) -> dict[str, dict]:
        from .voice import VOICE_PRESETS
        return VOICE_PRESETS

    def preset_config(self, preset: str) -> Any:
        from .voice import preset_config
        return preset_config(preset)

    def synthesize_script(self, script: Any, job_dir: Path,
                          config: Any) -> list[Path]:
        self.synthesize_calls.append(
            {"segment_count": len(script.segments),
             "config": config, "approved": script.approved})
        voices_dir = Path(job_dir) / "voices"
        voices_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for seg in script.segments:
            target = voices_dir / f"{seg.segment_id}.wav"
            target.write_bytes(b"")
            seg.voice_wav = str(target)
            paths.append(target)
        return paths

    def preview(self, config: Any, out_dir: Path) -> Path:
        self.preview_calls.append({"config": config})
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / "voice_preview.wav"
        target.write_bytes(b"")
        return target


# ---------------------------------------------------------------------
# Gemini seam
# ---------------------------------------------------------------------

@runtime_checkable
class GeminiClient(Protocol):
    """Gemini translation/script calls, behind one seam.

    Contract:
      * ``translate(segments, product, mode=..., style=...,
        visible_demonstration=...)`` returns a
        ``TranslationRecord`` with SEPARATE original / translated /
        rewritten lists and an honest ``engine`` label
        (``"gemini:<model>"`` only when a real Gemini call produced
        the output, ``"fallback"`` otherwise).
      * When Gemini is unavailable, the implementation returns
        ``needs_human_review=True`` and ZERO translated/rewritten
        segments for DIRECT/NATURAL modes — it never fabricates a
        translation. Speaker ids on input segments are preserved.
      * No implementation in this module handles API keys: key
        handling lives in ``translation.py`` (see the module
        docstring). Implementations take no key parameter.
    """

    name: str

    def translate(self, segments: list[dict], product: Any, *,
                  mode: str = "NATURAL_LOCALIZATION",
                  style: str = "neutral",
                  visible_demonstration: str = "") -> Any:
        """Translate/localize segments; see the class contract."""
        ...


class TranslationGeminiClient:
    """Thin adapter over ``translation.translate_segments``.

    Delegates unchanged: model fallback order, retry policy, prompt,
    segment parsing, and the labelled fallback all stay in
    ``translation.py`` — including the ONLY key handling in the
    affiliate module (``translate_segments`` reads
    ``GEMINI_API_KEY`` from the environment, as it already did in
    Phase 1). This adapter adds no key parameter, no env-var read,
    and no new secret path. Wire this implementation as the registry
    default only after Mai stores the key through the connector flow
    and the connector doc wires the backend to use it.
    """

    name = "translation_adapter"

    def translate(self, segments: list[dict], product: Any, *,
                  mode: str = "NATURAL_LOCALIZATION",
                  style: str = "neutral",
                  visible_demonstration: str = "") -> Any:
        from .translation import translate_segments
        return translate_segments(
            segments, product, mode=mode, style=style,
            visible_demonstration=visible_demonstration)


class UnavailableGeminiClient:
    """Labelled-unavailable Gemini client (the current default).

    Used while no Gemini key exists in this environment. It makes NO
    API call and reads NO credentials: it returns a fallback
    ``TranslationRecord`` with the original segments preserved,
    ``needs_human_review=True``, and zero translated/rewritten
    segments — the same honesty contract as the fallback in
    ``translation.py``, without depending on key state. Mode/style
    vocabularies are imported from ``schema.py`` (never duplicated).
    """

    name = "labelled_unavailable"

    def translate(self, segments: list[dict], product: Any, *,
                  mode: str = "NATURAL_LOCALIZATION",
                  style: str = "neutral",
                  visible_demonstration: str = "") -> Any:
        from .schema import (
            TRANSLATION_MODES,
            TRANSLATION_STYLES,
            TranslationRecord,
        )
        if mode not in TRANSLATION_MODES:
            raise ValueError(f"unknown translation mode {mode!r}")
        if style not in TRANSLATION_STYLES:
            raise ValueError(f"unknown translation style {style!r}")
        originals = [{"start": float(s.get("start", 0.0)),
                      "end": float(s.get("end", 0.0)),
                      "text": str(s.get("text", "")),
                      "speaker_id": str(s.get("speaker_id", "SPEAKER_00"))}
                     for s in segments]
        return TranslationRecord(
            mode=mode, engine="fallback",
            engine_detail=("Gemini unavailable — labelled fallback "
                           "used (no key wired; not Gemini output)"),
            style=style, original_segments=originals,
            needs_human_review=True,
            review_notes=[
                "No Gemini key: segments were NOT translated. A human "
                "translator (or a Gemini run with a key) must supply "
                "the Vietnamese text — the fallback never invents "
                "translations."])


class FakeGeminiClient:
    """TEST-ONLY Gemini fake: canned translations or unavailable.

    With ``canned_texts`` supplied, ``translate`` returns those
    texts as the translated segments, labelled
    ``engine="fake_test_only"`` — the canned texts are explicit test
    data, never a claim of model output. Without them it behaves
    like :class:`UnavailableGeminiClient`. Calls are recorded.
    """

    name = "fake-test"

    def __init__(self, canned_texts: list[str] | None = None) -> None:
        self._canned = list(canned_texts) if canned_texts else None
        self.calls: list[dict[str, Any]] = []

    def translate(self, segments: list[dict], product: Any, *,
                  mode: str = "NATURAL_LOCALIZATION",
                  style: str = "neutral",
                  visible_demonstration: str = "") -> Any:
        from .schema import TranslationRecord
        self.calls.append({"mode": mode, "style": style,
                           "segment_count": len(segments)})
        originals = [{"start": float(s.get("start", 0.0)),
                      "end": float(s.get("end", 0.0)),
                      "text": str(s.get("text", "")),
                      "speaker_id": str(s.get("speaker_id", "SPEAKER_00"))}
                     for s in segments]
        if self._canned is None:
            return UnavailableGeminiClient().translate(
                segments, product, mode=mode, style=style,
                visible_demonstration=visible_demonstration)
        if len(self._canned) != len(originals):
            raise ValueError(
                f"fake canned {len(self._canned)} texts for "
                f"{len(originals)} segments")
        return TranslationRecord(
            mode=mode, engine="fake_test_only",
            engine_detail="test-only canned translations",
            style=style, original_segments=originals,
            translated_segments=[dict(seg, text=text)
                                 for seg, text in zip(originals,
                                                      self._canned)])


# ---------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------

class ProviderRegistry:
    """A tiny name -> factory registry, one namespace per seam.

    Factories are zero-argument callables returning a fresh provider
    instance. Each seam has exactly one default; ``get`` with no name
    returns the default. Unknown seams/names raise ``KeyError``
    listing what IS registered, so a typo fails loudly at wiring
    time instead of silently returning the wrong provider.
    """

    def __init__(self) -> None:
        self._factories: dict[str, dict[str, Callable[[], Any]]] = {}
        self._defaults: dict[str, str] = {}

    def register(self, seam: str, name: str,
                 factory: Callable[[], Any], *, default: bool = False) -> None:
        """Register ``factory`` under ``(seam, name)``.

        The first registration for a seam becomes its default unless
        another registration explicitly claims ``default=True``.
        """
        self._factories.setdefault(seam, {})[name] = factory
        if default or seam not in self._defaults:
            self._defaults[seam] = name

    def get(self, seam: str, name: str | None = None) -> Any:
        """Instantiate the named (or default) provider for a seam."""
        if seam not in self._factories:
            raise KeyError(
                f"unknown provider seam {seam!r}; registered seams: "
                f"{sorted(self._factories)}")
        names = self._factories[seam]
        chosen = name or self._defaults[seam]
        if chosen not in names:
            raise KeyError(
                f"unknown provider {chosen!r} for seam {seam!r}; "
                f"registered: {sorted(names)}")
        return names[chosen]()

    def list_providers(self) -> dict[str, list[str]]:
        """Seam -> sorted registered provider names."""
        return {seam: sorted(names)
                for seam, names in self._factories.items()}

    def default_name(self, seam: str) -> str:
        """The default provider name for a seam (KeyError if unknown)."""
        if seam not in self._defaults:
            raise KeyError(f"unknown provider seam {seam!r}")
        return self._defaults[seam]

    def describe(self) -> dict[str, dict[str, Any]]:
        """Seam -> {default, providers} for status/diagnostics pages."""
        return {seam: {"default": self._defaults[seam],
                       "providers": sorted(names)}
                for seam, names in self._factories.items()}


REGISTRY = ProviderRegistry()
REGISTRY.register("downloader", "yt-dlp", YtDlpDownloader, default=True)
# The fake downloader needs a fixture path, so its factory raises a
# clear error: tests construct FakeDownloader directly with a real
# fixture instead of resolving it through the registry.
REGISTRY.register(
    "downloader", "fake",
    lambda: (_ for _ in ()).throw(RuntimeError(
        "FakeDownloader needs a fixture_path; construct it directly "
        "in tests: FakeDownloader(fixture_path)")))
REGISTRY.register("ocr", "default", DelegatingOCREngine, default=True)
REGISTRY.register("ocr", "fake", FakeOCREngine)
REGISTRY.register("tts", "voice", VoiceTTSProvider, default=True)
REGISTRY.register("tts", "fake", FakeTTSProvider)
REGISTRY.register("gemini", "labelled_unavailable",
                  UnavailableGeminiClient, default=True)
REGISTRY.register("gemini", "translation_adapter",
                  TranslationGeminiClient)
REGISTRY.register("gemini", "fake", FakeGeminiClient)


def get_provider(seam: str, name: str | None = None) -> Any:
    """Resolve a provider from the module registry (see REGISTRY)."""
    return REGISTRY.get(seam, name)


def register_provider(seam: str, name: str,
                      factory: Callable[[], Any], *,
                      default: bool = False) -> None:
    """Register a provider factory (Stage 2 / new backends)."""
    REGISTRY.register(seam, name, factory, default=default)


def list_providers() -> dict[str, list[str]]:
    """Seam -> registered provider names (see REGISTRY)."""
    return REGISTRY.list_providers()


__all__ = [
    "DOWNLOAD_FAILURE_REASONS",
    "REASON_AUTH_REQUIRED",
    "REASON_COOKIES_REQUIRED",
    "REASON_DOWNLOAD_FAILED",
    "REASON_NETWORK_ERROR",
    "REASON_NOT_AVAILABLE",
    "REASON_NOT_FOUND",
    "REASON_UNSUPPORTED_URL",
    "REGISTRY",
    "DelegatingOCREngine",
    "DownloadFailure",
    "DownloadResult",
    "Downloader",
    "FakeDownloader",
    "FakeGeminiClient",
    "FakeOCREngine",
    "FakeTTSProvider",
    "FailingDownloader",
    "GeminiClient",
    "OCREngine",
    "ProviderRegistry",
    "TTSProvider",
    "TranslationGeminiClient",
    "UnavailableGeminiClient",
    "VoiceTTSProvider",
    "YtDlpDownloader",
    "as_ingest_downloader",
    "get_provider",
    "list_providers",
    "register_provider",
    "resolve_ytdlp_binary",
]
