"""Director V2 — script-to-shot autonomous director.

Pipeline (enforced by ``orchestrator``):

    SCRIPT -> ANALYZE -> HISTORICAL/CONTINUITY -> BIBLES -> RETENTION -> SCENE
    -> SHOT PLAN -> CAMERA VALIDATION -> REPETITION/STAGE-VIEW VALIDATION
    -> ASSET REUSE CHECK -> IMAGE GENERATION (only missing assets) -> VISUAL CRITIC
    -> RENDER MANIFEST

Image models are art/environment providers only; they never decide cinematography.
"""

__version__ = "2.0.0-phase1"
