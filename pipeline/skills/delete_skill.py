from __future__ import annotations
import os
import sys
import subprocess
from pathlib import Path
from mathesis.core import MathesisDB
from pipeline.skills.base import BaseEntitySkill

class DeleteEntitySkill(BaseEntitySkill):
    """Deletes an entity cleanly from both the SQLite database and local filesystem,
    rebuilding the master index and book PDF.
    """

    def execute(self, db: MathesisDB, entity_id: str, *args, **kwargs) -> bool:
        print(f"\n--- [DeleteEntitySkill] Starting deletion for '{entity_id}' ---")

        # 1. Lookup entity in the database
        entity = db.find_entity(entity_id)
        if not entity:
            print(f"[Error] Entity '{entity_id}' not found in database.")
            return False

        project_root = Path(__file__).resolve().parent.parent.parent
        content_dir = project_root / "content"

        # 2. Identify physical LaTeX file path
        tex_path = None
        if entity.tex_path:
            p = project_root / entity.tex_path
            if p.exists():
                tex_path = p

        if not tex_path:
            # Fallback scan content directory for matching filename [entity_id].tex
            pattern = f"[{entity_id}].tex"
            for dirpath, _, filenames in os.walk(content_dir):
                for fn in filenames:
                    if pattern in fn:
                        tex_path = Path(dirpath) / fn
                        break
                if tex_path:
                    break

        # 3. Identify physical Lean file path
        lean_path = None
        if entity.lean_path:
            p = project_root / entity.lean_path
            if p.exists():
                lean_path = p

        if not lean_path:
            p = project_root / "lean_validator" / "Validated" / f"{entity_id}.lean"
            if p.exists():
                lean_path = p

        # 4. Clean delete from SQLite (cascades manually to support legacy/unmigrated databases)
        print(f"[Delete] Removing '{entity_id}' from SQLite database...")
        try:
            db.conn.execute("DELETE FROM entity_dependency WHERE source_id = ? OR target_id = ?", (entity_id, entity_id))
            db.conn.execute("DELETE FROM formulation_sources WHERE entity_id = ?", (entity_id,))
            db.conn.execute("DELETE FROM equivalence WHERE entity_a_id = ? OR entity_b_id = ? OR proof_id = ?", (entity_id, entity_id, entity_id))
            db.conn.execute("DELETE FROM alias WHERE entity_id = ?", (entity_id,))
            db.delete_entity(entity_id)
            db.conn.commit()
        except Exception as db_err:
            db.conn.rollback()
            print(f"[Error] Failed to delete from database: {db_err}")
            return False

        # 5. Prune physical LaTeX file. A failed unlink leaves an orphaned file while the
        #    DB row is already gone, so we surface it as a failure (see contract note below).
        file_failed = False
        if tex_path and tex_path.exists():
            print(f"[Delete] Deleting LaTeX file: {tex_path.relative_to(project_root)}")
            try:
                tex_path.unlink()
            except Exception as e:
                print(f"[Error] Failed to delete LaTeX file '{tex_path}': {e}")
                file_failed = True
        else:
            print("[Delete] No physical LaTeX file found.")

        # 6. Prune physical Lean file
        if lean_path and lean_path.exists():
            print(f"[Delete] Deleting Lean file: {lean_path.relative_to(project_root)}")
            try:
                lean_path.unlink()
            except Exception as e:
                print(f"[Error] Failed to delete Lean file '{lean_path}': {e}")
                file_failed = True
        else:
            print("[Delete] No physical Lean file found.")

        # 7. Rebuild master.tex and compile PDF to keep documents in sync
        print("[Delete] Rebuilding master index and PDF...")
        try:
            rebuild_script = project_root / "tools" / "rebuild_pdf.py"
            subprocess.run([sys.executable, str(rebuild_script)], check=True, cwd=str(project_root))
            print("[Delete] PDF and master index successfully rebuilt.")
        except Exception as e:
            print(f"[Warning] PDF rebuild command failed: {e}")

        if file_failed:
            print(f"[Error] Entity '{entity_id}' was removed from the database but a physical "
                  "file could not be deleted — an orphaned file remains. Reporting failure so "
                  "the issue is surfaced as an Incident.")
            return False

        print(f"--- [DeleteEntitySkill] Clean deletion of '{entity_id}' finished successfully ---")
        return True
