"""Text generation protocol for structured script understanding and director planning."""
from __future__ import annotations

from typing import Any, Protocol, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class TextProvider(Protocol):
    """Protocol for generating structured data conforming to a Pydantic schema."""

    def generate_structured(
        self,
        schema: Type[T],
        system_instruction: str,
        prompt: str,
        temperature: float = 0.2,
    ) -> T:
        ...
