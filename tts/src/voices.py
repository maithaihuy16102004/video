"""Các giọng đọc tiếng Việt (preset) + khám phá giọng từ edge-tts.

Giọng neural tiếng Việt chuẩn của Microsoft (dùng qua edge-tts, miễn phí):
  - vi-VN-HoaiMyNeural  (Nữ — trong trẻo, tự nhiên, phù hợp kể chuyện/news)
  - vi-VN-NamMinhNeural  (Nam — trầm ấm, phù hợp báo cáo/daily)

Các tên preset thân thiện ở dưới để dễ gọi, có thể dùng trực tiếp voice id.
"""

# preset -> (voice id, giới tính, mô tả ngắn)
VI_VOICES = {
    "hoaimy": ("vi-VN-HoaiMyNeural", "female",
               "Giọng nữ trong trẻo, tự nhiên — tốt cho kể chuyện, tin tức, shorts"),
    "namminh": ("vi-VN-NamMinhNeural", "male",
                "Giọng nam trầm ấm, rõ ràng — tốt cho báo cáo, documentary, daily"),
    "vieneu-minhquan": ("vieneu-Minh Quân", "male", "VieNeu-TTS: Nam Bắc tự nhiên, chân thực"),
    "vieneu-aihan": ("vieneu-Ái Hân", "female", "VieNeu-TTS: Nữ Nam tin tức, rõ ràng"),
    "vieneu-myduyen": ("vieneu-Mỹ Duyên", "female", "VieNeu-TTS: Nữ Bắc đọc truyện cảm xúc"),
    "vieneu-ductri": ("vieneu-Đức Trí", "male", "VieNeu-TTS: Nam Bắc đọc truyện truyền cảm"),
    "vieneu-huuquan": ("vieneu-Hữu Quân", "male", "VieNeu-TTS: Nam Bắc tin tức đĩnh đạc"),
    "vieneu-xuantien": ("vieneu-Xuân Tiên", "female", "VieNeu-TTS: Nữ Bắc thời sự, chuyên nghiệp"),
    "vieneu-maianh": ("vieneu-Mai Anh", "female", "VieNeu-TTS: Nữ Bắc tin tức, lưu loát"),
    "vieneu-trucly": ("vieneu-Trúc Ly", "female", "VieNeu-TTS: Nữ Bắc tự nhiên, duyên dáng"),
    "vieneu-anhkhoi": ("vieneu-Anh Khôi", "male", "VieNeu-TTS: Nam Bắc kể chuyện hào sảng"),
    "vieneu-manhdung": ("vieneu-Mạnh Dũng", "male", "VieNeu-TTS: Nam Bắc tự nhiên, mạnh mẽ"),
    "vieneu-adam": ("vieneu-Adam", "male", "VieNeu-TTS: Nam Nam tự nhiên, phóng khoáng"),
}

# alias ngắn
VI_ALIASES = {
    "nu": "hoaimy",
    "nam": "namminh",
    "female": "hoaimy",
    "male": "namminh",
    "minhquan": "vieneu-minhquan",
    "aihan": "vieneu-aihan",
    "myduyen": "vieneu-myduyen",
    "ductri": "vieneu-ductri",
    "huuquan": "vieneu-huuquan",
    "xuantien": "vieneu-xuantien",
    "maianh": "vieneu-maianh",
    "trucly": "vieneu-trucly",
    "anhkhoi": "vieneu-anhkhoi",
    "manhdung": "vieneu-manhdung",
    "adam": "vieneu-adam",
}


def resolve_voice(name: str) -> str:
    """Trả về voice id từ preset/alias, hoặc trả về nguyên nếu đã là voice id."""
    key = name.strip().lower()
    if key in VI_ALIASES:
        key = VI_ALIASES[key]
    if key in VI_VOICES:
        return VI_VOICES[key][0]
    # mặc định: coi như voice id trực tiếp (vd "vi-VN-HoaiMyNeural")
    return name


def describe(name: str) -> str:
    key = name.strip().lower()
    if key in VI_ALIASES:
        key = VI_ALIASES[key]
    if key in VI_VOICES:
        _, gender, desc = VI_VOICES[key]
        return f"{gender} — {desc}"
    return "voice id trực tiếp"


def list_vi_voices_async():
    """Khám phá toàn bộ giọng tiếng Việt từ edge-tts (cần có mạng).

    Trả về danh sách dict: {id, gender, locale}.
    """
    import edge_tts  # noqa: PLC0415

    async def _get():
        voices = await edge_tts.list_voices()
        out = []
        for v in voices:
            locale = getattr(v, "Locale", "") or ""
            if locale.lower().startswith("vi-"):
                out.append({
                    "id": getattr(v, "ShortName", ""),
                    "gender": getattr(v, "Gender", ""),
                    "locale": locale,
                })
        return out

    import asyncio
    return asyncio.run(_get())
