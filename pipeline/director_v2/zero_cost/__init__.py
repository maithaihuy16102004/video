"""Zero-Cost Cinematic Visual Engine for Director V2.

Guarantees 100% functional cinematic rendering at $0.00 cost:
- High-fidelity parametric procedural environment primitives.
- True perspective convergence (1-point, 2-point, deep corridor, ground level, high angle).
- Multi-plane scene layering (Far BG, BG, MG, Actor, FG occluders, Atmospheric FX).
- 2D cinematic lighting (directional gradients, cast contact shadows, rim highlights).
- Complete 20+ Stickman pose library with interaction anchors and lighting response.
- Provider-neutral routing with circuit breaker and strictly enforced $0.00 cost ledger.
"""
from __future__ import annotations

from .primitives import *
from .location_kits import *
from .lighting_engine import CinematicLightingEngine
from .multi_plane_renderer import CinematicEnvironmentRenderer
from .actor_rig import StickmanActorRig
from .provider_router import VisualProviderRouter, QualityMode
from .cost_ledger import ZeroCostBudgetLedger
