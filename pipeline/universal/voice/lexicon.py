"""Pronunciation Lexicon Data Layer for Vietnamese Historical & Foreign Names.

Guarantees accurate, culturally standard Vietnamese phonetic representations
for historical figures, European locations, and military terms.
Separates phonetic data from pipeline logic.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional


class PronunciationLexicon:
    """Stores and applies phonetic pronunciation rules for TTS speech synthesis."""

    DEFAULT_LEXICON = {
        # Historical Figures
        "Adolf Hitler": "A-đôn Hít-le",
        "Hitler": "Hít-le",
        "Kaiser Wilhelm": "Khai-dơ Vin-hem",
        "Wilhelm": "Vin-hem",
        "Franz Ferdinand": "Phơ-răng Phéc-đi-năng",
        "Napoleon": "Na-pô-lê-ông",
        "Bismarck": "Bít-mác",

        # Historical Locations (WW1 & European Geography)
        "Munich": "Miu-ních",
        "Bavaria": "Ba-va-ri-a",
        "Bavarian": "Ba-va-ri-a",
        "Ypres": "I-prơ",
        "Somme": "Xôm",
        "Pasewalk": "Pa-xơ-vanh-k",
        "Odeonsplatz": "Ô-đê-ông-xơ-plát",
        "Versailles": "Véc-xây",
        "Flanders": "Phran-đơ",
        "Berlin": "Béc-lin",
        "Vienna": "Vi-ên",
        "Sarajevo": "Xa-ra-yê-vô",

        # Military & Historical Concepts
        "Reich": "Rai-kh",
        "Wehrmacht": "Ve-mác",
        "Feldwebel": "Phem-ve-ben",
        "Iron Cross": "Thập tự Sắt",

        # Loan words & Modern Idioms in Script
        "Spoiler": "Xpoi-lơ",
        "podcast": "pót-cát",
        "video": "vi-đê-ô",
    }

    def __init__(self, custom_entries: Optional[dict[str, str]] = None, json_path: Optional[Path] = None):
        self._entries: dict[str, str] = dict(self.DEFAULT_LEXICON)
        if json_path and Path(json_path).is_file():
            try:
                data = json.loads(Path(json_path).read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._entries.update(data)
            except Exception:
                pass
        if custom_entries:
            self._entries.update(custom_entries)

    def register(self, term: str, pronunciation: str) -> None:
        self._entries[term] = pronunciation

    def apply_pronunciation(self, text: str) -> str:
        """Substitutes terms with their phonetic pronunciation respecting word boundaries."""
        result = text
        # Sort terms by length descending to replace multi-word phrases first (e.g. 'Adolf Hitler' before 'Hitler')
        sorted_terms = sorted(self._entries.keys(), key=len, reverse=True)
        for term in sorted_terms:
            phonetic = self._entries[term]
            # Word boundary regex with case-insensitive search
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            result = pattern.sub(phonetic, result)
        return result

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "total_terms": len(self._entries),
            "lexicon_entries": self._entries,
        }
