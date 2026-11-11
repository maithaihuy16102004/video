"""AI Clip Studio — universal script-to-cinematic-animation pipeline.

Additive layer on top of the V5.1 Universal Cinematic Pipeline.
This package adds the missing orchestration pieces from Mai's Master
Prompt (production request / hash chain, preflight, dynamic timeline,
event-driven audio, Drive uploader, end-to-end pipeline) without
modifying any upstream file. See AUDIT.md for what already existed in
the V5.1 code and what this package adds.

Modules:
    production_request — immutable ProductionRequest + hash chain
    preflight          — PASS/FAIL validation before any render
    timeline           — dynamic duration from real TTS audio
    audio_events       — event-driven SFX / meme rules / stems
    drive_uploader     — Drive folder structure + verified uploads
    pipeline           — run_production() orchestrating the above
"""

from .production_request import ProductionRequest, HashChainError
from .timeline import build_timeline, measure_wav_duration
from .preflight import run_preflight, PreflightResult
from .audio_events import plan_audio_events, AudioEventPlan
from .drive_uploader import DriveUploader, DRIVE_ROOT_FOLDER_ID, PROJECT_FOLDERS
from .pipeline import run_production, ProductionStatus
from .orchestrator import UniversalProductionPipeline, STAGES
from . import upstream

__all__ = [
    "ProductionRequest", "HashChainError",
    "build_timeline", "measure_wav_duration",
    "run_preflight", "PreflightResult",
    "plan_audio_events", "AudioEventPlan",
    "DriveUploader", "DRIVE_ROOT_FOLDER_ID", "PROJECT_FOLDERS",
    "run_production", "ProductionStatus",
    "UniversalProductionPipeline", "STAGES", "upstream",
]
