"""Silhouette identity differentiation (Cinematic Engine Upgrade,
Phase D).

Identity must read in GRAYSCALE / SILHOUETTE: costume, hair,
headwear, accessories, proportions and pose -- never colour alone.
This module measures identity from the character DATA (the
Stickman/template fields that character_art.py draws), without
redesigning any approved art: head ratio 0.34 stays locked and
character_art.py is untouched. Colour is recorded separately and
never contributes to the shape score, so a pair that differs only
by suit colour scores as INDISTINGUISHABLE here (that is the point).

Pixel-level silhouette IoU (render two characters, threshold, IoU
of the masks) needs the renderer and lives with ATLAS (see the
report); this module is the data-level gate that runs in unit tests
and proof scripts without rendering.
"""
from __future__ import annotations

__all__ = [
    "DISTINGUISHABLE_THRESHOLD",
    "identity_signature",
    "silhouette_signature",
    "grayscale_features",
    "shape_distance",
    "distinguishable",
    "pairwise_report",
]

# Minimum shape distance for two characters to read as different
# people in silhouette. Calibrated so that "hat + moustache" (the
# Lustig signature vs a plain suit) clears it, while "moustache
# only" or "glasses only" does not.
DISTINGUISHABLE_THRESHOLD = 3.0

# Feature weights: the features that change the outline most count
# most. Hat changes the head silhouette outright; hair and costume
# change the outline; body variant and height change proportions;
# moustache/glasses/cane are smaller outline details. eye_count
# (Test F): a single central eye is a strong identity signal -- the
# same precedent as glasses (an interior face feature that still
# reads at a glance) -- weighted like hair.
_WEIGHTS = {
    "template": 2.0,
    "body_variant": 1.0,
    "hat": 3.0,
    "hair_style": 2.0,
    "moustache_style": 1.0,
    "glasses": 1.0,
    "cane": 1.0,
    "costume": 2.0,
    "eye_count": 2.0,
}

_SHAPE_KEYS = tuple(_WEIGHTS)


def _field(char, name, default=None):
    if isinstance(char, dict):
        return char.get(name, default)
    return getattr(char, name, default)


def identity_signature(char) -> dict:
    """Shape + colour identity for a Stickman or a trait dict.

    "shape" is the silhouette identity (no colour); "colour" is
    recorded separately and excluded from every shape score;
    "height_px" is the drawn height (proportions, not colour).
    """
    shape = {key: _field(char, key) for key in _SHAPE_KEYS}
    # Normalise the moustache bool legacy: moustache=True with no
    # style means "full" (see rig.Stickman).
    if shape["moustache_style"] is None:
        shape["moustache_style"] = (
            "full" if _field(char, "moustache") else "none")
    # Normalise eye_count: characters / dicts that predate the trait
    # have two eyes (the rig default).
    if shape.get("eye_count") is None:
        shape["eye_count"] = 2
    return {
        "shape": shape,
        "colour": {"suit": _field(char, "suit"),
                   "skin": _field(char, "skin")},
        "height_px": float(_field(char, "H", _field(char, "height", 560.0))),
        "name": _field(char, "name"),
    }


def silhouette_signature(char) -> dict:
    """The shape-only part of the identity (alias for the silhouette
    features of ``identity_signature``)."""
    return identity_signature(char)["shape"]


def grayscale_features(signature: dict) -> tuple:
    """The identity as it reads without colour: the shape feature
    tuple plus a coarse height bucket (height differences under 5%
    do not count as a distinguishing feature)."""
    sig = signature["shape"] if "shape" in signature else signature
    height = signature.get("height_px", 560.0) if "shape" in signature \
        else 560.0
    bucket = round(float(height) / 560.0, 1)
    return tuple(sig.get(key) for key in _SHAPE_KEYS) + (bucket,)


def shape_distance(sig_a: dict, sig_b: dict) -> float:
    """Weighted shape distance between two identity signatures
    (or two shape dicts). Height contributes 4.0 * relative
    difference, so a 1.8x giant is far from an adult on proportions
    alone."""
    a = sig_a["shape"] if "shape" in sig_a else sig_a
    b = sig_b["shape"] if "shape" in sig_b else sig_b
    distance = 0.0
    for key, weight in _WEIGHTS.items():
        if a.get(key) != b.get(key):
            distance += weight
    ha = sig_a.get("height_px", 560.0) if "shape" in sig_a else 560.0
    hb = sig_b.get("height_px", 560.0) if "shape" in sig_b else 560.0
    denom = max(float(ha), float(hb))
    if denom > 0:
        distance += 4.0 * abs(float(ha) - float(hb)) / denom
    return distance


def distinguishable(char_a, char_b,
                    threshold: float = DISTINGUISHABLE_THRESHOLD
                    ) -> dict:
    """{distinguishable, distance, differing} for two characters.

    ``differing`` names the shape features that differ, so a failure
    says exactly what to change (add a hat, change the costume...)
    instead of reporting a bare score.
    """
    sig_a, sig_b = identity_signature(char_a), identity_signature(char_b)
    distance = shape_distance(sig_a, sig_b)
    differing = [key for key in _SHAPE_KEYS
                 if sig_a["shape"].get(key) != sig_b["shape"].get(key)]
    if abs(sig_a["height_px"] - sig_b["height_px"]) / max(
            sig_a["height_px"], sig_b["height_px"], 1.0) >= 0.05:
        differing.append("height_px")
    return {
        "distinguishable": distance >= threshold,
        "distance": distance,
        "differing": differing,
    }


def pairwise_report(chars) -> list[dict]:
    """Distinguishability for every pair in ``chars``.

    ``chars`` is {name: Stickman-or-dict} or a list of characters
    (names fall back to the character's ``name`` field / index).
    Returns [{a, b, distinguishable, distance, differing}].
    """
    if isinstance(chars, dict):
        items = list(chars.items())
    else:
        items = [(getattr(c, "name", None) or f"char_{i}", c)
                 for i, c in enumerate(chars)]
    report: list[dict] = []
    for i, (name_a, char_a) in enumerate(items):
        for name_b, char_b in items[i + 1:]:
            result = distinguishable(char_a, char_b)
            result.update({"a": name_a, "b": name_b})
            report.append(result)
    return report
