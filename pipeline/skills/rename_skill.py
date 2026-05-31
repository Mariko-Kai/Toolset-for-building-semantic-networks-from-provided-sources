from __future__ import annotations
import os
import sys
import re
import subprocess
from pathlib import Path
from mathesis.core import MathesisDB
from pipeline.skills.base import BaseEntitySkill

class RenameEntitySkill(BaseEntitySkill):
    """Renames an entity ID, propagating changes cleanly across the SQLite database,
    physical LaTeX/Lean files, inter-file references, and compiles the updated document.
    """

    def execute(self, db: MathesisDB, entity_id: str, *args, **kwargs) -> bool:
        new_id = kwargs.get("new_id")
        if not new_id:
            print("[Error] 'new_id' parameter is required for RenameEntitySkill.")
            return False

        print(f"\n--- [RenameEntitySkill] Renaming '{entity_id}' -> '{new_id}' ---")

        # 1. Lookup entity in database
        entity = db.find_entity(entity_id)
        if not entity:
            print(f"[Error] Entity '{entity_id}' not found in database.")
            return False

        if db.find_entity(new_id):
            print(f"[Error] Destination entity ID '{new_id}' already exists.")
            return False

        project_root = Path(__file__).resolve().parent.parent.parent
        content_dir = project_root / "content"

        # 2. Locate physical LaTeX file
        tex_path = None
        if entity.tex_path:
            p = project_root / entity.tex_path
            if p.exists():
                tex_path = p

        if not tex_path:
            pattern = f"[{entity_id}].tex"
            for dirpath, _, filenames in os.walk(content_dir):
                for fn in filenames:
                    if pattern in fn:
                        tex_path = Path(dirpath) / fn
                        break
                if tex_path:
                    break

        # 3. Locate physical Lean file
        lean_path = None
        if entity.lean_path:
            p = project_root / entity.lean_path
            if p.exists():
                lean_path = p

        if not lean_path:
            p = project_root / "lean_validator" / "Validated" / f"{entity_id}.lean"
            if p.exists():
                lean_path = p

        # 4. Compute new physical filenames
        new_tex_path = None
        if tex_path:
            new_name = tex_path.name.replace(f"[{entity_id}].tex", f"[{new_id}].tex")
            new_tex_path = tex_path.parent / new_name

        new_lean_path = None
        if lean_path:
            new_lean_name = f"{new_id}.lean"
            new_lean_path = lean_path.parent / new_lean_name

        # 5. Database Rename Transaction
        print("[Rename] Updating database records...")
        conn = db.conn
        try:
            # Repoint the primary key and its child rows atomically. `defer_foreign_keys`
            # is transaction-scoped and re-checks at COMMIT — unlike `PRAGMA foreign_keys=OFF`,
            # which is a silent no-op inside an open transaction and would also leave FK
            # enforcement disabled on the (possibly long-lived) connection afterwards.
            if conn.in_transaction:
                conn.commit()
            conn.execute("BEGIN")
            conn.execute("PRAGMA defer_foreign_keys = ON")

            # Fetch and clean equivalence relationships (to prevent check constraints violation on sorting)
            eqs = conn.execute(
                "SELECT entity_a_id, entity_b_id, proof_id FROM equivalence WHERE entity_a_id = ? OR entity_b_id = ?",
                (entity_id, entity_id)
            ).fetchall()

            if eqs:
                conn.execute("DELETE FROM equivalence WHERE entity_a_id = ? OR entity_b_id = ?", (entity_id, entity_id))

            # Update entities table (including relative file paths)
            rel_tex = str(new_tex_path.relative_to(project_root).as_posix()) if new_tex_path else entity.tex_path
            rel_lean = str(new_lean_path.relative_to(project_root).as_posix()) if new_lean_path else entity.lean_path

            conn.execute(
                "UPDATE entities SET entity_id = ?, file_path = ?, lean_path = ?, updated_at = datetime('now') WHERE entity_id = ?",
                (new_id, rel_tex, rel_lean, entity_id)
            )

            # Update related tables
            conn.execute("UPDATE alias SET entity_id = ? WHERE entity_id = ?", (new_id, entity_id))
            conn.execute("UPDATE formulation_sources SET entity_id = ? WHERE entity_id = ?", (new_id, entity_id))

            conn.execute("UPDATE entity_dependency SET source_id = ? WHERE source_id = ?", (new_id, entity_id))
            conn.execute("UPDATE entity_dependency SET target_id = ? WHERE target_id = ?", (new_id, entity_id))

            # Re-insert updated equivalence relationships with canonical sorted order
            for a, b, proof in eqs:
                new_a = new_id if a == entity_id else a
                new_b = new_id if b == entity_id else b
                new_proof = new_id if proof == entity_id else proof

                if new_a > new_b:
                    new_a, new_b = new_b, new_a
                conn.execute(
                    "INSERT OR IGNORE INTO equivalence (entity_a_id, entity_b_id, proof_id) VALUES (?, ?, ?)",
                    (new_a, new_b, new_proof)
                )

            # Update FTS index virtual table
            conn.execute("UPDATE entity_fts SET entity_id = ? WHERE entity_id = ?", (new_id, entity_id))

            conn.commit()  # deferred FK constraints are validated here
            print("[Rename] SQLite transaction committed successfully.")
        except Exception as e:
            conn.rollback()
            print(f"[Error] SQLite transaction failed and was rolled back: {e}")
            return False

        # 6. Physical File Renames and Internal Updates.
        #    NB: full crash-atomicity across DB and filesystem is deferred to Stage F
        #    (orchestrator-owned PatchPlan). Here we at least REFUSE to report success
        #    when a critical file operation fails, so the dispatcher logs an Incident
        #    instead of silently claiming the rename succeeded.
        file_failed = False
        if tex_path and tex_path.exists() and new_tex_path:
            print(f"[Rename] Renaming LaTeX file: {tex_path.name} -> {new_tex_path.name}")
            try:
                # Read old content, update internal tags and hypertargets
                content = tex_path.read_text(encoding='utf-8')
                content = re.sub(rf'% entity-id:\s*{re.escape(entity_id)}', f'% entity-id: {new_id}', content)
                content = content.replace(f"\\hypertarget{{{entity_id}}}", f"\\hypertarget{{{new_id}}}")
                content = content.replace(f"\\label{{entity:{entity_id}}}", f"\\label{{entity:{new_id}}}")

                new_tex_path.write_text(content, encoding='utf-8')
                tex_path.unlink()
            except Exception as e:
                print(f"[Error] Failed to rename/update LaTeX file: {e}")
                file_failed = True

        if lean_path and lean_path.exists() and new_lean_path:
            print(f"[Rename] Renaming Lean file: {lean_path.name} -> {new_lean_path.name}")
            try:
                content = lean_path.read_text(encoding='utf-8')
                # Update occurrences of old_id with new_id in lean source code
                content = content.replace(entity_id, new_id)
                new_lean_path.write_text(content, encoding='utf-8')
                lean_path.unlink()
            except Exception as e:
                print(f"[Error] Failed to rename/update Lean file: {e}")
                file_failed = True

        # 7. Mass-scan and propagate reference updates across ALL .tex and .lean files
        print("[Rename] Mass-propagating references in the content directory...")
        for filepath in content_dir.rglob("*.tex"):
            if filepath.name in ("master.tex", "TEMPLATE.tex", "mathesis.sty"):
                continue
            try:
                text = filepath.read_text(encoding='utf-8')
                # Replace exact references \entityref{old_id} with \entityref{new_id}
                pattern = rf'\\entityref\{{{re.escape(entity_id)}}}'
                if re.search(pattern, text):
                    updated = re.sub(pattern, f"\\\\entityref{{{new_id}}}", text)
                    filepath.write_text(updated, encoding='utf-8')
                    print(f"  Updated references in: {filepath.relative_to(project_root)}")
            except Exception as e:
                print(f"  [Warning] Failed to update reference in '{filepath.name}': {e}")

        print("[Rename] Mass-propagating references in Lean files...")
        lean_dir = project_root / "lean_validator" / "Validated"
        if lean_dir.exists():
            for filepath in lean_dir.rglob("*.lean"):
                try:
                    text = filepath.read_text(encoding='utf-8')
                    if entity_id in text:
                        updated = text.replace(entity_id, new_id)
                        filepath.write_text(updated, encoding='utf-8')
                        print(f"  Updated references in: {filepath.relative_to(project_root)}")
                except Exception as e:
                    print(f"  [Warning] Failed to update reference in Lean file '{filepath.name}': {e}")

        # 8. Rebuild master.tex and compile PDF
        print("[Rename] Rebuilding master index and compiling PDF...")
        try:
            rebuild_script = project_root / "tools" / "rebuild_pdf.py"
            subprocess.run([sys.executable, str(rebuild_script)], check=True, cwd=str(project_root))
            print("[Rename] PDF and master index successfully updated.")
        except Exception as e:
            print(f"[Warning] PDF rebuild command failed: {e}")

        if file_failed:
            print(f"[Error] Rename of '{entity_id}' was committed in the database but a "
                  "critical file operation failed — DB and filesystem may be out of sync. "
                  "Reporting failure so the issue is surfaced as an Incident.")
            return False

        print(f"--- [RenameEntitySkill] Rename of '{entity_id}' -> '{new_id}' finished successfully ---")
        return True
