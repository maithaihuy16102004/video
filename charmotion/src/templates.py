"""Templates kịch bản sẵn cho các chủ đề phổ biến (tech, giáo dục, động lực...).

Mỗi template là hàm nhận (title, points, options) -> script JSON đầy đủ để render.
"""


def _base(width=1080, height=1920, fps=30):
    return {"width": width, "height": height, "fps": fps, "scenes": []}


def tech_explainer(title, points, hook=None, accent=(255, 200, 60),
                   dark=(20, 25, 45), fps=30):
    """Chủ đề công nghệ / lập trình: nền tech + nhân vật giải thích."""
    s = _base(fps=fps)
    n = len(points)

    # Hook scene
    s["scenes"].append({
        "title": "hook",
        "duration": 3.0,
        "background": {"type": "tech", "top": dark, "bottom": (5, 10, 25),
                       "grid_color": (70, 150, 230)},
        "texts": [
            {"text": hook or "Bạn có biết?", "x": 0.5, "y": 0.3, "size": 90,
             "effect": "pop", "delay": 0.2, "duration": 1.5, "max_width": 950},
        ],
        "shapes": [
            {"type": "lightbulb", "x": 0.5, "y": 0.55, "radius": 90,
             "color": accent, "delay": 0.4, "duration": 1.2},
        ],
    })

    # Title scene
    s["scenes"].append({
        "title": "title",
        "duration": 3.5,
        "background": {"type": "gradient", "top": dark, "bottom": (8, 12, 28)},
        "character": {"pose": "wave", "expression": "happy", "x": 0.5,
                      "y": 0.72, "scale": 130},
        "texts": [
            {"text": title, "x": 0.5, "y": 0.22, "size": 96, "effect": "pop",
             "delay": 0.2, "duration": 1.6, "max_width": 950},
        ],
    })

    # Point scenes
    for i, pt in enumerate(points):
        s["scenes"].append({
            "title": f"point_{i+1}",
            "duration": 4.0,
            "background": {"type": "tech", "top": dark, "bottom": (5, 10, 25),
                           "grid_color": (70, 150, 230)},
            "character": {"pose": "talk", "expression": "neutral",
                          "x": 0.3, "y": 0.72, "scale": 110, "talking": True},
            "texts": [
                {"text": f"{i+1}", "x": 0.5, "y": 0.16, "size": 70,
                 "effect": "pop", "delay": 0.1, "duration": 1.0,
                 "color": accent},
                {"text": pt, "x": 0.5, "y": 0.42, "size": 62,
                 "effect": "slide_up", "delay": 0.4, "duration": 1.2,
                 "max_width": 900},
            ],
            "shapes": [
                {"type": "progress", "x": 0.5, "y": 0.88, "width": 700,
                 "height": 26, "color": accent,
                 "delay": 0.6, "duration": 2.0},
            ],
        })

    # CTA / outro
    s["scenes"].append({
        "title": "outro",
        "duration": 3.0,
        "background": {"type": "gradient", "top": accent, "bottom": (200, 130, 30)},
        "character": {"pose": "thumbs_up", "expression": "happy",
                      "x": 0.5, "y": 0.7, "scale": 140},
        "texts": [
            {"text": "Follow để xem thêm!", "x": 0.5, "y": 0.25, "size": 80,
             "effect": "bounce", "delay": 0.3, "duration": 1.5, "max_width": 900},
        ],
    })

    return s


def motivation(title, points, hook=None, accent=(255, 120, 120),
               dark=(40, 15, 40), fps=30):
    """Chủ đề động lực / truyền cảm hứng: nền ấm + nhân vật excited."""
    s = _base(fps=fps)
    s["scenes"].append({
        "title": "hook",
        "duration": 3.0,
        "background": {"type": "gradient", "top": dark, "bottom": (20, 8, 30)},
        "texts": [
            {"text": hook or "Đừng bỏ cuộc!", "x": 0.5, "y": 0.35, "size": 100,
             "effect": "pop", "delay": 0.2, "duration": 1.5},
        ],
        "shapes": [
            {"type": "star", "x": 0.3, "y": 0.6, "radius": 60, "color": accent},
            {"type": "star", "x": 0.7, "y": 0.55, "radius": 45, "color": accent},
        ],
    })
    s["scenes"].append({
        "title": "title",
        "duration": 3.0,
        "background": {"type": "gradient", "top": dark, "bottom": (25, 10, 35)},
        "character": {"pose": "excited", "expression": "excited",
                      "x": 0.5, "y": 0.7, "scale": 130},
        "texts": [
            {"text": title, "x": 0.5, "y": 0.22, "size": 92, "effect": "scale",
             "delay": 0.2, "duration": 1.5, "max_width": 950},
        ],
    })
    for i, pt in enumerate(points):
        s["scenes"].append({
            "title": f"point_{i+1}",
            "duration": 3.5,
            "background": {"type": "gradient", "top": dark, "bottom": (15, 8, 30)},
            "character": {"pose": "talk", "expression": "happy",
                          "x": 0.5, "y": 0.72, "scale": 120, "talking": True},
            "texts": [
                {"text": pt, "x": 0.5, "y": 0.35, "size": 68,
                 "effect": "fade", "delay": 0.3, "duration": 1.5, "max_width": 900},
            ],
            "shapes": [
                {"type": "heart", "x": 0.5, "y": 0.7, "size": 55,
                 "color": accent, "delay": 0.5, "duration": 1.5},
            ],
        })
    s["scenes"].append({
        "title": "outro",
        "duration": 3.0,
        "background": {"type": "gradient", "top": accent, "bottom": (150, 60, 60)},
        "character": {"pose": "excited", "expression": "excited",
                      "x": 0.5, "y": 0.7, "scale": 140},
        "texts": [
            {"text": "Bạn làm được!", "x": 0.5, "y": 0.25, "size": 85,
             "effect": "bounce", "delay": 0.3, "duration": 1.5},
        ],
    })
    return s


def education(title, points, hook=None, accent=(90, 200, 160),
              dark=(15, 40, 40), fps=30):
    """Chủ đề giáo dục / mẹo hay: nền xanh + nhân vật chỉ dẫn."""
    s = _base(fps=fps)
    s["scenes"].append({
        "title": "hook",
        "duration": 3.0,
        "background": {"type": "gradient", "top": dark, "bottom": (8, 25, 25)},
        "texts": [
            {"text": hook or "Mẹo hay hôm nay!", "x": 0.5, "y": 0.35, "size": 92,
             "effect": "pop", "delay": 0.2, "duration": 1.5},
        ],
        "shapes": [
            {"type": "lightbulb", "x": 0.5, "y": 0.62, "radius": 80,
             "color": accent, "delay": 0.4, "duration": 1.2},
        ],
    })
    s["scenes"].append({
        "title": "title",
        "duration": 3.0,
        "background": {"type": "gradient", "top": dark, "bottom": (10, 28, 28)},
        "character": {"pose": "point", "expression": "neutral",
                      "x": 0.5, "y": 0.72, "scale": 130},
        "texts": [
            {"text": title, "x": 0.5, "y": 0.22, "size": 88, "effect": "slide_up",
             "delay": 0.2, "duration": 1.5, "max_width": 950},
        ],
    })
    for i, pt in enumerate(points):
        s["scenes"].append({
            "title": f"point_{i+1}",
            "duration": 3.5,
            "background": {"type": "gradient", "top": dark, "bottom": (8, 25, 25)},
            "character": {"pose": "talk", "expression": "neutral",
                          "x": 0.5, "y": 0.72, "scale": 120, "talking": True},
            "texts": [
                {"text": f"Bước {i+1}", "x": 0.5, "y": 0.16, "size": 60,
                 "effect": "pop", "delay": 0.1, "duration": 1.0, "color": accent},
                {"text": pt, "x": 0.5, "y": 0.4, "size": 64,
                 "effect": "slide_left", "delay": 0.4, "duration": 1.2,
                 "max_width": 900},
            ],
        })
    s["scenes"].append({
        "title": "outro",
        "duration": 3.0,
        "background": {"type": "gradient", "top": accent, "bottom": (30, 120, 90)},
        "character": {"pose": "thumbs_up", "expression": "happy",
                      "x": 0.5, "y": 0.7, "scale": 140},
        "texts": [
            {"text": "Lưu lại ngay!", "x": 0.5, "y": 0.25, "size": 82,
             "effect": "bounce", "delay": 0.3, "duration": 1.5},
        ],
    })
    return s


TEMPLATES = {
    "tech": tech_explainer,
    "motivation": motivation,
    "education": education,
}
