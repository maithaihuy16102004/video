from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass
class HandContactAnchor:
    hand: str
    target_id: str
    target_anchor: str
    point: list[float]
    contact_type: str = "TOUCH"

@dataclass
class ActorBlockingPlan:
    actor_id: str
    role: str
    screen_position: list[float]
    depth_plane: str
    body_orientation: str
    facing_target: str
    eyeline_target: str
    head_direction: str
    weight_distribution: str
    movement_intent: str
    interaction_target: str
    action: str
    emotional_state: str
    acting_intensity: str = "NORMAL"
    line_of_action: str = "VERTICAL"
    silhouette_priority: str = "MEDIUM"
    hand_contacts: list[HandContactAnchor] = field(default_factory=list)
    foot_anchors: list[list[float]] = field(default_factory=list)
    occlusion_order: list[str] = field(default_factory=list)

@dataclass
class PerformancePlan:
    scene_id: str
    vitality_lock: str
    seed: int
    actors: list[ActorBlockingPlan]
    action_chain: list[str]
    visual_priority: list[str]

    def to_dict(self) -> dict[str, Any]: return asdict(self)

class InteractionSolver:
    """Small deterministic semantic constraint solver; intentionally not general IK."""
    def solve(self, actor: ActorBlockingPlan, asset_anchors: dict[str, list[float]]) -> dict[str, Any]:
        contacts=[]
        for c in actor.hand_contacts:
            key=f"{c.target_id}.{c.target_anchor}"
            point=asset_anchors.get(key,c.point)
            contacts.append({"hand":c.hand,"target":key,"point":point,"type":c.contact_type})
        return {
            "actor_id":actor.actor_id,
            "root":actor.screen_position,
            "orientation":actor.body_orientation,
            "line_of_action":actor.line_of_action,
            "weight":actor.weight_distribution,
            "contacts":contacts,
            "feet":actor.foot_anchors,
            "object_state_change":self._state_change(actor.action,actor.interaction_target),
            "occlusion_order":actor.occlusion_order,
        }

    @staticmethod
    def _state_change(action: str, target: str) -> dict[str,str] | None:
        changes={"ADJUST_BLANKET":"PULLED_TOWARD_PATIENT","CARRY_BASIN":"ATTACHED_TO_HANDS","REACT_TOWARD":"HEAD_TURNED","GESTURE_SUBTLE":"UNCHANGED"}
        return {"target":target,"state":changes[action]} if action in changes else None
