"""MathesisDB — the single entry point to the mathesis core.

Wraps all modules (db, queries, validator) into a coherent public API.
Transport layers (web, CLI, desktop) only interact with this class.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from . import db, models, queries, validator
from .exceptions import EntityNotFoundError


class MathesisDB:
    """Facade over the mathesis knowledge base."""

    def __init__(self, db_path: str, content_dir: str = ""):
        self._db_path = db_path
        self._content_dir = Path(content_dir) if content_dir else None
        self._conn: Optional[sqlite3.Connection] = None

    # --- Connection lifecycle ---

    def connect(self) -> None:
        self._conn = db.connect(self._db_path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn

    def init_db(self) -> None:
        db.init_schema(self.conn)

    def reset_db(self) -> None:
        db.reset_db(self.conn)

    # --- CRUD: Objects ---

    def get_object(self, id: str) -> models.Object:
        obj = queries.get_object(self.conn, id)
        if not obj:
            raise EntityNotFoundError("object", id)
        return obj

    def list_objects(self, module: str = None) -> list[models.Object]:
        return queries.list_objects(self.conn, module)

    def create_object(self, obj: models.Object) -> models.Object:
        import json
        self.conn.execute(
            "INSERT INTO object (id, name, aliases, module, "
            "formal_definition, intuition, file_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (obj.id, obj.name, json.dumps(obj.aliases),
             obj.module, obj.formal_definition, obj.intuition, obj.file_path)
        )
        self.conn.commit()
        return obj

    # --- CRUD: Properties ---

    def get_property(self, id: str) -> models.Property:
        prop = queries.get_property(self.conn, id)
        if not prop:
            raise EntityNotFoundError("property", id)
        return prop

    def list_properties(self, module: str = None) -> list[models.Property]:
        return queries.list_properties(self.conn, module)

    def create_property(self, prop: models.Property) -> models.Property:
        import json
        self.conn.execute(
            "INSERT INTO property (id, name, aliases, module, "
            "formal_definition, equivalent_forms, file_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (prop.id, prop.name, json.dumps(prop.aliases),
             prop.module, prop.formal_definition,
             prop.equivalent_forms, prop.file_path)
        )
        self.conn.commit()
        return prop

    # --- CRUD: Operations ---

    def get_operation(self, id: str) -> models.Operation:
        op = queries.get_operation(self.conn, id)
        if not op:
            raise EntityNotFoundError("operation", id)
        return op

    def list_operations(self, module: str = None) -> list[models.Operation]:
        return queries.list_operations(self.conn, module)

    def create_operation(self, op: models.Operation) -> models.Operation:
        import json
        self.conn.execute(
            "INSERT INTO operation (id, name, aliases, module, arity, "
            "formal_definition, codomain_id, file_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (op.id, op.name, json.dumps(op.aliases), op.module,
             op.arity, op.formal_definition, op.codomain_id, op.file_path)
        )
        self.conn.commit()
        return op

    # --- CRUD: Theorems ---

    def get_theorem(self, id: str) -> models.Theorem:
        thm = queries.get_theorem(self.conn, id)
        if not thm:
            raise EntityNotFoundError("theorem", id)
        return thm

    def list_theorems(self, module: str = None,
                      subtype: str = None) -> list[models.Theorem]:
        return queries.list_theorems(self.conn, module, subtype)

    def create_theorem(self, thm: models.Theorem) -> models.Theorem:
        self.conn.execute(
            "INSERT INTO theorem (id, name, subtype, parent_theorem_id, "
            "module, statement, proof, strategy, file_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (thm.id, thm.name, thm.subtype, thm.parent_theorem_id,
             thm.module, thm.statement, thm.proof,
             thm.strategy, thm.file_path)
        )
        self.conn.commit()
        return thm

    # --- CRUD: Axioms ---

    def get_axiom(self, id: str) -> models.Axiom:
        axm = queries.get_axiom(self.conn, id)
        if not axm:
            raise EntityNotFoundError("axiom", id)
        return axm

    def list_axioms(self) -> list[models.Axiom]:
        return queries.list_axioms(self.conn)

    def create_axiom(self, axm: models.Axiom) -> models.Axiom:
        self.conn.execute(
            "INSERT INTO axiom (id, name, system, statement, file_path) "
            "VALUES (?, ?, ?, ?, ?)",
            (axm.id, axm.name, axm.system, axm.statement, axm.file_path)
        )
        self.conn.commit()
        return axm

    # --- Relationships ---

    def get_object_properties(self, object_id: str) -> list[models.ObjectProperty]:
        return queries.get_object_properties(self.conn, object_id)

    def get_operation_arguments(self, op_id: str) -> list[models.OperationArgument]:
        return queries.get_operation_arguments(self.conn, op_id)

    def get_lemmas(self, theorem_id: str) -> list[models.Theorem]:
        return queries.get_lemmas(self.conn, theorem_id)

    def get_dependencies(self, theorem_id: str) -> list[models.Theorem]:
        return queries.get_dependencies(self.conn, theorem_id)

    # --- Backlinks ---

    def get_used_by(self, entity_id: str) -> models.UsedByResult:
        return queries.get_used_by(self.conn, entity_id)

    # --- Graph ---

    def trace_to_axioms(self, theorem_id: str) -> list[models.TraceNode]:
        return queries.trace_to_axioms(self.conn, theorem_id)

    def get_full_dag(self) -> list[models.TheoremDependency]:
        return queries.get_full_dag(self.conn)

    # --- Equivalences & Composition ---

    def get_equivalents(self, object_id: str) -> list[models.Equivalence]:
        return queries.get_equivalents(self.conn, object_id)

    def get_components(self, object_id: str) -> list[models.ObjectComposition]:
        return queries.get_components(self.conn, object_id)

    def get_containers(self, component_id: str) -> list[models.Object]:
        return queries.get_containers(self.conn, component_id)

    # --- Search ---

    def search(self, query: str,
               entity_type: str = None) -> list[models.SearchResult]:
        return queries.search(self.conn, query, entity_type)

    # --- Catalog support ---

    def list_modules(self) -> list[str]:
        return queries.list_modules(self.conn)

    def list_by_module(self, module: str) -> dict:
        return queries.list_by_module(self.conn, module)

    # --- Validation ---

    def validate(self) -> models.ValidationReport:
        return validator.validate(self.conn)

    # --- Junction table helpers ---

    def link_theorem_object(self, theorem_id: str, object_id: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO theorem_object (theorem_id, object_id) "
            "VALUES (?, ?)", (theorem_id, object_id)
        )
        self.conn.commit()

    def link_theorem_property(self, theorem_id: str, property_id: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO theorem_property (theorem_id, property_id) "
            "VALUES (?, ?)", (theorem_id, property_id)
        )
        self.conn.commit()

    def link_theorem_operation(self, theorem_id: str, operation_id: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO theorem_operation (theorem_id, operation_id) "
            "VALUES (?, ?)", (theorem_id, operation_id)
        )
        self.conn.commit()

    def link_theorem_axiom(self, theorem_id: str, axiom_id: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO theorem_axiom (theorem_id, axiom_id) "
            "VALUES (?, ?)", (theorem_id, axiom_id)
        )
        self.conn.commit()

    def link_theorem_dependency(self, theorem_id: str, used_thm_id: str,
                                proof_step: str = "") -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO theorem_dependency "
            "(theorem_id, used_thm_id, proof_step) VALUES (?, ?, ?)",
            (theorem_id, used_thm_id, proof_step)
        )
        self.conn.commit()

    def link_object_property(self, object_id: str, property_id: str,
                             context: str = None,
                             context_ref: str = None) -> None:
        self.conn.execute(
            "INSERT INTO object_property "
            "(object_id, property_id, context, context_ref) VALUES (?, ?, ?, ?)",
            (object_id, property_id, context, context_ref)
        )
        self.conn.commit()

    def add_operation_argument(self, arg: models.OperationArgument) -> None:
        self.conn.execute(
            "INSERT INTO operation_argument "
            "(operation_id, position, object_id, role) VALUES (?, ?, ?, ?)",
            (arg.operation_id, arg.position, arg.object_id, arg.role)
        )
        self.conn.commit()

    def add_equivalence(self, a_id: str, b_id: str,
                        proof_id: str = None) -> None:
        # Enforce canonical order
        if a_id > b_id:
            a_id, b_id = b_id, a_id
        self.conn.execute(
            "INSERT OR IGNORE INTO equivalence "
            "(entity_a_id, entity_b_id, proof_id) VALUES (?, ?, ?)",
            (a_id, b_id, proof_id)
        )
        self.conn.commit()

    def add_composition(self, comp: models.ObjectComposition) -> None:
        self.conn.execute(
            "INSERT INTO object_composition "
            "(container_id, obj_comp_id, prop_comp_id, op_comp_id, role) "
            "VALUES (?, ?, ?, ?, ?)",
            (comp.container_id, comp.obj_comp_id,
             comp.prop_comp_id, comp.op_comp_id, comp.role)
        )
        self.conn.commit()
