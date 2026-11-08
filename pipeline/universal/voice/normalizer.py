"""Vietnamese TTS Text Normalizer.

Enforces Part 6:
- Normalizes numbers, dates, years, abbreviations, symbols, and foreign names.
- Changes phonetic representation for synthesis WITHOUT altering semantic meaning.
- Produces (original_text, normalized_spoken_text).
"""
from __future__ import annotations

import re
from typing import Optional

from .lexicon import PronunciationLexicon


class VietnameseTTSNormalizer:
    """Normalizes raw Vietnamese script text into phonetically standard TTS input."""

    DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]

    def __init__(self, lexicon: Optional[PronunciationLexicon] = None):
        self.lexicon = lexicon or PronunciationLexicon()

    def normalize(self, text: str) -> tuple[str, str]:
        """Takes raw script text and returns (original_text, normalized_spoken_text)."""
        original = text.strip()
        normalized = original

        # 1. Normalize symbols
        normalized = normalized.replace("%", " phần trăm")
        normalized = normalized.replace("&", " và ")
        normalized = normalized.replace("+", " cộng ")
        normalized = normalized.replace("—", " - ")
        normalized = normalized.replace("–", " - ")

        # 2. Normalize 4-digit years (e.g. 1914 -> một nghìn chín trăm mười bốn)
        def replace_year(match: re.Match) -> str:
            prefix = match.group(1) or ""
            year_num = int(match.group(2))
            return f"{prefix}{self._number_to_vietnamese(year_num)}"

        normalized = re.sub(r"\b(năm\s+)?(1[89]\d\d|20\d\d)\b", replace_year, normalized, flags=re.IGNORECASE)

        # 3. Normalize dates: "tháng 8" -> "tháng tám"
        def replace_month(match: re.Match) -> str:
            month_num = int(match.group(1))
            month_words = ["", "một", "hai", "ba", "tư", "năm", "sáu", "bảy", "tám", "chín", "mười", "mười một", "mười hai"]
            m_str = month_words[month_num] if 1 <= month_num <= 12 else str(month_num)
            return f"tháng {m_str}"

        normalized = re.sub(r"\btháng\s+([1-9]|1[0-2])\b", replace_month, normalized, flags=re.IGNORECASE)

        # 4. Normalize standalone numbers (e.g. 25 -> hai mươi lăm, 16 -> mười sáu)
        def replace_number(match: re.Match) -> str:
            val = int(match.group(0))
            return self._number_to_vietnamese(val)

        normalized = re.sub(r"\b\d+\b", replace_number, normalized)

        # 5. Apply Pronunciation Lexicon for foreign & historical names
        normalized = self.lexicon.apply_pronunciation(normalized)

        # 6. Normalize punctuation: remove excessive dots, commas, exclamation marks
        normalized = re.sub(r"\.{4,}", "...", normalized)
        normalized = re.sub(r"!{2,}", "!", normalized)
        normalized = re.sub(r"\?{2,}", "?", normalized)
        normalized = re.sub(r",{2,}", ",", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()

        return original, normalized

    def _number_to_vietnamese(self, n: int) -> str:
        """Converts integer (0 to 999999) to standard Vietnamese words."""
        if n == 0:
            return "không"
        if n < 0:
            return "âm " + self._number_to_vietnamese(-n)

        if n < 10:
            return self.DIGITS[n]

        if n < 20:
            unit = n % 10
            if unit == 0:
                return "mười"
            elif unit == 5:
                return "mười lăm"
            else:
                return f"mười {self.DIGITS[unit]}"

        if n < 100:
            ten = n // 10
            unit = n % 10
            ten_str = f"{self.DIGITS[ten]} mươi"
            if unit == 0:
                return ten_str
            elif unit == 1:
                return f"{ten_str} mốt"
            elif unit == 4:
                return f"{ten_str} tư"
            elif unit == 5:
                return f"{ten_str} lăm"
            else:
                return f"{ten_str} {self.DIGITS[unit]}"

        if n < 1000:
            hundred = n // 100
            rem = n % 100
            h_str = f"{self.DIGITS[hundred]} trăm"
            if rem == 0:
                return h_str
            elif rem < 10:
                return f"{h_str} linh {self.DIGITS[rem]}"
            else:
                return f"{h_str} {self._number_to_vietnamese(rem)}"

        if n < 1000000:
            thousand = n // 1000
            rem = n % 1000
            t_str = f"{self._number_to_vietnamese(thousand)} nghìn"
            if rem == 0:
                return t_str
            elif rem < 100:
                return f"{t_str} không trăm {self._number_to_vietnamese(rem)}"
            else:
                return f"{t_str} {self._number_to_vietnamese(rem)}"

        return str(n)
