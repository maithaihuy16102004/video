"""Structured production failures (integration sprint section 6).

A compiler error must never be swallowed into a silent fallback: a
mandatory failure fails the stage (and the job) with a structured
record naming the error code, the stage, the source directive, the
affected entity, the severity, the recoverability, a diagnostic and
a suggested resolution. The frontend and the job status report the
same record -- there is no second, softer account of the failure.

Error taxonomy (sprint section 6 table):

- Mandatory action unsupported (a classified action whose actor
  cannot be resolved) -> ACTOR_RESOLUTION_FAILED, fatal.
- Mandatory prop unsupported (no renderable geometry/kind) ->
  MANDATORY_PROP_UNSUPPORTED, fatal. (Enforced at preflight by the
  prop_kinds check; the renderer raises UnsupportedPropError
  rather than drawing a generic placeholder.)
- Actor resolution failed -> ACTOR_RESOLUTION_FAILED, fatal.
- Timeline conflict -> TIMELINE_CONFLICT: rebuild explicitly or
  stop. (The unified timeline raises SchedulingConflict; the
  pipeline stops -- no silent rebuild exists.)
- Optional decorative action unsupported -> warning, recorded in
  the unsupported classification, never silent.
- Historical dataset unavailable -> HISTORICAL_DATASET_UNAVAILABLE:
  the dependent scene's render raises MissingHistoricalMapData
  and the job fails (an episode must be complete; scene-level
  skipping would ship a hole).
- Renderer unavailable -> RENDERER_UNAVAILABLE: reported as a
  blocker, never faked as success. (The code renderer is always
  available; Motion Canvas availability is recorded separately
  and never claimed as the rendering engine.)

Vocabulary gaps -- action sentences with no verb mapping at all
(UNCLEAR) -- are NOT exceptions: the compiler returns them in the
``unsupported`` list, and classify_unsupported() sorts them into
routed / expression / constraint / vocabulary-gap classes with an
explicit handling each. They warn and are listed shot-by-shot in
the coverage report; failing the whole production on every
vocabulary gap would block both episodes on ~30 sentences and
force the vocabulary expansion Mai explicitly deferred ("finish
what's built, render two episodes, then decide"). The strict
mandatory-stop reading for vocabulary gaps is a pending decision
for Mai, recorded in the integration report -- this module makes
the gap list exact so she can decide on evidence.

This module maps exception types BY NAME (no imports of the
raising modules) so it can be imported anywhere without cycles.
"""

from __future__ import annotations

# --- Error codes ---------------------------------------------------------

COMPILER_EXCEPTION = "COMPILER_EXCEPTION"
ACTOR_RESOLUTION_FAILED = "ACTOR_RESOLUTION_FAILED"
MANDATORY_PROP_UNSUPPORTED = "MANDATORY_PROP_UNSUPPORTED"
TIMELINE_CONFLICT = "TIMELINE_CONFLICT"
HISTORICAL_DATASET_UNAVAILABLE = "HISTORICAL_DATASET_UNAVAILABLE"
RENDERER_UNAVAILABLE = "RENDERER_UNAVAILABLE"
GRAPH_VALIDATION_FAILED = "GRAPH_VALIDATION_FAILED"
PROP_STATE_CONTRADICTION = "PROP_STATE_CONTRADICTION"
STORY_CONFLICT = "STORY_CONFLICT"
MAP_SPEC_ERROR = "MAP_SPEC_ERROR"
STAGE_EXCEPTION = "STAGE_EXCEPTION"

# Exception class name -> (error_code, recoverability, suggestion).
# Name-based on purpose: importing every raising module here would
# create import cycles (this module is imported by product_flow and
# preflight, which those modules' callers already import).
_EXCEPTION_MAP = {
    "UnauthorizedStoryChange": (
        STORY_CONFLICT, "fix_script",
        "Resolve the semantic conflict: remove or correct the "
        "inferred cue / directive that contradicts the script."),
    "GraphValidationError": (
        GRAPH_VALIDATION_FAILED, "fix_script",
        "Fix the broken reference or forbidden compilation named "
        "in the diagnostic; re-run preflight."),
    "ForbiddenPropTransition": (
        PROP_STATE_CONTRADICTION, "fix_script",
        "Fix the prop timeline: a prop cannot change state without "
        "the intervening action the transition table requires."),
    "MissingHistoricalMapData": (
        HISTORICAL_DATASET_UNAVAILABLE, "fix_code",
        "Ingest a verified historical dataset for the required "
        "period, or remove the map scene from the script."),
    "MapSpecError": (
        MAP_SPEC_ERROR, "fix_script",
        "Fix the map shot specification (year, framing, dataset "
        "reference) named in the diagnostic."),
    "UnsupportedPropError": (
        MANDATORY_PROP_UNSUPPORTED, "fix_code",
        "Add a semantic geometry builder for the prop kind, or "
        "change the script to a supported prop."),
    "SchedulingConflict": (
        TIMELINE_CONFLICT, "rebuild",
        "Rebuild the unified timeline explicitly from the "
        "conflicting schedule; never edit the frozen schedule."),
    "RegistryError": (
        HISTORICAL_DATASET_UNAVAILABLE, "fix_code",
        "Repair the historical dataset registry entry named in "
        "the diagnostic (checksum, file, or verification)."),
}


class ProductionError(Exception):
    """A structured, reportable production failure.

    All ten sprint-section-6 fields are required except the source
    ids, which stay None when the failure has no single source
    directive (never an invented id).
    """

    def __init__(self, error_code, *, stage, diagnostic_message,
                 affected_entity=None, severity="fatal",
                 recoverability="none", suggested_resolution="",
                 source_scene_id=None, source_shot_id=None,
                 source_directive_id=None, cause_type=None):
        super().__init__(f"[{error_code}] {stage}: {diagnostic_message}")
        self.error_code = error_code
        self.stage = stage
        self.source_scene_id = source_scene_id
        self.source_shot_id = source_shot_id
        self.source_directive_id = source_directive_id
        self.affected_entity = affected_entity
        self.severity = severity
        self.recoverability = recoverability
        self.diagnostic_message = diagnostic_message
        self.suggested_resolution = suggested_resolution
        self.cause_type = cause_type

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "stage": self.stage,
            "source_scene_id": self.source_scene_id,
            "source_shot_id": self.source_shot_id,
            "source_directive_id": self.source_directive_id,
            "affected_entity": self.affected_entity,
            "severity": self.severity,
            "recoverability": self.recoverability,
            "diagnostic_message": self.diagnostic_message,
            "suggested_resolution": self.suggested_resolution,
            "cause_type": self.cause_type,
        }


def wrap_exception(exc: BaseException, *, stage,
                   error_code: str | None = None) -> ProductionError:
    """Translate any exception into a ProductionError.

    The original type and message are preserved (cause_type +
    diagnostic_message) so the structured record never loses the
    underlying failure. An explicit error_code overrides the
    type mapping (used by the compile stages for compiler
    exceptions, which are COMPILER_EXCEPTION whatever their
    Python type).
    """
    cause_type = type(exc).__name__
    mapped = _EXCEPTION_MAP.get(cause_type)
    if error_code is None:
        error_code = mapped[0] if mapped else STAGE_EXCEPTION
    recoverability = mapped[1] if mapped else "none"
    suggestion = mapped[2] if mapped else (
        "Inspect the diagnostic and fix the failing stage; "
        "re-running without a fix will fail the same way.")
    return ProductionError(
        error_code, stage=stage,
        diagnostic_message=f"{cause_type}: {exc}",
        severity="fatal", recoverability=recoverability,
        suggested_resolution=suggestion, cause_type=cause_type)


# --- Unsupported-sentence classification ---------------------------------

# Categories the compiler routes to an owning stage (not errors).
_ROUTED_CATEGORIES = frozenset({
    "MAP", "ENVIRONMENT", "CAMERA", "AUDIO", "COSTUME_STATE",
    "DIALOGUE",
})

# Constraint / staging-note markers: negative directives ("Không
# mô tả..."), edit directives and composition notes. These are
# satisfied by non-staging or by the planner/camera, never by an
# action primitive.
_CONSTRAINT_MARKERS = (
    "match cut", "chuyển cảnh", "cắt cảnh", "cắt sang",
    "phía sau là", "ở phía sau",
)


def _expression_phrases() -> set[str]:
    """Expression-vocabulary phrases (the expression system's own
    keywords -- imported lazily so this module stays cycle-free)."""
    phrases: set[str] = set()
    try:
        from .expression_library import SUPPLEMENTARY_KEYWORDS
        from .trait_derivation import _EXPRESSION_KEYWORDS
        for _label, keywords in SUPPLEMENTARY_KEYWORDS:
            phrases.update(k.lower() for k in keywords)
        for _name, keywords in _EXPRESSION_KEYWORDS:
            if isinstance(keywords, (list, tuple)):
                phrases.update(k.lower() for k in keywords)
            else:
                phrases.add(str(keywords).lower())
    except Exception:  # noqa: BLE001 - vocabulary is advisory
        pass
    # Face/body-expression words observed in real scripts that the
    # label vocabularies do not cover as phrases.
    phrases.update({
        "cau mày", "nhướng mày", "nhướn mày", "nheo mắt",
        "mắt mở lớn", "mắt mở to", "biểu cảm", "nụ cười",
        "cười gượng", "mỉm cười", "cười", "khóc",
    })
    return {p for p in phrases if p}


def _looks_like_expression(text: str, phrases: set[str]) -> bool:
    lowered = (text or "").lower()
    return any(p in lowered for p in phrases)


def _looks_like_constraint(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if lowered.startswith("không ") or lowered.startswith("không,"):
        return True
    return any(m in lowered for m in _CONSTRAINT_MARKERS)


def classify_unsupported(unsupported, package=None) -> dict:
    """Classify every unsupported entry with an explicit handling.

    Returns {"entries": [...], "counts": {...}, "warnings": [...]}.
    Each entry gains "handling_class" + "handling":

    - ROUTED: owned by another stage (map/environment/camera/audio/
      costume/dialogue) -- info, not an error.
    - EXPRESSION_STAGED: a face-expression sentence whose shot
      carries an expression record -- staged statically; a
      within-shot expression TRANSITION is not staged (warning).
    - EXPRESSION_UNVERIFIED: a face-expression sentence, no
      package supplied to verify the shot's expression record.
    - CONSTRAINT: a negative/edit/composition note -- satisfied
      by non-staging or by the planner/camera.
    - VOCABULARY_GAP: an action sentence with no verb mapping --
      warning; listed shot-by-shot in the coverage report.
    - NO_ACTOR: a classified action with no resolvable actor --
      error (see check_compile_outcome, which raises on it).
    """
    phrases = _expression_phrases()
    shot_expressions = {}
    if package is not None:
        try:
            from .action_compiler import compile_shot_expressions
            shot_expressions = compile_shot_expressions(package)
        except Exception:  # noqa: BLE001 - unverified, not fatal
            shot_expressions = {}
    entries = []
    counts: dict[str, int] = {}
    warnings: list[str] = []
    for entry in unsupported or []:
        category = entry.get("category")
        text = entry.get("directive_text") or ""
        if category == "NO_ACTOR":
            handling_class = "NO_ACTOR"
            handling = ("error: classified action with no "
                        "resolvable actor -- fails the stage")
        elif category in _ROUTED_CATEGORIES:
            handling_class = "ROUTED"
            handling = f"routed to the {category.lower()} stage"
        elif _looks_like_constraint(text):
            handling_class = "CONSTRAINT"
            handling = ("staging note / negative constraint -- "
                        "satisfied by non-staging or planner/camera")
        elif _looks_like_expression(text, phrases):
            shot_id = entry.get("shot_id") or entry.get(
                "source_shot_id")
            record = shot_expressions.get(str(shot_id)) if shot_id \
                else None
            if package is None:
                handling_class = "EXPRESSION_UNVERIFIED"
                handling = ("face-expression sentence -- shot "
                            "expression record not verified "
                            "(no package supplied)")
            elif record and record.get("expression"):
                handling_class = "EXPRESSION_STAGED"
                handling = ("staged via the shot expression record "
                            "(static expression; transitions within "
                            "a shot are not staged)")
            else:
                handling_class = "VOCABULARY_GAP"
                handling = ("face-expression sentence with no shot "
                            "expression record -- unstaged")
        else:
            handling_class = "VOCABULARY_GAP"
            handling = ("action sentence with no verb mapping -- "
                        "unstaged; listed in the coverage report")
        counts[handling_class] = counts.get(handling_class, 0) + 1
        classified = dict(entry)
        classified["handling_class"] = handling_class
        classified["handling"] = handling
        entries.append(classified)
        if handling_class in ("VOCABULARY_GAP", "EXPRESSION_STAGED",
                              "EXPRESSION_UNVERIFIED"):
            warnings.append(
                f"{entry.get('action_id')}: [{handling_class}] {text}")
    return {"entries": entries, "counts": counts, "warnings": warnings}


def check_compile_outcome(events, unsupported, *, stage,
                        package=None) -> dict:
    """Raise on mandatory compile failures; else return the
    unsupported classification.

    Raises ProductionError (ACTOR_RESOLUTION_FAILED) when a
    classified action has no resolvable actor -- the pipeline
    must never stage an action for a character it cannot name.
    Vocabulary gaps do not raise here (see the module docstring);
    they return as classified warnings. ``package`` (when
    supplied) lets expression sentences verify against the
    shot's expression record.
    """
    classification = classify_unsupported(unsupported, package)
    no_actor = [e for e in classification["entries"]
                if e["handling_class"] == "NO_ACTOR"]
    if no_actor:
        first = no_actor[0]
        raise ProductionError(
            ACTOR_RESOLUTION_FAILED, stage=stage,
            diagnostic_message=(
                f"{len(no_actor)} classified action(s) with no "
                f"resolvable actor; first: "
                f"{first.get('action_id')}: "
                f"{first.get('directive_text')!r}"),
            affected_entity=first.get("action_id"),
            severity="fatal", recoverability="fix_script",
            suggested_resolution=(
                "Name the acting character in the directive, or "
                "declare the shot's actor; subject elision only "
                "resolves in FIRST_PERSON_ROLEPLAY with a carried "
                "or primary actor."),
            source_scene_id=first.get("source_scene_id"),
            source_shot_id=first.get("source_shot_id"),
            source_directive_id=first.get("source_directive_id"))
    return classification


__all__ = [
    "ProductionError", "wrap_exception", "classify_unsupported",
    "check_compile_outcome",
    "COMPILER_EXCEPTION", "ACTOR_RESOLUTION_FAILED",
    "MANDATORY_PROP_UNSUPPORTED", "TIMELINE_CONFLICT",
    "HISTORICAL_DATASET_UNAVAILABLE", "RENDERER_UNAVAILABLE",
    "GRAPH_VALIDATION_FAILED", "PROP_STATE_CONTRADICTION",
    "STORY_CONFLICT", "MAP_SPEC_ERROR", "STAGE_EXCEPTION",
]
