"""Các hàm easing cho animation mượt (kinetic typography, chuyển động nhân vật)."""

import math


def linear(t):
    return t


def ease_in_quad(t):
    return t * t


def ease_out_quad(t):
    return t * (2 - t)


def ease_in_out_quad(t):
    return 2 * t * t if t < 0.5 else -1 + (4 - 2 * t) * t


def ease_in_cubic(t):
    return t * t * t


def ease_out_cubic(t):
    t -= 1
    return t * t * t + 1


def ease_in_out_cubic(t):
    if t < 0.5:
        return 4 * t * t * t
    t -= 1
    return 4 * t * t * t + 1


def ease_out_back(t, s=1.70158):
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def ease_out_elastic(t):
    if t == 0 or t == 1:
        return t
    return math.pow(2, -10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1


def ease_out_bounce(t):
    n1 = 7.5625
    d1 = 2.75
    if t < 1 / d1:
        return n1 * t * t
    elif t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    elif t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


EASINGS = {
    "linear": linear,
    "in_quad": ease_in_quad,
    "out_quad": ease_out_quad,
    "in_out_quad": ease_in_out_quad,
    "in_cubic": ease_in_cubic,
    "out_cubic": ease_out_cubic,
    "in_out_cubic": ease_in_out_cubic,
    "out_back": ease_out_back,
    "out_elastic": ease_out_elastic,
    "out_bounce": ease_out_bounce,
}


def ease(name, t):
    """t trong [0,1] -> giá trị easing [0,1]."""
    t = max(0.0, min(1.0, t))
    fn = EASINGS.get(name, linear)
    return fn(t)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def lerp(a, b, t):
    return a + (b - a) * t
