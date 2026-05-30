"""Mathesis — каноническая база знаний.

Единая сущность `Entity` с осью `kind ∈ {def, prop}` (зеркало Lean).
Транспортные слои (web, CLI) работают только через фасад `MathesisDB`.
"""

from .core import MathesisDB
from .exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    MathesisError,
    MathesisIndexError,
    ParseError,
    ValidationError,
)
from .models import (
    Dependency,
    Entity,
    Equivalence,
    Kind,
    LeanStatus,
    Source,
)

__all__ = [
    "MathesisDB",
    "MathesisError",
    "EntityNotFoundError",
    "DuplicateEntityError",
    "ValidationError",
    "MathesisIndexError",
    "ParseError",
    "Entity",
    "Dependency",
    "Source",
    "Equivalence",
    "Kind",
    "LeanStatus",
]
