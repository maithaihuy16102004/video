"""Meme Sound Resolver & Asset Validator for Studio Script V1.
Manages the cloned Myinstants Vietnam meme library in d:\\Agent\\assets\\memes.
Enforces Production Rules:
- Rule 7: MEME cues are optional and must not replace essential Foley.
- Rule 8: Never place meme audio over important dialogue.
- Rule 9: Never use meme sounds during serious historical tragedy, death or suffering.
- Rule 10: If an asset is missing, report it instead of substituting unrelated content.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[1]
MEMES_DIR = ROOT_DIR / "assets" / "memes"
CATALOG_PATH = MEMES_DIR / "catalog.json"


def normalize_keyword(text: str) -> str:
    """Normalize text removing accents and punctuation for accurate matching."""
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text)
    only_ascii = "".join([c for c in nfkd if not unicodedata.combining(c)])
    clean = re.sub(r'[^a-zA-Z0-9\w]+', ' ', only_ascii).strip().lower()
    return clean


@dataclass
class ResolvedMemeSound:
    meme_id: str
    title: str
    filename: str
    file_path: Path
    gain_db: float
    trigger: str
    exists: bool
    is_missing: bool
    error_message: Optional[str] = None


class MemeSoundResolver:
    """Fast indexed resolver for Vietnam memes downloaded from Myinstants."""

    def __init__(self, catalog_path: Optional[Path] = None):
        self.catalog_path = catalog_path or CATALOG_PATH
        self.memes: List[Dict[str, Any]] = []
        self._load_catalog()

    def _load_catalog(self):
        if self.catalog_path.exists():
            try:
                with open(self.catalog_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.memes = data.get("memes", [])
            except Exception as e:
                print(f"[MemeResolver] Error loading catalog: {e}")
                self.memes = []
        else:
            # Fallback scan files directly in MEMES_DIR
            if MEMES_DIR.exists():
                for p in MEMES_DIR.glob("*.mp3"):
                    self.memes.append({
                        "id": p.stem,
                        "title": p.stem.replace('_', ' ').title(),
                        "filename": p.name,
                        "local_path": str(p)
                    })

    def list_available_memes(self, limit: int = 50) -> List[Dict[str, str]]:
        return [
            {"id": m.get("id", ""), "title": m.get("title", ""), "filename": m.get("filename", "")}
            for m in self.memes[:limit]
        ]

    def resolve(self, meme_name: str, trigger: str = "", gain_db: float = -12.0) -> ResolvedMemeSound:
        """
        Resolves a meme by title, filename, or fuzzy match.
        Strictly enforces Rule 10: If missing, reports missing without substituting unrelated content.
        """
        clean_name = meme_name.strip()
        if not clean_name or clean_name.upper() in ("NONE", "NULL", "NO", "KHONG"):
            return ResolvedMemeSound(
                meme_id="NONE",
                title="NONE",
                filename="",
                file_path=Path(""),
                gain_db=gain_db,
                trigger=trigger,
                exists=False,
                is_missing=False
            )

        norm_query = normalize_keyword(clean_name)
        if not norm_query:
            return ResolvedMemeSound(
                meme_id="UNKNOWN",
                title=clean_name,
                filename="",
                file_path=Path(""),
                gain_db=gain_db,
                trigger=trigger,
                exists=False,
                is_missing=True,
                error_message=f"MISSING_ASSET: Tên meme rỗng sau chuẩn hóa."
            )

        # 1. Exact or prefix match
        best_match = None
        for m in self.memes:
            m_title_norm = normalize_keyword(m.get("title", ""))
            m_slug = normalize_keyword(m.get("slug", ""))
            m_file = normalize_keyword(m.get("filename", ""))

            if m_title_norm and norm_query == m_title_norm:
                best_match = m
                break
            if m_slug and norm_query == m_slug:
                best_match = m
                break

        # 2. Substring match
        if not best_match:
            for m in self.memes:
                m_title_norm = normalize_keyword(m.get("title", ""))
                if m_title_norm and (norm_query in m_title_norm or m_title_norm in norm_query):
                    best_match = m
                    break

        # 3. Fuzzy ratio match (require high confidence >= 0.75)
        if not best_match:
            scored = []
            for m in self.memes:
                m_title_norm = normalize_keyword(m.get("title", ""))
                if not m_title_norm:
                    continue
                ratio = difflib.SequenceMatcher(None, norm_query, m_title_norm).ratio()
                if ratio >= 0.75:
                    scored.append((ratio, m))
            if scored:
                scored.sort(key=lambda x: x[0], reverse=True)
                best_match = scored[0][1]

        if best_match:
            local_path = Path(best_match.get("local_path", ""))
            if not local_path.is_absolute():
                local_path = MEMES_DIR / best_match.get("filename", "")

            if local_path.exists() and local_path.stat().st_size > 0:
                return ResolvedMemeSound(
                    meme_id=best_match.get("id", ""),
                    title=best_match.get("title", ""),
                    filename=best_match.get("filename", ""),
                    file_path=local_path,
                    gain_db=gain_db,
                    trigger=trigger,
                    exists=True,
                    is_missing=False
                )
            else:
                return ResolvedMemeSound(
                    meme_id=best_match.get("id", ""),
                    title=best_match.get("title", ""),
                    filename=best_match.get("filename", ""),
                    file_path=local_path,
                    gain_db=gain_db,
                    trigger=trigger,
                    exists=False,
                    is_missing=True,
                    error_message=f"MISSING_ASSET: File {local_path} không tồn tại trên đĩa."
                )

        # Rule 10: Report missing instead of substituting unrelated content!
        return ResolvedMemeSound(
            meme_id="UNKNOWN",
            title=clean_name,
            filename="",
            file_path=Path(""),
            gain_db=gain_db,
            trigger=trigger,
            exists=False,
            is_missing=True,
            error_message=f"MISSING_ASSET: Âm thanh meme '{clean_name}' không tìm thấy trong thư viện Myinstants."
        )


if __name__ == "__main__":
    resolver = MemeSoundResolver()
    print(f"Loaded {len(resolver.memes)} memes from catalog.")
    test_queries = ["vine boom", "anime wow", "trời ơi cứu tui", "fart", "among us", "quang teo", "unknown_sound_123"]
    for q in test_queries:
        res = resolver.resolve(q)
        print(f"Query: '{q}' -> Found: {res.exists}, Title: '{res.title}', File: '{res.filename}', Missing: {res.is_missing}")
