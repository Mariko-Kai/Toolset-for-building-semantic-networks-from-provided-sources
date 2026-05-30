"""Data-driven реестры доменной логики (ТЗ Этап 4.2)."""
from .entity_types import PROP_KEYWORDS, clear_detectors, detect_entity_type, register_detector
from .lean_hints import DEFAULT_RULES, HintRule, hints_for_error

__all__ = [
    "detect_entity_type",
    "register_detector",
    "clear_detectors",
    "PROP_KEYWORDS",
    "hints_for_error",
    "HintRule",
    "DEFAULT_RULES",
]
