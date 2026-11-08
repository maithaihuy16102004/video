"""Five Adversarial Benchmark Stories for Universal Visual Director Quality Test.

Ensures zero story overfitting and tests the system across drastically different genres,
enclosures, scales, character dynamics, and actions:
1. Editorial Dispute (Tiny room, heated dialogue, close blocking, table/chair, papers)
2. The Solitary Traverse (Exterior, vast mountain ridge, solitary figure, wide panoramic depth)
3. The Overheated Dynamo (Interior workshop, complex machinery, crouching/reaching, tool engagement)
4. The Council Assembly (Interior chamber, multi-character crowd, speech gesture, podium/benches)
5. The Vigil (Quiet intimate bedside, subtle micro-acting, sitting/leaning, bedpost foreground)
"""
from __future__ import annotations

from .schemas import (
    BeatAction,
    CharacterBible,
    CharacterDNA,
    CharacterMention,
    CostumeVariant,
    LocationBible,
    LocationDNA,
    LocationMention,
    PropSpec,
    StoryBeat,
    StoryIntelligence,
)


def get_adversarial_stories() -> list[tuple[str, StoryIntelligence, CharacterBible, LocationBible]]:
    """Returns the 5 adversarial benchmark test suites."""
    return [
        _build_story_1_editorial_dispute(),
        _build_story_2_solitary_traverse(),
        _build_story_3_overheated_dynamo(),
        _build_story_4_council_assembly(),
        _build_story_5_the_vigil(),
    ]


def _build_story_1_editorial_dispute() -> tuple[str, StoryIntelligence, CharacterBible, LocationBible]:
    chars = [
        CharacterMention(character_id="EDITOR_LEAD", name="Marcus", role="LEAD"),
        CharacterMention(character_id="JOURNALIST", name="Elena", role="SUPPORTING"),
    ]
    beats = [
        StoryBeat(
            beat_id="b1_edit",
            index=0,
            text="Marcus leans aggressively over the cramped desk, tapping the draft dispatch report.",
            location_id="LOC_EDIT_ROOM",
            characters=["EDITOR_LEAD", "JOURNALIST"],
            actions=[BeatAction(actor_id="EDITOR_LEAD", verb="LEAN", emotion="ANGRY", target="draft report")],
            suggested_purpose="CONFLICT",
            objects=["draft report"],
        ),
        StoryBeat(
            beat_id="b2_edit",
            index=1,
            text="Elena steps aside and argues back, refusing to redact the confidential source.",
            location_id="LOC_EDIT_ROOM",
            characters=["EDITOR_LEAD", "JOURNALIST"],
            actions=[BeatAction(actor_id="JOURNALIST", verb="ARGUE", emotion="DEFIANT", target="EDITOR_LEAD")],
            suggested_purpose="ACTION",
        ),
        StoryBeat(
            beat_id="b3_edit",
            index=2,
            text="Marcus pauses in the amber lamplight and reads the unredacted signature line.",
            location_id="LOC_EDIT_ROOM",
            characters=["EDITOR_LEAD", "JOURNALIST"],
            actions=[BeatAction(actor_id="EDITOR_LEAD", verb="READ", emotion="SOMBER", target="draft report")],
            suggested_purpose="REVEAL",
            objects=["draft report"],
        ),
    ]
    story = StoryIntelligence(
        title="The Editorial Dispute",
        characters=chars,
        locations=[LocationMention(location_id="LOC_EDIT_ROOM", name="Editorial Office", enclosure="INTERIOR")],
        story_beats=beats,
    )
    cb = CharacterBible(characters=[
        CharacterDNA(character_id="EDITOR_LEAD", name="Marcus", role="LEAD", visual_identity="Senior Editor in waistcoat"),
        CharacterDNA(character_id="JOURNALIST", name="Elena", role="SUPPORTING", visual_identity="Field reporter in trench jacket"),
    ])
    loc = LocationDNA(
        location_id="LOC_EDIT_ROOM",
        name="Editorial Office",
        enclosure="INTERIOR",
        lighting_behavior="WARM_INTERIOR_LAMP",
        architecture="Victorian oak-paneled office",
        materials=["WOOD", "PAPER", "GLASS", "BRASS"],
        props=[
            PropSpec(semantic="cluttered oak desk", category="FURNITURE", role="HERO", materials=["WOOD"]),
            PropSpec(semantic="brass reading lamp", category="LIGHTING", role="PRACTICAL", materials=["BRASS", "GLASS"]),
            PropSpec(semantic="draft report", category="DOCUMENT", role="HERO", materials=["PAPER"]),
        ],
    )
    return "01_editorial_dispute", story, cb, LocationBible(locations=[loc])


def _build_story_2_solitary_traverse() -> tuple[str, StoryIntelligence, CharacterBible, LocationBible]:
    chars = [
        CharacterMention(character_id="TRAVELER", name="Rowan", role="LEAD"),
    ]
    beats = [
        StoryBeat(
            beat_id="b1_trav",
            index=0,
            text="Rowan braces against freezing winds upon the jagged ridge crest overlooking the abyss.",
            location_id="LOC_MOUNTAIN_RIDGE",
            characters=["TRAVELER"],
            actions=[BeatAction(actor_id="TRAVELER", verb="BRACE", emotion="DETERMINED")],
            suggested_purpose="LOCATION",
        ),
        StoryBeat(
            beat_id="b2_trav",
            index=1,
            text="Rowan inspects the pocket navigational compass as blizzard gusts swirl around.",
            location_id="LOC_MOUNTAIN_RIDGE",
            characters=["TRAVELER"],
            actions=[BeatAction(actor_id="TRAVELER", verb="INSPECT", emotion="FOCUSED", target="compass")],
            suggested_purpose="OBJECT_INFORMATION",
            objects=["brass compass"],
        ),
        StoryBeat(
            beat_id="b3_trav",
            index=2,
            text="Rowan descends down the narrow rock ledge towards the sheltered alpine pass.",
            location_id="LOC_MOUNTAIN_RIDGE",
            characters=["TRAVELER"],
            actions=[BeatAction(actor_id="TRAVELER", verb="WALK", emotion="RESOLVED")],
            suggested_purpose="PAYOFF",
        ),
    ]
    story = StoryIntelligence(
        title="The Solitary Traverse",
        characters=chars,
        locations=[LocationMention(location_id="LOC_MOUNTAIN_RIDGE", name="Windswept Ridge", enclosure="EXTERIOR")],
        story_beats=beats,
    )
    cb = CharacterBible(characters=[
        CharacterDNA(character_id="TRAVELER", name="Rowan", role="LEAD", visual_identity="Mountain surveyor in heavy wool hooded parka"),
    ])
    loc = LocationDNA(
        location_id="LOC_MOUNTAIN_RIDGE",
        name="Windswept Ridge",
        enclosure="EXTERIOR",
        lighting_behavior="COLD_OVERCAST",
        architecture="Alpine crag and rocky outcrops",
        materials=["STONE", "ICE", "DIRT"],
        props=[
            PropSpec(semantic="surveyor trail marker", category="WAYMARK", role="SUPPORT", materials=["STONE", "WOOD"]),
            PropSpec(semantic="brass compass", category="APPARATUS", role="HERO", materials=["BRASS", "GLASS"]),
        ],
    )
    return "02_solitary_traverse", story, cb, LocationBible(locations=[loc])


def _build_story_3_overheated_dynamo() -> tuple[str, StoryIntelligence, CharacterBible, LocationBible]:
    chars = [
        CharacterMention(character_id="MECHANIC", name="Tara", role="LEAD"),
        CharacterMention(character_id="APPRENTICE", name="Leo", role="SUPPORTING"),
    ]
    beats = [
        StoryBeat(
            beat_id="b1_dyn",
            index=0,
            text="Steam jets suddenly burst from the high-pressure manifold, forcing Leo to flinch.",
            location_id="LOC_WORKSHOP",
            characters=["MECHANIC", "APPRENTICE"],
            actions=[BeatAction(actor_id="APPRENTICE", verb="FLINCH", emotion="ALARMED")],
            suggested_purpose="CAUSE",
            objects=["pressure manifold"],
        ),
        StoryBeat(
            beat_id="b2_dyn",
            index=1,
            text="Tara crouches beneath the shaking boiler and grabs the emergency valve lever.",
            location_id="LOC_WORKSHOP",
            characters=["MECHANIC", "APPRENTICE"],
            actions=[BeatAction(actor_id="MECHANIC", verb="CROUCH", emotion="INTENSE", target="valve lever")],
            suggested_purpose="ACTION",
            objects=["valve lever"],
        ),
        StoryBeat(
            beat_id="b3_dyn",
            index=2,
            text="Tara heaves with full weight, wrenching the bronze valve shut as the pressure drops.",
            location_id="LOC_WORKSHOP",
            characters=["MECHANIC", "APPRENTICE"],
            actions=[BeatAction(actor_id="MECHANIC", verb="PULL", emotion="TRIUMPHANT", target="valve lever")],
            suggested_purpose="REVEAL",
            objects=["valve lever"],
        ),
    ]
    story = StoryIntelligence(
        title="The Overheated Dynamo",
        characters=chars,
        locations=[LocationMention(location_id="LOC_WORKSHOP", name="Steam Dynamo Hall", enclosure="INTERIOR")],
        story_beats=beats,
    )
    cb = CharacterBible(characters=[
        CharacterDNA(character_id="MECHANIC", name="Tara", role="LEAD", visual_identity="Industrial mechanic with leather tool belt"),
        CharacterDNA(character_id="APPRENTICE", name="Leo", role="SUPPORTING", visual_identity="Young apprentice technician in denim dungarees"),
    ])
    loc = LocationDNA(
        location_id="LOC_WORKSHOP",
        name="Steam Dynamo Hall",
        enclosure="INTERIOR",
        lighting_behavior="INDUSTRIAL_LOW_KEY",
        architecture="Brick vaulted boiler workshop with exposed copper conduits",
        materials=["METAL", "BRICK", "BRONZE", "GLASS"],
        props=[
            PropSpec(semantic="heavy dynamo boiler", category="MACHINE", role="HERO", materials=["IRON", "BRONZE"]),
            PropSpec(semantic="heavy iron workbench", category="FURNITURE", role="SUPPORT", materials=["WOOD", "METAL"]),
            PropSpec(semantic="bronze valve lever", category="APPARATUS", role="HERO", materials=["BRONZE"]),
        ],
    )
    return "03_overheated_dynamo", story, cb, LocationBible(locations=[loc])


def _build_story_4_council_assembly() -> tuple[str, StoryIntelligence, CharacterBible, LocationBible]:
    chars = [
        CharacterMention(character_id="SPEAKER", name="Vance", role="LEAD"),
        CharacterMention(character_id="DELEGATE", name="Koren", role="SUPPORTING"),
    ]
    beats = [
        StoryBeat(
            beat_id="b1_counc",
            index=0,
            text="Vance stands at the elevated podium, addressing the murmuring council chamber.",
            location_id="LOC_COUNCIL_HALL",
            characters=["SPEAKER", "DELEGATE"],
            actions=[BeatAction(actor_id="SPEAKER", verb="SPEAK", emotion="AUTHORITATIVE")],
            suggested_purpose="LOCATION",
        ),
        StoryBeat(
            beat_id="b2_counc",
            index=1,
            text="Koren rises abruptly from the tiered benches and shouts in protest.",
            location_id="LOC_COUNCIL_HALL",
            characters=["SPEAKER", "DELEGATE"],
            actions=[BeatAction(actor_id="DELEGATE", verb="RISE", emotion="OUTRAGED", target="SPEAKER")],
            suggested_purpose="CONFLICT",
        ),
        StoryBeat(
            beat_id="b3_counc",
            index=2,
            text="Vance turns firmly to confront the dissenter, lifting the stamped parchment high.",
            location_id="LOC_COUNCIL_HALL",
            characters=["SPEAKER", "DELEGATE"],
            actions=[BeatAction(actor_id="SPEAKER", verb="TURN_BODY", emotion="RESOLUTE", target="DELEGATE")],
            suggested_purpose="REVEAL",
            objects=["stamped parchment"],
        ),
    ]
    story = StoryIntelligence(
        title="The Council Assembly",
        characters=chars,
        locations=[LocationMention(location_id="LOC_COUNCIL_HALL", name="Council Hall", enclosure="INTERIOR")],
        story_beats=beats,
    )
    cb = CharacterBible(characters=[
        CharacterDNA(character_id="SPEAKER", name="Vance", role="LEAD", visual_identity="Council magistrate in ceremonial long coat"),
        CharacterDNA(character_id="DELEGATE", name="Koren", role="SUPPORTING", visual_identity="Opposition delegate in civilian formal suit"),
    ])
    loc = LocationDNA(
        location_id="LOC_COUNCIL_HALL",
        name="Council Hall",
        enclosure="INTERIOR",
        lighting_behavior="CATHEDRAL_DIFFUSE",
        architecture="Grand stone assembly hall with arched windows and oak rostrum",
        materials=["STONE", "WOOD", "BRASS"],
        props=[
            PropSpec(semantic="carved rostrum podium", category="FURNITURE", role="HERO", materials=["WOOD"]),
            PropSpec(semantic="tiered council bench", category="FURNITURE", role="SUPPORT", materials=["WOOD"]),
            PropSpec(semantic="stamped parchment", category="DOCUMENT", role="HERO", materials=["PAPER"]),
        ],
    )
    return "04_council_assembly", story, cb, LocationBible(locations=[loc])


def _build_story_5_the_vigil() -> tuple[str, StoryIntelligence, CharacterBible, LocationBible]:
    chars = [
        CharacterMention(character_id="CAREGIVER", name="Nora", role="LEAD"),
        CharacterMention(character_id="PATIENT", name="Julian", role="SUPPORTING"),
    ]
    beats = [
        StoryBeat(
            beat_id="b1_vig",
            index=0,
            text="Nora sits in stillness by the bedside, bathed in the soft glow of a table lantern.",
            location_id="LOC_SICKROOM",
            characters=["CAREGIVER", "PATIENT"],
            actions=[BeatAction(actor_id="CAREGIVER", verb="SIT", emotion="SOMBER")],
            suggested_purpose="LOCATION",
        ),
        StoryBeat(
            beat_id="b2_vig",
            index=1,
            text="Nora reaches forward gently to take Julian's hand in quiet comfort.",
            location_id="LOC_SICKROOM",
            characters=["CAREGIVER", "PATIENT"],
            actions=[BeatAction(actor_id="CAREGIVER", verb="REACH", emotion="TENDER", target="PATIENT")],
            suggested_purpose="EMOTION",
        ),
        StoryBeat(
            beat_id="b3_vig",
            index=2,
            text="Julian whispers weakly with a faint smile, breaking the long silence.",
            location_id="LOC_SICKROOM",
            characters=["CAREGIVER", "PATIENT"],
            actions=[BeatAction(actor_id="PATIENT", verb="WHISPER", emotion="RELIEVED", target="CAREGIVER")],
            suggested_purpose="PAYOFF",
        ),
    ]
    story = StoryIntelligence(
        title="The Vigil",
        characters=chars,
        locations=[LocationMention(location_id="LOC_SICKROOM", name="Intimate Sickroom", enclosure="INTERIOR")],
        story_beats=beats,
    )
    cb = CharacterBible(characters=[
        CharacterDNA(character_id="CAREGIVER", name="Nora", role="LEAD", visual_identity="Devoted caregiver in simple linen dress and shawl"),
        CharacterDNA(character_id="PATIENT", name="Julian", role="SUPPORTING", visual_identity="Bedridden patient resting under woolen blanket"),
    ])
    loc = LocationDNA(
        location_id="LOC_SICKROOM",
        name="Intimate Sickroom",
        enclosure="INTERIOR",
        lighting_behavior="INTIMATE_CANDLELIGHT",
        architecture="Cozy domestic chamber with plaster walls and timber beams",
        materials=["WOOD", "FABRIC", "BRASS", "GLASS"],
        props=[
            PropSpec(semantic="timber bedside stool", category="FURNITURE", role="SUPPORT", materials=["WOOD"]),
            PropSpec(semantic="brass oil lantern", category="LIGHTING", role="HERO", materials=["BRASS", "GLASS"]),
            PropSpec(semantic="wooden clinic bed", category="FURNITURE", role="HERO", materials=["WOOD", "FABRIC"]),
        ],
    )
    return "05_the_vigil", story, cb, LocationBible(locations=[loc])
