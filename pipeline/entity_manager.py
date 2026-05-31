from __future__ import annotations
import sys
import argparse
import subprocess
from pathlib import Path

# Ensure project root is in python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import get_db_path
from mathesis.core import MathesisDB
from pipeline.skills.delete_skill import DeleteEntitySkill
from pipeline.skills.rename_skill import RenameEntitySkill
from pipeline.skills.change_type_skill import ChangeTypeSkill
from pipeline.orchestration.incidents import Incident, PatchPlan
from pipeline.orchestration.store import save_incident

def select_candidate(db: MathesisDB, query: str) -> str | None:
    """Searches FTS index and alias lookup, and lets user select from candidate list."""
    # Try FTS search
    results = db.search(query, limit=10)

    # Try exact alias lookup if FTS has no results
    if not results:
        alias_id = db.lookup_alias(query)
        if alias_id:
            entity = db.find_entity(alias_id)
            if entity:
                return entity.id

        # Check if direct ID search yields anything
        entity = db.find_entity(query)
        if entity:
            return entity.id

        print(f"[-] No entities found matching query '{query}'.")
        return None

    print(f"\n[+] Candidates found matching '{query}':")
    for idx, r in enumerate(results, start=1):
        print(f"  [{idx}] ID: {r.id} | Kind: {r.kind} | Title: {r.title}")
        if r.snippet:
            print(f"      Snippet: {r.snippet}")

    while True:
        choice = input(f"\nSelect a candidate (1-{len(results)}) or 'c' to cancel: ").strip().lower()
        if choice == 'c':
            return None
        try:
            val = int(choice)
            if 1 <= val <= len(results):
                return results[val - 1].id
        except ValueError:
            pass
        print(f"Invalid selection. Please choose a number between 1 and {len(results)}.")

def register_incident_on_failure(db: MathesisDB, entity_id: str, action: str, error_message: str):
    """Registers an Incident and prints out PatchPlan steps for manual review/agentic recovery."""
    print("\n" + "="*60)
    print("!!! [CRITICAL] Refactoring Validation Incident Triggered !!!")
    print("="*60)

    # Log an incident
    incident = Incident(
        run_id=f"refactor-{entity_id}",
        node=f"entity_manager.{action}",
        status="failed",
        severity="error",
        signals=[error_message],
        context={"entity_id": entity_id, "action": action},
        message=f"Refactoring skill '{action}' failed validation checks or generated cycles for '{entity_id}'."
    )

    plan = PatchPlan(
        summary=f"Fix integrity issues/cycles created by '{action}' on '{entity_id}'",
        steps=[
            "1. Inspect compilation logs / pdf compiler output for errors.",
            "2. Identify cyclic dependencies via Tarjan's SCC validation.",
            "3. Manually edit related LaTeX references or SQLite dependency edges to break cycles.",
            "4. Rerun python tools/rebuild_pdf.py to verify build."
        ],
        risk="high",
        auto_applicable=False
    )

    try:
        incident_id = save_incident(db.conn, incident, plan)
        print(f"[Incident Saved] Registered structured DB Incident ID: #{incident_id}")
    except Exception as e:
        print(f"[Warning] Failed to write incident to database: {e}")

    print("\n--- PROPOSED PATCH PLAN ---")
    print(f"Summary: {plan.summary}")
    for step in plan.steps:
        print(f"  * {step}")
    print(f"Risk Level: {plan.risk}")
    print("="*60 + "\n")

def run_interactive(db: MathesisDB):
    """Interactive CLI menu driver."""
    print("==================================================")
    print("Mathesis Refactoring & Entity Manager CLI")
    print("==================================================")

    while True:
        print("\nAvailable Refactoring Operations:")
        print("  1. Rename Entity ID")
        print("  2. Change Entity Type (def <-> prop)")
        print("  3. Delete Entity")
        print("  4. Rebuild PDF Manual Index")
        print("  5. Exit")

        choice = input("\nChoose an option (1-5): ").strip()
        if choice == "5":
            break
        elif choice == "4":
            print("[+] Triggering PDF rebuilder...")
            rebuild_script = PROJECT_ROOT / "tools" / "rebuild_pdf.py"
            subprocess.run([sys.executable, str(rebuild_script)], check=True, cwd=str(PROJECT_ROOT))
            continue
        elif choice not in ("1", "2", "3"):
            print("Invalid choice. Please select 1-5.")
            continue

        query = input("Enter search query or Entity ID to select entity: ").strip()
        if not query:
            print("Query cannot be empty.")
            continue

        entity_id = select_candidate(db, query)
        if not entity_id:
            continue

        if choice == "1":
            new_id = input(f"Enter new ID for '{entity_id}': ").strip()
            if not new_id:
                print("ID cannot be empty.")
                continue
            confirm = input(f"Confirm Rename '{entity_id}' -> '{new_id}'? (y/n): ").strip().lower()
            if confirm == 'y':
                skill = RenameEntitySkill()
                success = skill.execute(db, entity_id, new_id=new_id)
                if success:
                    # Post-refactor integrity validation check
                    report = db.validate()
                    if not report.is_valid:
                        err = f"Rename resulted in broken references: {report.broken_refs} or cycles: {report.cycles}"
                        register_incident_on_failure(db, entity_id, "rename", err)
                else:
                    register_incident_on_failure(db, entity_id, "rename", "Rename execution failed internally.")

        elif choice == "2":
            new_type = input(f"Enter new type for '{entity_id}' (def/prop): ").strip().lower()
            if new_type not in ("def", "prop"):
                print("Type must be 'def' or 'prop'.")
                continue
            confirm = input(f"Confirm Change Type of '{entity_id}' to '{new_type}'? (y/n): ").strip().lower()
            if confirm == 'y':
                skill = ChangeTypeSkill()
                success = skill.execute(db, entity_id, new_type=new_type)
                if success:
                    report = db.validate()
                    if not report.is_valid:
                        err = f"ChangeType resulted in broken references: {report.broken_refs} or cycles: {report.cycles}"
                        register_incident_on_failure(db, entity_id, "change_type", err)
                else:
                    register_incident_on_failure(db, entity_id, "change_type", "ChangeType execution failed internally.")

        elif choice == "3":
            confirm = input(f"Confirm Delete Entity '{entity_id}'? WARNING: This is permanent! (y/n): ").strip().lower()
            if confirm == 'y':
                skill = DeleteEntitySkill()
                success = skill.execute(db, entity_id)
                if success:
                    report = db.validate()
                    if not report.is_valid:
                        err = f"Delete resulted in broken references: {report.broken_refs} or cycles: {report.cycles}"
                        register_incident_on_failure(db, entity_id, "delete", err)
                else:
                    register_incident_on_failure(db, entity_id, "delete", "Delete execution failed internally.")

def main():
    parser = argparse.ArgumentParser(description="Mathesis Entity Refactoring and Management System")
    parser.add_argument("--interactive", action="store_true", help="Launch the interactive CLI wizard")
    parser.add_argument("--action", type=str, choices=("delete", "rename", "change-type"), help="Action to perform")
    parser.add_argument("--id", type=str, help="Primary Entity ID to operate on")
    parser.add_argument("--new-id", type=str, help="New Entity ID for rename action")
    parser.add_argument("--new-type", type=str, choices=("def", "prop"), help="New Entity Type for change-type action")

    args = parser.parse_args()

    db_path = get_db_path()
    db = MathesisDB(db_path)
    db.connect()
    # Ensure the canonical schema (incl. the `incident` table) exists — otherwise the
    # Fail-Safe in register_incident_on_failure() would silently lose the incident.
    db.init_db()

    try:
        if args.interactive or (not args.action and not args.id):
            run_interactive(db)
        else:
            if not args.id:
                parser.error("--id is required for non-interactive execution")

            if args.action == "delete":
                skill = DeleteEntitySkill()
                success = skill.execute(db, args.id)
                if success:
                    report = db.validate()
                    if not report.is_valid:
                        err = f"Delete resulted in broken references: {report.broken_refs} or cycles: {report.cycles}"
                        register_incident_on_failure(db, args.id, "delete", err)
                        sys.exit(1)
                else:
                    register_incident_on_failure(db, args.id, "delete", "Delete execution failed internally.")
                    sys.exit(1)

            elif args.action == "rename":
                if not args.new_id:
                    parser.error("--new-id is required for rename action")
                skill = RenameEntitySkill()
                success = skill.execute(db, args.id, new_id=args.new_id)
                if success:
                    report = db.validate()
                    if not report.is_valid:
                        err = f"Rename resulted in broken references: {report.broken_refs} or cycles: {report.cycles}"
                        register_incident_on_failure(db, args.id, "rename", err)
                        sys.exit(1)
                else:
                    register_incident_on_failure(db, args.id, "rename", "Rename execution failed internally.")
                    sys.exit(1)

            elif args.action == "change-type":
                if not args.new_type:
                    parser.error("--new-type is required for change-type action")
                skill = ChangeTypeSkill()
                success = skill.execute(db, args.id, new_type=args.new_type)
                if success:
                    report = db.validate()
                    if not report.is_valid:
                        err = f"ChangeType resulted in broken references: {report.broken_refs} or cycles: {report.cycles}"
                        register_incident_on_failure(db, args.id, "change-type", err)
                        sys.exit(1)
                else:
                    register_incident_on_failure(db, args.id, "change-type", "ChangeType execution failed internally.")
                    sys.exit(1)

    finally:
        db.close()

if __name__ == "__main__":
    main()
