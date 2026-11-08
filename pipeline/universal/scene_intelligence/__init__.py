"""Universal Scene Intelligence V3 Package.

Core exports for Scene Architecture, Physical Geography, Staging,
Event Graphs, Production Design, and Blueprint Integration.
"""
from __future__ import annotations

from .adapter import SceneIntelligenceAdapter
from .architect import (
    DeterministicSceneArchitect,
    GeminiSceneArchitect,
    GeminiSceneCallLedger,
    SceneArchitectProvider,
)
from .events import SceneEventGraphBuilder
from .geography import SceneGeographyManager
from .schemas import (
    ActorStagingV3,
    Affordance,
    CameraOpportunityZone,
    EventEffect,
    InformationItem,
    InteractionAnchor,
    PowerRelationship,
    ProductionDesignPlan,
    ProductionProp,
    PropReason,
    ProxemicDistance,
    ProxemicRelationship,
    SceneDesignV3,
    SceneEndState,
    SceneEvent,
    SceneEventGraph,
    SceneGeographyV3,
    SceneIdentity,
    SceneOutcome,
    SceneOutcomeType,
    ScenePurpose,
    SceneStartState,
    SceneStagingPlan,
    UModel,
    WorldObject,
)
from .staging import SceneStagingPlanner
from .validation import (
    SceneGeographyValidator,
    SceneSurvivalAuditor,
    TemplateLeakageValidator,
)

__all__ = [
    "ScenePurpose",
    "SceneOutcomeType",
    "SceneOutcome",
    "SceneIdentity",
    "PropReason",
    "Affordance",
    "InteractionAnchor",
    "ProductionProp",
    "ProductionDesignPlan",
    "WorldObject",
    "CameraOpportunityZone",
    "SceneGeographyV3",
    "ProxemicDistance",
    "ProxemicRelationship",
    "PowerRelationship",
    "ActorStagingV3",
    "SceneStagingPlan",
    "EventEffect",
    "SceneEvent",
    "InformationItem",
    "SceneEventGraph",
    "SceneStartState",
    "SceneEndState",
    "SceneDesignV3",
    "SceneGeographyManager",
    "SceneStagingPlanner",
    "SceneEventGraphBuilder",
    "SceneArchitectProvider",
    "DeterministicSceneArchitect",
    "GeminiSceneArchitect",
    "GeminiSceneCallLedger",
    "SceneIntelligenceAdapter",
    "SceneGeographyValidator",
    "TemplateLeakageValidator",
    "SceneSurvivalAuditor",
]
