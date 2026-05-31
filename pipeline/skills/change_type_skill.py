from __future__ import annotations
import os
import sys
import re
import subprocess
from pathlib import Path
from mathesis.core import MathesisDB
from pipeline.skills.base import BaseEntitySkill
from pipeline.skills.rename_skill import RenameEntitySkill

class ChangeTypeSkill(BaseEntitySkill):
    """Changes the entity type between 'def' and 'prop' inside database, updates LaTeX formatting,
    relocates the physical .tex files between defs/ and props/ directories, and updates references.
    """

    def execute(self, db: MathesisDB, entity_id: str, *args, **kwargs) -> bool:
        new_type = kwargs.get("new_type")
        if not new_type or new_type not in ("def", "prop"):
            print("[Error] 'new_type' parameter ('def' or 'prop') is required for ChangeTypeSkill.")
            return False

        print(f"\n--- [ChangeTypeSkill] Changing type for '{entity_id}' to '{new_type}' ---")

        # 1. Lookup entity in database
        entity = db.find_entity(entity_id)
        if not entity:
            print(f"[Error] Entity '{entity_id}' not found in database.")
            return False

        if entity.kind == new_type:
            print(f"[Info] Entity '{entity_id}' is already of type '{new_type}'.")
            return True

        project_root = Path(__file__).resolve().parent.parent.parent
        content_dir = project_root / "content"

        # 2. Check and prompt for ID prefix rename to keep naming consistent (e.g. def-foo -> prop-foo)
        current_id = entity_id
        if current_id.startswith("def-") and new_type == "prop":
            target_id = current_id.replace("def-", "prop-", 1)
            print(f"[ChangeType] Requesting prefix rename: '{current_id}' -> '{target_id}' to match type '{new_type}'...")
            renamer = RenameEntitySkill()
            if renamer.execute(db, current_id, new_id=target_id):
                current_id = target_id
            else:
                print("[Warning] Prefix rename failed. Continuing with original ID.")
        elif (current_id.startswith("prop-") or current_id.startswith("thm-")) and new_type == "def":
            prefix = "prop-" if current_id.startswith("prop-") else "thm-"
            target_id = current_id.replace(prefix, "def-", 1)
            print(f"[ChangeType] Requesting prefix rename: '{current_id}' -> '{target_id}' to match type '{new_type}'...")
            renamer = RenameEntitySkill()
            if renamer.execute(db, current_id, new_id=target_id):
                current_id = target_id
            else:
                print("[Warning] Prefix rename failed. Continuing with original ID.")

        # Re-fetch entity after potential rename (find_entity returns None instead of
        # raising, so a partial prefix-rename surfaces as a clean failure, not an
        # uncaught exception out of the dispatcher).
        entity = db.find_entity(current_id)
        if not entity:
            print(f"[Error] Entity '{current_id}' not found after prefix rename; aborting.")
            return False

        # 3. Locate physical LaTeX file
        tex_path = None
        if entity.tex_path:
            p = project_root / entity.tex_path
            if p.exists():
                tex_path = p

        if not tex_path:
            pattern = f"[{current_id}].tex"
            for dirpath, _, filenames in os.walk(content_dir):
                for fn in filenames:
                    if pattern in fn:
                        tex_path = Path(dirpath) / fn
                        break
                if tex_path:
                    break

        # 4. Relocate LaTeX file and adjust content formatting
        new_tex_path = None
        if tex_path and tex_path.exists():
            target_subdir = "defs" if new_type == "def" else "props"
            dest_dir = content_dir / target_subdir
            dest_dir.mkdir(parents=True, exist_ok=True)
            new_tex_path = dest_dir / tex_path.name

            print(f"[ChangeType] Relocating file: {tex_path.relative_to(project_root)} -> {new_tex_path.relative_to(project_root)}")

            try:
                # Read, format content, update metadata tags and LaTeX block environments
                content = tex_path.read_text(encoding='utf-8')

                # Update comment meta tag
                content = re.sub(r'% entity-type:\s*(def|prop)', f'% entity-type: {new_type}', content)

                # Update \begin{...} and \end{...} environments
                if new_type == "def":
                    content = content.replace("\\begin{proposition}", "\\begin{definition}")
                    content = content.replace("\\end{proposition}", "\\end{definition}")
                    content = content.replace("\\begin{theorem}", "\\begin{definition}")
                    content = content.replace("\\end{theorem}", "\\end{definition}")
                else:
                    content = content.replace("\\begin{definition}", "\\begin{proposition}")
                    content = content.replace("\\end{definition}", "\\end{proposition}")

                new_tex_path.write_text(content, encoding='utf-8')
                if new_tex_path != tex_path:
                    tex_path.unlink()
            except Exception as e:
                print(f"[Error] Failed to relocate or update LaTeX file: {e}")
                return False

        # 5. Database Update
        print(f"[ChangeType] Updating SQLite records for '{current_id}' to type '{new_type}'...")
        conn = db.conn
        try:
            rel_tex = str(new_tex_path.relative_to(project_root).as_posix()) if new_tex_path else entity.tex_path

            conn.execute(
                "UPDATE entities SET type = ?, file_path = ?, updated_at = datetime('now') WHERE entity_id = ?",
                (new_type, rel_tex, current_id)
            )
            conn.execute("UPDATE entity_fts SET type = ? WHERE entity_id = ?", (new_type, current_id))
            conn.commit()
            print("[ChangeType] Database type change committed successfully.")
        except Exception as e:
            conn.rollback()
            print(f"[Error] SQLite update failed: {e}")
            return False

        # 6. Rebuild master.tex and compile PDF
        print("[ChangeType] Rebuilding master index and PDF...")
        try:
            rebuild_script = project_root / "tools" / "rebuild_pdf.py"
            subprocess.run([sys.executable, str(rebuild_script)], check=True, cwd=str(project_root))
            print("[ChangeType] PDF and master index successfully updated.")
        except Exception as e:
            print(f"[Warning] PDF rebuild command failed: {e}")

        print(f"--- [ChangeTypeSkill] Change type of '{current_id}' finished successfully ---")
        return True
