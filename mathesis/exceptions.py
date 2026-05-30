"""Custom exceptions for mathesis."""


class MathesisError(Exception):
    """Base exception for all mathesis errors."""
    pass


class EntityNotFoundError(MathesisError):
    """Raised when an entity with the given ID does not exist."""

    def __init__(self, entity_type: str, entity_id: str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} '{entity_id}' not found")


class DuplicateEntityError(MathesisError):
    """Raised when trying to create an entity with an ID that already exists."""

    def __init__(self, entity_type: str, entity_id: str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} '{entity_id}' already exists")


class ValidationError(MathesisError):
    """Raised when data fails validation (e.g. cyclic DAG, broken refs)."""
    pass


class MathesisIndexError(MathesisError):
    """Raised when indexing .tex files fails.

    Назван MathesisIndexError, чтобы не затенять встроенный IndexError.
    """
    pass


class ParseError(MathesisError):
    """Raised when a .tex file cannot be parsed."""

    def __init__(self, file_path: str, reason: str):
        self.file_path = file_path
        self.reason = reason
        super().__init__(f"Failed to parse '{file_path}': {reason}")
