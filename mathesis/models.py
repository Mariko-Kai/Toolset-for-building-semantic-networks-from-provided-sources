"""Data models for mathesis entities.

All models are plain dataclasses — no ORM dependency.
Core module uses these for input/output; transports serialize them as needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Core entity models
# ---------------------------------------------------------------------------

@dataclass
class Axiom:
    id: str
    name: str
    system: str                     # 'ZFC' | 'FOL' | 'Tool'
    statement: str                  # LaTeX
    file_path: str = ""


@dataclass
class Object:
    id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    module: str = ""
    formal_definition: str = ""     # LaTeX
    intuition: str = ""             # LaTeX
    file_path: str = ""


@dataclass
class Property:
    id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    module: str = ""
    formal_definition: str = ""     # LaTeX
    equivalent_forms: str = ""      # LaTeX, optional
    file_path: str = ""


@dataclass
class Operation:
    id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    module: str = ""
    arity: int = 1
    formal_definition: str = ""     # LaTeX
    codomain_id: Optional[str] = None
    file_path: str = ""


@dataclass
class OperationArgument:
    operation_id: str
    position: int
    object_id: str
    role: str = "operand"           # 'operand' | 'parameter'


@dataclass
class Theorem:
    id: str
    name: str
    subtype: str = "theorem"        # 'theorem' | 'lemma'
    parent_theorem_id: Optional[str] = None
    module: str = ""
    statement: str = ""             # LaTeX
    proof: str = ""                 # LaTeX
    strategy: str = ""              # proof method summary
    file_path: str = ""


# ---------------------------------------------------------------------------
# Relationship / junction models
# ---------------------------------------------------------------------------

@dataclass
class ObjectProperty:
    """M:N link between Object and Property, with optional context."""
    id: Optional[int] = None        # surrogate PK
    object_id: str = ""
    property_id: str = ""
    context: Optional[str] = None   # LaTeX, e.g. "на $(0,1)$"
    context_ref: Optional[str] = None  # FK → object.id


@dataclass
class TheoremDependency:
    """Logical DAG edge: theorem uses another theorem in its proof."""
    theorem_id: str = ""
    used_thm_id: str = ""
    proof_step: str = ""            # e.g. "Step 3"


@dataclass
class Equivalence:
    """Symmetric equivalence between two entities."""
    entity_a_id: str = ""
    entity_b_id: str = ""
    proof_id: Optional[str] = None  # FK → theorem.id


@dataclass
class ObjectComposition:
    """Container object (space) is composed of components."""
    container_id: str = ""
    obj_comp_id: Optional[str] = None
    prop_comp_id: Optional[str] = None
    op_comp_id: Optional[str] = None
    role: str = ""                  # 'base_set' | 'structure' | 'axiom'

    @property
    def component_id(self) -> str:
        return self.obj_comp_id or self.prop_comp_id or self.op_comp_id or ""

    @property
    def component_type(self) -> str:
        if self.obj_comp_id:
            return "object"
        if self.prop_comp_id:
            return "property"
        if self.op_comp_id:
            return "operation"
        return ""


# ---------------------------------------------------------------------------
# Aggregate / result models
# ---------------------------------------------------------------------------

@dataclass
class TraceNode:
    """A node in the axiom-trace tree."""
    id: str
    name: str
    subtype: str = "theorem"
    depth: int = 0
    axiom_ids: list[str] = field(default_factory=list)


@dataclass
class UsedByResult:
    """Backlinks: which entities reference a given entity."""
    entity_id: str = ""
    theorems: list[Theorem] = field(default_factory=list)
    objects: list[Object] = field(default_factory=list)
    properties: list[Property] = field(default_factory=list)
    operations: list[Operation] = field(default_factory=list)


@dataclass
class SearchResult:
    id: str
    name: str
    entity_type: str                # 'object' | 'property' | 'operation' | 'theorem' | 'axiom'
    snippet: str = ""               # FTS match snippet


@dataclass
class IndexReport:
    """Result of a reindex operation."""
    objects: int = 0
    properties: int = 0
    operations: int = 0
    theorems: int = 0
    axioms: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Result of a validation pass."""
    is_valid: bool = True
    broken_refs: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    orphan_lemmas: list[str] = field(default_factory=list)
