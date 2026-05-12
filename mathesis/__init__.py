"""Mathesis — Mathematical Knowledge Base.

The core package for structuring, querying, and validating
mathematical entities (axioms, objects, properties, operations, theorems).
"""

from .core import MathesisDB
from .exceptions import (
    MathesisError,
    EntityNotFoundError,
    DuplicateEntityError,
    ValidationError,
)

__all__ = [
    "MathesisDB",
    "MathesisError",
    "EntityNotFoundError",
    "DuplicateEntityError",
    "ValidationError",
]
