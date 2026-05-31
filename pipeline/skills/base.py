from __future__ import annotations
from mathesis.core import MathesisDB

class BaseEntitySkill:
    """Base class for all fast-path entity refactoring/management skills."""

    def execute(self, db: MathesisDB, entity_id: str, *args, **kwargs) -> bool:
        """Executes the specific refactoring or management skill.

        Args:
            db: Facade over the Mathesis database.
            entity_id: The ID of the primary entity on which the action is performed.

        Returns:
            True if the skill executed successfully, False otherwise.
        """
        raise NotImplementedError
