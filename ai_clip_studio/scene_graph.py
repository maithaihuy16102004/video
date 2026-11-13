"""Canonical scene graph (directive section 5).

The graph EXTENDS the scene package -- it never replaces or
duplicates it. It is the compiled representation every downstream
module reads: stable ids for every entity, the semantic resolution
for every action, the compiled event each resolution produced, and
provenance on every node.

Construction: ``build_scene_graph`` indexes the package (scenes,
directive shots, characters, props), links compiled events to
their SemanticAction records (``action_id ==
source_directive_id``), and maps every semantic type to its
expected compiler verb through SEMANTIC_TO_COMPILER_VERB. Events
with no semantic record are supporting/derived actions (IDLE,
MARCH, expression holds); they are marked, never given an
invented resolution.

Validation: ``validate_scene_graph`` re-checks a built graph from
its own indexes alone, so a persisted scene_graph.json can be
re-validated without the package. Errors fail the job at the
early semantic pass and fail preflight; warnings (unsupported
entries, semantic-less supporting events, event-less shots) are
reported, never hidden.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum

from .action_compiler import (
    FORBIDDEN_SEMANTIC_COMPILATIONS, SEMANTIC_TO_COMPILER_VERB,
    resolve_semantic_actions)

SCENE_GRAPH_VERSION = 1


class GraphValidationError(Exception):
    """The scene graph failed structural validation."""


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _rec_get(record, field, default=None):
    if isinstance(record, dict):
        return record.get(field, default)
    return getattr(record, field, default)


def build_scene_graph(package, compiled_events, semantic_actions=None,
                      unsupported=None) -> dict:
    """Build the canonical graph for a package + compile outputs.

    ``semantic_actions`` defaults to resolving the package (the
    single resolution path); callers that already compiled pass
    their semantic sink to avoid resolving twice. The graph is
    JSON-serializable and carries its own validation result.
    """
    if semantic_actions is None:
        semantic_actions = resolve_semantic_actions(package)
    events = list(compiled_events or [])
    unsupported = list(unsupported or [])

    scenes: dict[str, dict] = {}
    scene_number_to_id: dict[int, str] = {}
    for scene in package.get("scenes") or []:
        number = scene.get("number")
        scene_id = scene.get("scene_id") or (
            f"SC{int(number):02d}" if number is not None else None)
        if scene_id is None:
            continue
        scenes[scene_id] = {
            "scene_id": scene_id,
            "number": number,
            "title": scene.get("title") or "",
            "shot_ids": [],
            "character_ids": sorted(
                str(c) for c in (scene.get("visible_characters") or [])),
            "prop_ids": sorted(
                str(p) for p in (scene.get("props") or [])),
        }
        if number is not None:
            scene_number_to_id[int(number)] = scene_id

    shots: dict[str, dict] = {}
    for directive in package.get("shot_directives") or []:
        shot_id = directive.get("shot_id")
        if not shot_id:
            continue
        shots[str(shot_id)] = {
            "shot_id": str(shot_id),
            "scene_number": directive.get("scene"),
            "shot_type": directive.get("shot_type") or "",
            "event_ids": [],
        }
    # Directive shots the package lists only inside v1_scene blocks.
    for scene in package.get("scenes") or []:
        v1_scene = scene.get("v1_scene") or {}
        for shot in v1_scene.get("shots") or []:
            shot_id = shot.get("id")
            if shot_id and str(shot_id) not in shots:
                shots[str(shot_id)] = {
                    "shot_id": str(shot_id),
                    "scene_number": scene.get("number"),
                    "shot_type": shot.get("type") or "",
                    "event_ids": [],
                }

    characters: dict[str, dict] = {}
    # Declared characters PLUS background-extras groups: extras
    # act in events (walk, march, carry) and must resolve as
    # actors, even though they are not in the visible cast.
    for char in list(package.get("characters") or []) + list(
            package.get("v1_extras") or []):
        char_id = char.get("id") or char.get("identity_id")
        if not char_id:
            continue
        characters[str(char_id)] = {
            "character_id": str(char_id),
            "name": char.get("name") or "",
            "is_extra": bool(char.get("is_extra", False)),
            "event_ids": [],
        }

    props: dict[str, dict] = {}
    for prop in package.get("props") or []:
        prop_id = prop.get("id")
        if not prop_id:
            continue
        props[str(prop_id)] = {
            "prop_id": str(prop_id),
            "kind": prop.get("kind") or "",
            "name": prop.get("name") or "",
            "event_ids": [],
        }

    semantic_index: dict[str, dict] = {}
    for action in semantic_actions:
        directive_id = _rec_get(action, "source_directive_id")
        if not directive_id:
            continue
        sem_type = _rec_get(action, "action_type")
        record = _jsonable(action)
        record["compiler_verb"] = SEMANTIC_TO_COMPILER_VERB.get(sem_type)
        record["event_id"] = None
        semantic_index[str(directive_id)] = record

    events_index: dict[str, dict] = {}
    for event in events:
        action_id = event.get("action_id")
        if not action_id:
            continue
        sem = semantic_index.get(str(action_id))
        node = {
            "action_id": str(action_id),
            "verb": event.get("action_type"),
            "actor_id": event.get("actor_id"),
            "target_id": event.get("target_id"),
            "prop_id": event.get("prop_id"),
            "shot_id": event.get("shot_id"),
            "scene_number": event.get("scene_number"),
            "start_time": event.get("start_time"),
            "end_time": event.get("end_time"),
            "semantic_action_id": (
                str(action_id) if sem is not None else None),
            "semantic_type": (
                _rec_get(sem, "action_type") if sem is not None
                else event.get("semantic_action_type")),
            "expected_verb": (
                _rec_get(sem, "compiler_verb") if sem is not None
                else None),
            "provenance": {
                "source_script_hash": event.get("source_script_hash"),
                "source_scene_id": event.get("source_scene_id"),
                "source_shot_id": event.get("source_shot_id"),
                "source_directive_id": event.get(
                    "source_directive_id"),
                "action_origin": _jsonable(event.get("action_origin")),
                "inference_reason": event.get("inference_reason"),
                "authorization_status": _jsonable(
                    event.get("authorization_status")),
            },
        }
        events_index[str(action_id)] = node
        if sem is not None:
            sem["event_id"] = str(action_id)

    # Back-references, in timeline order per entity.
    ordered = sorted(
        events_index.values(),
        key=lambda n: (n["start_time"] is None, n["start_time"] or 0.0))
    for node in ordered:
        action_id = node["action_id"]
        shot = shots.get(str(node["shot_id"])) if node["shot_id"] else None
        if shot is not None:
            shot["event_ids"].append(action_id)
            scene_id = scene_number_to_id.get(node["scene_number"])
            if scene_id and shot["shot_id"] not in scenes[scene_id][
                    "shot_ids"]:
                scenes[scene_id]["shot_ids"].append(shot["shot_id"])
        char = characters.get(str(node["actor_id"])) \
            if node["actor_id"] else None
        if char is not None:
            char["event_ids"].append(action_id)
        prop = props.get(str(node["prop_id"])) if node["prop_id"] else None
        if prop is not None:
            prop["event_ids"].append(action_id)

    graph = {
        "version": SCENE_GRAPH_VERSION,
        "snapshot_hash": package.get("v1_snapshot_hash")
        or package.get("snapshot_hash"),
        "scenes": scenes,
        "shots": shots,
        "characters": characters,
        "props": props,
        "events": events_index,
        "semantic_actions": semantic_index,
        "unsupported": [_jsonable(u) for u in unsupported],
        "validation": {"errors": [], "warnings": []},
    }
    errors, warnings = validate_scene_graph(
        graph, event_count=len(events),
        semantic_count=len(semantic_index))
    graph["validation"] = {"errors": errors, "warnings": warnings}
    return graph


def validate_scene_graph(graph: dict, *, event_count: int | None = None,
                         semantic_count: int | None = None
                         ) -> tuple[list[str], list[str]]:
    """Re-check a built graph from its own indexes.

    ``event_count`` / ``semantic_count`` (the builder's input
    sizes) let the validator catch ids the builder dropped;
    omitted when re-validating a loaded graph.
    """
    errors: list[str] = []
    warnings: list[str] = []
    scenes = graph.get("scenes") or {}
    shots = graph.get("shots") or {}
    characters = graph.get("characters") or {}
    props = graph.get("props") or {}
    events = graph.get("events") or {}
    semantics = graph.get("semantic_actions") or {}
    scene_numbers = {s.get("number") for s in scenes.values()}

    if event_count is not None and len(events) != event_count:
        errors.append(
            f"event index holds {len(events)} of {event_count} "
            "compiled events (duplicate or missing action_id)")
    if semantic_count is not None and len(semantics) != semantic_count:
        errors.append(
            f"semantic index holds {len(semantics)} of "
            f"{semantic_count} resolved actions (duplicate or "
            "missing source_directive_id)")

    for directive_id, sem in semantics.items():
        sem_type = sem.get("action_type")
        if sem.get("compiler_verb") is None:
            errors.append(
                f"semantic action {directive_id}: type {sem_type!r} "
                "has no SEMANTIC_TO_COMPILER_VERB entry")
        if sem.get("event_id") is None:
            errors.append(
                f"semantic action {directive_id} ({sem_type}) "
                "produced no compiled event")
        elif sem["event_id"] not in events:
            errors.append(
                f"semantic action {directive_id} links to missing "
                f"event {sem['event_id']!r}")

    for action_id, node in events.items():
        actor = node.get("actor_id")
        if actor and str(actor) not in characters:
            errors.append(
                f"event {action_id}: unknown actor {actor!r}")
        target = node.get("target_id")
        if target and str(target) not in characters \
                and str(target) not in props:
            errors.append(
                f"event {action_id}: unknown target {target!r}")
        prop_id = node.get("prop_id")
        if prop_id and str(prop_id) not in props:
            errors.append(
                f"event {action_id}: unknown prop {prop_id!r}")
        shot_id = node.get("shot_id")
        if shot_id and str(shot_id) not in shots:
            errors.append(
                f"event {action_id}: unknown shot {shot_id!r}")
        scene_number = node.get("scene_number")
        if scene_number is not None and scene_number not in scene_numbers:
            errors.append(
                f"event {action_id}: unknown scene {scene_number!r}")
        sem_type = node.get("semantic_type")
        verb = node.get("verb")
        if sem_type and verb:
            forbidden = FORBIDDEN_SEMANTIC_COMPILATIONS.get(
                sem_type, frozenset())
            if verb in forbidden:
                errors.append(
                    f"event {action_id}: forbidden compilation -- "
                    f"semantic type {sem_type} compiled to {verb}")
        if node.get("semantic_action_id") is None:
            warnings.append(
                f"event {action_id} ({verb}): supporting action, "
                "no semantic record")

    unsupported = graph.get("unsupported") or []
    if unsupported:
        warnings.append(
            f"{len(unsupported)} unsupported directive(s) recorded, "
            "no event produced")
    for shot_id, shot in shots.items():
        if not shot.get("event_ids"):
            warnings.append(
                f"shot {shot_id}: no compiled events (visual/lead "
                "shot or uncompiled directive)")
    return errors, warnings


def validate_or_raise(graph: dict) -> None:
    """Raise GraphValidationError listing every validation error."""
    errors = (graph.get("validation") or {}).get("errors") or []
    if errors:
        raise GraphValidationError(
            "scene graph validation failed: " + "; ".join(errors))
