import sqlite3
import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db/mathesis_index.db"
LEAN_DIR = PROJECT_ROOT / "lean_validator"
VALIDATED_DIR = LEAN_DIR / "Validated"

# Map foundational entities to Mathlib abstractions or aliases
MATHLIB_AXIOMS = {
    "def-set": "abbrev def_set := Set",
    "def-real-numbers": "abbrev def_real_numbers := Real",
    "def-natural-numbers": "abbrev def_natural_numbers := Nat",
    "def-integer-numbers": "abbrev def_integer_numbers := Int",
    "def-complex-numbers": "abbrev def_complex_numbers := Complex",
    "def-zfc-extensionality": "-- ZFC Extensionality axiom is implicit in Lean Prop"
}

class LeanTreeBuilder:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    def _get_dependencies_from_db(self, entity_id: str) -> list[str]:
        if not self.db_path.exists():
            return []
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT target_id FROM entity_dependency WHERE source_id = ?", (entity_id,))
            deps = [row[0] for row in cursor.fetchall()]
            conn.close()
            return deps
        except sqlite3.OperationalError:
            return []

    def _load_or_generate_lean_code(self, entity_id: str) -> str:
        if entity_id in MATHLIB_AXIOMS:
            return MATHLIB_AXIOMS[entity_id]

        validated_path = VALIDATED_DIR / f"{entity_id}.lean"
        if validated_path.exists():
            return validated_path.read_text(encoding='utf-8')

        # Needs generation
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT type, file_path FROM entities WHERE entity_id = ?", (entity_id,))
        row = cursor.fetchone()
        conn.close()

        if not row or not row[1]:
            return f"-- Warning: Entity {entity_id} not found in DB or missing file_path."

        entity_type, file_path = row
        abs_file_path = PROJECT_ROOT / file_path
        if not abs_file_path.exists():
             return f"-- Warning: File {abs_file_path} not found."

        tex_content = abs_file_path.read_text(encoding='utf-8')
        content_no_proofs = re.sub(r'\\begin\{proof\}.*?\\end\{proof\}', '', tex_content, flags=re.DOTALL)
        
        print(f"[LeanTreeBuilder] Recursively generating Lean code for missing dependency: {entity_id} ...")
        from pipeline.export_to_lean import attempt_generation_with_repair
        lean_code, is_valid = attempt_generation_with_repair(entity_id, entity_type, content_no_proofs)
        
        if lean_code and is_valid:
            validated_path.parent.mkdir(parents=True, exist_ok=True)
            validated_path.write_text(lean_code, encoding='utf-8')
            return lean_code
        else:
            return f"-- Failed to recursively generate valid Lean code for {entity_id}\n" + (lean_code or "")

    def build_closure_order(self, target_id: str, extra_deps: list[str] = None) -> list[str]:
        """
        Строит топологически корректный плоский список ID сущностей.
        Единый алгоритм и для Lean, и для сборки master.tex.
        """
        order = []
        visited = set()
        visited_currently = set()

        def dfs(v: str):
            if v in visited_currently:
                print(f"[LeanTreeBuilder] CRITICAL: Cycle detected at {v}!")
                return
            if v not in visited:
                visited_currently.add(v)
                
                # Fetch deps: if it's the root target_id, we inject extra_deps
                deps = self._get_dependencies_from_db(v)
                if v == target_id and extra_deps:
                    deps = list(set(deps + extra_deps))
                    
                for dep in deps:
                    dfs(dep)
                    
                visited_currently.remove(v)
                visited.add(v)
                order.append(v)

        # For LaTeX master build, we might pass a list of target_ids or a virtual root node.
        # Handling multiple roots if target_id is a list
        if isinstance(target_id, list):
            for t in target_id:
                dfs(t)
        else:
            dfs(target_id)
            
        return order

    def generate_lean_tree_file(self, target_id: str, output_path: str, target_code: str = None, target_deps: list[str] = None) -> bool:
        compilation_order = self.build_closure_order(target_id, target_deps)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as tree_file:
                tree_file.write("-- --- MATHESIS AUTOMATICALLY GENERATED LEANTREE ENVIRONMENT ---\n")
                tree_file.write("import Mathlib\n\n") 
                
                for entity_id in compilation_order:
                    tree_file.write(f"-- Start of entity: {entity_id}\n")
                    
                    if entity_id == target_id and target_code is not None:
                        code_snippet = target_code
                    else:
                        code_snippet = self._load_or_generate_lean_code(entity_id)
                    
                    clean_code = "\n".join([line for line in code_snippet.splitlines() if not line.strip().startswith("import ")])
                    
                    tree_file.write(clean_code)
                    tree_file.write(f"\n\n-- End of entity: {entity_id}\n\n")
            
            print(f"[LeanTreeBuilder] SUCCESS: Среда компиляции для {target_id} успешно материализована в {output_path}")
            return True
        except Exception as e:
            print(f"[LeanTreeBuilder] ERROR: {e}")
            return False
