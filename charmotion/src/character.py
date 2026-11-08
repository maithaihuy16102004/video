"""Nhân vật hoạt hình 2D (cartoon character) có thể tạo dáng + biểu cảm + cử động miệng.

Vẽ bằng Pillow theo kiểu vector (parametric) nên mượt ở mọi kích thước và dễ animation.
"""

import math
from PIL import ImageDraw

from easing import lerp, clamp


def _line(draw, p1, p2, width, fill):
    """Vẽ đoạn thẳng bo tròn đầu (capsule)."""
    draw.line([p1, p2], fill=fill, width=int(width))


def _circle(draw, center, radius, fill, outline=None, ow=1):
    x, y = center
    draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                 fill=fill, outline=outline, width=ow)


# --- Pose: trả về các góc khớp (độ) cho tay trái/phải ---
# mỗi tay: (shoulder_angle, elbow_angle) đo từ phương thẳng đứng xuống
POSES = {
    "idle":      {"left": (15, 10),  "right": (-15, -10), "tilt": 0},
    "wave":      {"left": (10, 10),  "right": (-160, -30), "tilt": 0},
    "point":     {"left": (20, 10),  "right": (-90, -5),  "tilt": 0},
    "talk":      {"left": (-40, -60), "right": (40, 60),  "tilt": 0},
    "excited":   {"left": (-150, -20), "right": (150, 20), "tilt": -5},
    "thumbs_up": {"left": (15, 10),  "right": (-120, -10), "tilt": 0},
    "thinking":  {"left": (15, 10),  "right": (-45, -90), "tilt": 5},
    "surprised": {"left": (-70, -20), "right": (70, 20),  "tilt": 0},
}


def default_colors():
    return {
        "skin": (255, 213, 170),
        "hair": (60, 45, 35),
        "shirt": (66, 133, 244),
        "pants": (50, 50, 60),
        "shoes": (40, 40, 45),
        "outline": (30, 30, 40),
        "mouth": (180, 60, 60),
        "blush": (255, 170, 170),
        "eye": (40, 40, 50),
    }


def _pose_angles(pose):
    return POSES.get(pose, POSES["idle"])


def _hand_pos(shoulder, shoulder_ang, elbow_ang, upper_len, fore_len, arm_swing=0.0):
    """Tính vị trí tay từ khớp vai + góc (độ, 0 = chỉ xuống dưới, dương = ra ngoài)."""
    a1 = math.radians(shoulder_ang + arm_swing * 6)
    elbow = (
        shoulder[0] + upper_len * math.sin(a1),
        shoulder[1] + upper_len * math.cos(a1),
    )
    a2 = math.radians(shoulder_ang + elbow_ang + arm_swing * 8)
    hand = (
        elbow[0] + fore_len * math.sin(a2),
        elbow[1] + fore_len * math.cos(a2),
    )
    return elbow, hand


def draw_character(draw, cx, cy, scale=1.0, pose="idle", expression="neutral",
                   talking=0.0, arm_swing=0.0, colors=None, facing=0.0):
    """Vẽ nhân vật. (cx, cy) = tâm của thân (ngực). scale = bán kính đầu px."""
    c = colors or default_colors()
    r = scale  # bán kính đầu

    tilt = _pose_angles(pose).get("tilt", 0)
    tilt_r = math.radians(tilt)

    # --- các điểm mốc (theo hệ head-radius, y xuống dưới) ---
    head_c = (cx, cy - 1.6 * r)
    neck = (cx, cy - 0.9 * r)
    shoulder_y = cy - 0.6 * r
    hip_y = cy + 0.7 * r
    foot_y = cy + 1.8 * r

    sh_width = 0.9 * r  # nửa rộng vai

    left_shoulder = (cx - sh_width, shoulder_y)
    right_shoulder = (cx + sh_width, shoulder_y)
    left_hip = (cx - 0.35 * r, hip_y)
    right_hip = (cx + 0.35 * r, hip_y)

    upper_len = 0.9 * r
    fore_len = 0.85 * r

    angles = _pose_angles(pose)

    # --- chân (2 đoạn: đùi + cẳng) ---
    leg_swing = math.sin(arm_swing * math.pi) * 4  # lắc nhẹ theo nhịp
    for hip, side in ((left_hip, -1), (right_hip, 1)):
        knee = (hip[0] + side * 0.12 * r, hip[1] + 0.5 * r)
        foot = (hip[0] + side * 0.15 * r + side * leg_swing * 0.05 * r, foot_y)
        _line(draw, hip, knee, 0.24 * r, c["pants"])
        _line(draw, knee, foot, 0.20 * r, c["pants"])
        # giày
        _circle(draw, (foot[0], foot[1] - 0.05 * r), 0.14 * r, c["shoes"])

    # --- thân (áo) ---
    body_rect = [
        cx - 0.55 * r, shoulder_y - 0.1 * r,
        cx + 0.55 * r, hip_y + 0.05 * r,
    ]
    draw.rounded_rectangle(body_rect, radius=int(0.3 * r), fill=c["shirt"])

    # --- tay ---
    left_ang = angles["left"]
    right_ang = angles["right"]
    l_elbow, l_hand = _hand_pos(left_shoulder, left_ang[0], left_ang[1],
                                upper_len, fore_len, -arm_swing)
    r_elbow, r_hand = _hand_pos(right_shoulder, right_ang[0], right_ang[1],
                                upper_len, fore_len, arm_swing)
    _line(draw, left_shoulder, l_elbow, 0.22 * r, c["shirt"])
    _line(draw, l_elbow, l_hand, 0.18 * r, c["shirt"])
    _line(draw, right_shoulder, r_elbow, 0.22 * r, c["shirt"])
    _line(draw, r_elbow, r_hand, 0.18 * r, c["shirt"])
    _circle(draw, l_hand, 0.16 * r, c["skin"])
    _circle(draw, r_hand, 0.16 * r, c["skin"])

    # --- cổ ---
    _line(draw, neck, (cx, shoulder_y - 0.05 * r), 0.18 * r, c["skin"])

    # --- đầu ---
    hx, hy = head_c
    _circle(draw, (hx, hy), r, c["skin"])

    # tóc (nửa trên + mái)
    draw.pieslice([hx - r, hy - r, hx + r, hy + r], 180, 360, fill=c["hair"])
    draw.pieslice([hx - r, hy - r, hx + r, hy + 0.1 * r], 180, 360, fill=c["hair"])

    # --- mặt (biểu cảm) ---
    eye_y = hy - 0.1 * r
    eye_dx = 0.38 * r
    eye_r = 0.13 * r

    if expression == "surprised":
        _circle(draw, (hx - eye_dx, eye_y), eye_r * 1.3, (255, 255, 255), c["eye"], 2)
        _circle(draw, (hx + eye_dx, eye_y), eye_r * 1.3, (255, 255, 255), c["eye"], 2)
        _circle(draw, (hx - eye_dx, eye_y), eye_r * 0.45, c["eye"])
        _circle(draw, (hx + eye_dx, eye_y), eye_r * 0.45, c["eye"])
    elif expression == "happy" or expression == "excited":
        # mắt cười (hình vòng cung)
        _arc_eye(draw, hx - eye_dx, eye_y, eye_r * 1.6, c["eye"], flip=False)
        _arc_eye(draw, hx + eye_dx, eye_y, eye_r * 1.6, c["eye"], flip=True)
    elif expression == "thinking":
        _circle(draw, (hx - eye_dx, eye_y), eye_r, (255, 255, 255))
        _circle(draw, (hx - eye_dx, eye_y), eye_r * 0.5, c["eye"])
        _circle(draw, (hx + eye_dx, eye_y), eye_r, (255, 255, 255))
        _circle(draw, (hx + eye_dx, eye_y), eye_r * 0.5, c["eye"])
        # lông mày nhíu
        _line(draw, (hx - eye_dx - 0.1 * r, eye_y - 0.25 * r),
              (hx - eye_dx + 0.12 * r, eye_y - 0.18 * r), 3, c["hair"])
    else:  # neutral
        _circle(draw, (hx - eye_dx, eye_y), eye_r, (255, 255, 255))
        _circle(draw, (hx + eye_dx, eye_y), eye_r, (255, 255, 255))
        _circle(draw, (hx - eye_dx, eye_y), eye_r * 0.5, c["eye"])
        _circle(draw, (hx + eye_dx, eye_y), eye_r * 0.5, c["eye"])

    # má hồng
    _circle(draw, (hx - 0.55 * r, hy + 0.25 * r), 0.14 * r, c["blush"])
    _circle(draw, (hx + 0.55 * r, hy + 0.25 * r), 0.14 * r, c["blush"])

    # --- miệng ---
    mouth_y = hy + 0.35 * r
    if expression == "surprised":
        _circle(draw, (hx, mouth_y), 0.12 * r * (1 + talking), c["mouth"])
    elif expression == "happy" or expression == "excited":
        _arc_mouth(draw, hx, mouth_y, 0.3 * r, c["mouth"], talking)
    elif expression == "thinking":
        # mím môi
        _line(draw, (hx - 0.15 * r, mouth_y), (hx + 0.15 * r, mouth_y), 3, c["mouth"])
    else:
        # mở theo talking
        if talking > 0.05:
            _circle(draw, (hx, mouth_y), 0.12 * r * (0.5 + talking), c["mouth"])
        else:
            _line(draw, (hx - 0.15 * r, mouth_y), (hx + 0.15 * r, mouth_y), 3, c["mouth"])

    return (cx, cy)


def _arc_eye(draw, cx, cy, radius, fill, flip=False):
    """Mắt cười (nét cong)."""
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    if flip:
        draw.arc(bbox, 20, 160, fill=fill, width=4)
    else:
        draw.arc(bbox, 20, 160, fill=fill, width=4)


def _arc_mouth(draw, cx, cy, radius, fill, talking):
    """Miệng cười; nếu talking>0 thì vẽ miệng mở (ellipse)."""
    if talking > 0.1:
        h = radius * (0.4 + talking)
        draw.ellipse([cx - radius, cy - h, cx + radius, cy + h], fill=fill)
    else:
        draw.arc([cx - radius, cy - radius, cx + radius, cy + radius],
                 200, 340, fill=fill, width=4)
