"""Universal Character Master Bible & Art Direction Specifications.

Implements the PROJECT-WIDE Character Art Direction Contract:
- A CHARACTER IS NOT: STICK BODY + DIFFERENT HAIR COLOR.
- A CHARACTER IS:
  HEAD SILHOUETTE (width, height, forehead, jaw, chin, cheeks, ears)
  + HAIR SILHOUETTE (hairline, parting, top mass, side mass, back mass, direction, profile silhouette)
  + FACE ANCHORS (brows, eyes, nose, mouth, facial hair, jaw/chin)
  + COSTUME SILHOUETTE (headwear, shirt, jacket, coat, trousers, boots, belt, equipment, accessories)
  + BODY PROPORTIONS (head 25-32% of standing height, compact torso, thin expressive limbs)
  + POSTURE & PERFORMANCE (gesture line, center of mass, action target).
- Never hardcodes specific historical individuals into core code (100% universal).
"""
from __future__ import annotations

import math
from typing import Any, Optional
from pydantic import BaseModel, Field


class HeadSilhouetteDNA(BaseModel):
    """Geometric head shape defining the character silhouette from all angles."""
    width_ratio: float = 1.0          # Relative to standard 38px base radius
    height_ratio: float = 1.05        # Slightly taller than wide for adult male
    forehead_slope: float = 0.05      # -0.2 (sloping back) to +0.2 (prominent)
    jaw_width_ratio: float = 0.88     # Taper from temples to jaw
    chin_shape: str = "ANGULAR"       # ANGULAR, ROUND, SQUARE, POINTED, RECEDING
    cheek_prominence: float = 0.1     # Cheekbone protrusion
    ear_size: float = 0.85
    ear_angle_deg: float = 8.0
    jaw_drop: float = 0.0             # Additional jaw drop for speaking / shock


class HairSilhouetteDNA(BaseModel):
    """Graphic mass defining the hair silhouette — never a generic black patch."""
    style_category: str = "SLICKED_SIDE_PART" # SLICKED_SIDE_PART, CROPPED_MILITARY, UNKEMPT_BOHEMIAN, BALDING, DISHEVELED
    parting: str = "DEEP_LEFT"        # DEEP_LEFT, SLIGHT_LEFT, CENTER, RIGHT, NONE
    hairline_height: float = 0.72     # 0.0 (low forehead) to 1.0 (receding)
    top_volume: float = 0.65          # Upward mass over skull curve
    side_mass_l: float = 0.55         # Left temple/sideburn volume
    side_mass_r: float = 0.82         # Right sweep overhang volume
    back_nape_mass: float = 0.45      # Volume over back collar
    direction: str = "SWEEP_RIGHT"    # SWEEP_RIGHT, SWEEP_LEFT, FORWARD, BACKWARD
    strand_clumps: int = 5            # Secondary silhouette silhouette tufts
    bangs_length: float = 0.48        # Overhang across forehead/brow
    profile_silhouette: str = "ANGULAR_COMB" # Graphic shape in pure side profile
    color_hex: str = "#241a15"        # Natural dark brown/black ink
    sheen_level: float = 0.25         # Specular hairline accent


class FaceAnchorsDNA(BaseModel):
    """Minimal but strong facial anchor marks that preserve identity across scales."""
    eye_spacing_ratio: float = 0.95   # Slightly close-set or wide-set
    eye_shape: str = "PIERCING_SLIT"  # PIERCING_SLIT, ROUND_ALERT, HEAVY_LID, SQUINT
    brow_weight: float = 1.35         # Heavy defined brows vs thin
    brow_slant_rest: float = 0.12     # Inward slant even at rest (intense gaze)
    nose_profile: str = "STRAIGHT_AQUILINE" # STRAIGHT_AQUILINE, PROMINENT_BRIDGE, BUTTON, CONCAVE
    nose_bridge_length: float = 1.15
    nose_tip_drop: float = 0.18
    mouth_width_ratio: float = 0.92   # Tense narrow mouth vs broad
    mouth_rest_expression: str = "FIRM_DOWNWARD" # FIRM_DOWNWARD, NEUTRAL, SKEPTICAL, MILD
    jaw_contour_line: bool = True     # Inked jaw contour for adult males
    distinctive_marks: list[str] = Field(default_factory=list) # e.g. ["PALE_UNDEREYE_SHADOW", "HOLLOW_CHEEKS"]


class FacialHairDNA(BaseModel):
    """Generic facial hair architecture — never a single-person renderer."""
    style: str = "NONE"               # NONE, COMPACT_RECTANGULAR, WALRUS, FULL_BEARD, GOATEE, HANDLEBAR, STUBBLE
    width_mm: float = 0.0             # Physical proportion in stickman space (e.g. 14px)
    height_mm: float = 0.0            # Height (e.g. 8px)
    density: float = 0.0              # 0.0 to 1.0 opacity
    placement_y: float = 0.0          # Offset from nose base to lip
    color_hex: str = "#201814"


class CostumeComponentDNA(BaseModel):
    """Composable clothing component that alters the character's physical silhouette."""
    component_type: str               # HEADWEAR, COAT, JACKET, SHIRT, TROUSERS, BOOTS, BELT, HARNESS, BANDAGE
    name: str = ""
    silhouette_spread_x: float = 0.0  # Expands base silhouette (e.g. trench coat expands shoulders/torso +18px)
    silhouette_drop_y: float = 0.0    # Lower hem extension (e.g. greatcoat reaches knees)
    collar_height: float = 0.0        # Raised collar silhouette
    edge_profile: str = "STIFF_CLOTH" # STIFF_CLOTH, RAGGED, FOLDED, DRAPED
    primary_color: str = "#455060"
    secondary_color: str = "#2d333d"
    trim_color: str = "#181a1f"
    weathering_level: float = 0.3     # Wear, mud stains, wrinkles
    attachments: list[str] = Field(default_factory=list) # ["POUCH", "MEDAL", "CANTEEN", "DISPATCH_CASE"]


class BodyProportionsDNA(BaseModel):
    """Stickman anatomical proportions preserving the large-head aesthetic."""
    standing_height_px: float = 280.0
    head_to_body_ratio: float = 0.28  # 28% of total height (in 25-32% range)
    shoulder_width_ratio: float = 1.05
    torso_compactness: float = 0.85   # Compact torso
    limb_thickness_px: float = 7.5    # Thin expressive limbs
    hand_scale: float = 0.95
    foot_scale: float = 1.15          # Grounded military/work boots


class PosturePerformanceDNA(BaseModel):
    """Physical habits, center of mass tendencies, and gesture style."""
    spine_natural_curve: float = -0.08# Mild forward hunch / intense forward lean
    neck_forward_thrust: float = 0.12 # Head pushed forward toward listener/target
    hand_habit_rest: str = "POCKETS_OR_CLENCHED" # POCKETS_OR_CLENCHED, AT_SIDES, BEHIND_BACK
    speaking_gesture_intensity: float = 1.45 # High expressive hand sweep
    defensive_recoil_bias: float = 0.85 # Flinches or tenses up when challenged


class CharacterAppearanceState(BaseModel):
    """Snapshot of a character's visual identity at a specific time/context."""
    state_id: str                     # e.g. "1914_RECRUIT", "1916_TRENCH_RUNNER", "1918_PASAWALK", "1919_SPEAKER"
    era_year: int
    age: int
    context_label: str
    head: HeadSilhouetteDNA
    hair: HairSilhouetteDNA
    face: FaceAnchorsDNA
    facial_hair: FacialHairDNA
    costume_components: list[CostumeComponentDNA]
    body: BodyProportionsDNA
    posture: PosturePerformanceDNA
    injuries_conditions: list[str] = Field(default_factory=list) # ["EYE_BANDAGE", "TRENCH_MUD", "FATIGUE_EYES"]
    color_palette: dict[str, str] = Field(default_factory=dict)


class CharacterMasterBible(BaseModel):
    """Complete Single Source of Truth for a character across the entire narrative."""
    character_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    story_role: str = "PROTAGONIST"   # PROTAGONIST, ANTAGONIST, COMMANDER, COMPANION, DOCTOR, NARRATOR
    historical_person: bool = False
    birth_year: Optional[int] = None
    core_identity_anchors: list[str] = Field(default_factory=list)
    appearance_timeline: dict[str, CharacterAppearanceState] = Field(default_factory=dict)
    continuity_rules: list[str] = Field(default_factory=list)
    performance_tendencies: list[str] = Field(default_factory=list)
    historical_confidence: str = "HISTORICALLY_SUPPORTED" # SCRIPT_EXPLICIT, HISTORICALLY_SUPPORTED, PLAUSIBLE_RECONSTRUCTION

    def get_state(self, state_id_or_year: str | int) -> CharacterAppearanceState:
        """Returns the appropriate appearance state for a year or state identifier."""
        if str(state_id_or_year) in self.appearance_timeline:
            return self.appearance_timeline[str(state_id_or_year)]
        # Match by nearest year
        if isinstance(state_id_or_year, int):
            states = sorted(self.appearance_timeline.values(), key=lambda s: abs(s.era_year - state_id_or_year))
            if states:
                return states[0]
        # Fallback to first available state
        if self.appearance_timeline:
            return next(iter(self.appearance_timeline.values()))
        raise ValueError(f"No appearance state found for character {self.character_id}")
