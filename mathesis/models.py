"""Типизированные модели канонической схемы Mathesis (ТЗ Этап 2.2).

Спина модели — единая сущность `Entity` с осью `kind ∈ {def, prop}` (зеркало
Lean). Прежняя ветвистая таксономия (object/property/operation/theorem/axiom)
свёрнута в `kind` + типизированные рёбра `Dependency`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Kind(str, Enum):
    """Ось знаний = ось Lean. Только два значения; axiom — НЕ отдельный вид."""
    DEF = "def"
    PROP = "prop"


class LeanStatus(str, Enum):
    UNVALIDATED = "unvalidated"
    VALID = "valid"
    SORRY = "sorry"      # компилируется, но доказательство = sorry
    FAILED = "failed"


class LeanDecl(str, Enum):
    """Форма Lean-декларации. 'axiom' допустим (постулируется без доказательства)."""
    DEF = "def"
    ABBREV = "abbrev"
    STRUCTURE = "structure"
    CLASS = "class"
    INSTANCE = "instance"
    THEOREM = "theorem"
    LEMMA = "lemma"
    AXIOM = "axiom"


class DepRole(str, Enum):
    USES = "uses"
    GENERALIZES = "generalizes"
    INSTANCE_OF = "instance_of"
    PROOF_USES = "proof_uses"
    COMPONENT = "component"


@dataclass
class Entity:
    """Каноническая сущность графа знаний."""
    id: str
    kind: str                       # 'def' | 'prop'
    title: str
    module: str = ""
    nl_desc: str = ""
    latex: str = ""                 # канонический формальный LaTeX
    lean_code: str = ""
    lean_decl: str = ""             # форма Lean-декларации (вкл. 'axiom')
    lean_status: str = "unvalidated"
    tex_path: str = ""              # относительный путь .tex (колонка file_path)
    lean_path: str = ""
    path: str = ""                  # легаси: директория .tex
    aliases: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_axiomatic(self) -> bool:
        """Постулируется без доказательства (Lean-декларация axiom)."""
        return self.lean_decl == "axiom"


@dataclass
class Dependency:
    """Типизированное ребро графа: source зависит от target."""
    source_id: str
    target_id: str
    role: str = "uses"
    proof_step: str = ""


@dataclass
class Source:
    """Провенанс: откуда извлечена сущность."""
    entity_id: str
    source_book: str
    page_info: str = ""
    id: Optional[int] = None


@dataclass
class Equivalence:
    entity_a_id: str
    entity_b_id: str
    proof_id: Optional[str] = None


@dataclass
class TraceNode:
    """Узел трассировки к корням (аксиоматичным сущностям или листьям DAG)."""
    id: str
    title: str
    kind: str = "prop"
    depth: int = 0
    is_root: bool = False


@dataclass
class SearchResult:
    id: str
    title: str
    kind: str                       # 'def' | 'prop'
    snippet: str = ""


@dataclass
class UsedByResult:
    """Обратные ссылки: какие сущности зависят от данной."""
    entity_id: str = ""
    used_by: list[Entity] = field(default_factory=list)


@dataclass
class ValidationReport:
    is_valid: bool = True
    broken_refs: list[str] = field(default_factory=list)   # рёбра на несуществующие id
    cycles: list[list[str]] = field(default_factory=list)  # циклы в графе
    unproven: list[str] = field(default_factory=list)      # lean_status sorry/failed
