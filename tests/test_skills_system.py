from __future__ import annotations
import pytest
from pathlib import Path
from mathesis.core import MathesisDB
from mathesis.models import Entity, Source
from pipeline.skills.delete_skill import DeleteEntitySkill
from pipeline.skills.rename_skill import RenameEntitySkill
from pipeline.skills.change_type_skill import ChangeTypeSkill

@pytest.fixture
def setup_test_env(monkeypatch, tmp_path):
    """Sets up a temporary content directory structure and SQLite database for skills testing."""
    # 1. Setup mock content directories
    content_dir = tmp_path / "content"
    defs_dir = content_dir / "defs"
    props_dir = content_dir / "props"

    defs_dir.mkdir(parents=True, exist_ok=True)
    props_dir.mkdir(parents=True, exist_ok=True)

    # Create an empty mathesis.sty and mathesis_macros.sty
    (content_dir / "mathesis.sty").write_text("", encoding="utf-8")
    (content_dir / "mathesis_macros.sty").write_text("", encoding="utf-8")

    # 2. Setup mock LaTeX files
    tex_content = """% defined-in: testbook (page 1)
% entity-id: def-test-foo
% entity-type: def
\\hypertarget{def-test-foo}{}
\\begin{definition}[Test Definition]
This is a test definition.
\\end{definition}
"""
    tex_file = defs_dir / "Test [def-test-foo].tex"
    tex_file.write_text(tex_content, encoding="utf-8")

    tex_referencing = """% defined-in: testbook (page 2)
% entity-id: prop-test-bar
% entity-type: prop
\\hypertarget{prop-test-bar}{}
\\begin{proposition}[Test Property]
This property references \\entityref{def-test-foo}.
\\end{proposition}
"""
    ref_file = props_dir / "Test Bar [prop-test-bar].tex"
    ref_file.write_text(tex_referencing, encoding="utf-8")

    # 3. Setup mock Lean directories and files
    lean_dir = tmp_path / "lean_validator" / "Validated"
    lean_dir.mkdir(parents=True, exist_ok=True)

    lean_file = lean_dir / "def-test-foo.lean"
    lean_file.write_text("def def-test-foo : Prop := True", encoding="utf-8")

    ref_lean_file = lean_dir / "prop-test-bar.lean"
    ref_lean_file.write_text("theorem prop-test-bar : def-test-foo := sorry", encoding="utf-8")

    # Create dummy tools/rebuild_pdf.py in temporary environment
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    (tools_dir / "rebuild_pdf.py").write_text("print('Dummy PDF Rebuild')", encoding="utf-8")

    # 4. Patch paths in Python environment and patch system config
    db_path = tmp_path / "db.sqlite"
    monkeypatch.setenv("MATHESIS_DB_PATH", str(db_path))

    db = MathesisDB(str(db_path))
    db.init_db()

    # 5. Populate SQLite tables
    ent1 = Entity(
        id="def-test-foo",
        kind="def",
        title="Test Definition",
        module="Test Module",
        tex_path=str(tex_file.relative_to(tmp_path)),
        lean_path=str(lean_file.relative_to(tmp_path)),
        aliases=["test-foo-alias"]
    )
    ent2 = Entity(
        id="prop-test-bar",
        kind="prop",
        title="Test Property",
        module="Test Module",
        tex_path=str(ref_file.relative_to(tmp_path)),
        lean_path=str(ref_lean_file.relative_to(tmp_path)),
        aliases=["test-bar-alias"]
    )

    db.upsert_entity(ent1)
    db.upsert_entity(ent2)
    db.add_dependency("prop-test-bar", "def-test-foo", role="uses")
    db.add_source(Source(entity_id="def-test-foo", source_book="testbook", page_info="1"))
    db.add_equivalence("prop-test-bar", "def-test-foo")

    # Mock tools/rebuild_pdf.py call in skills by overriding subprocess.run
    import subprocess
    original_run = subprocess.run

    def mock_run(cmd, *a, **kw):
        if len(cmd) > 1 and "rebuild_pdf.py" in cmd[1]:
            # Simulate rebuilding master.tex
            master_path = content_dir / "master.tex"
            master_path.write_text(f"\\input{{{tex_file.relative_to(tmp_path)}}}", encoding="utf-8")
            return type("CompletedProcess", (), {"returncode": 0, "stdout": "", "stderr": ""})
        return original_run(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "run", mock_run)

    # Patch sys.path / project root paths by monkeypatching Path/os/glob operations if necessary,
    # but the skills resolve paths dynamically via Path(__file__).resolve().parent.parent.parent.
    # To map to our tmp_path correctly, let's patch class files or relative roots.
    # Alternatively, because skills compute project_root relative to pipeline/skills folder,
    # let's monkeypatch Path(__file__) resolution inside skills.

    yield db, tmp_path, tex_file, ref_file, lean_file, ref_lean_file

def test_delete_entity_skill(setup_test_env, monkeypatch):
    db, tmp_path, tex_file, ref_file, lean_file, ref_lean_file = setup_test_env

    # Monkeypatch the project root computed inside DeleteEntitySkill to match tmp_path
    original_resolve = Path.resolve
    def mock_resolve(self):
        if "delete_skill" in str(self):
            return tmp_path / "pipeline" / "skills" / "delete_skill.py"
        return original_resolve(self)
    monkeypatch.setattr(Path, "resolve", mock_resolve)

    # Verify initial database state
    assert db.find_entity("def-test-foo") is not None
    assert tex_file.exists() is True
    assert lean_file.exists() is True

    # Execute Delete skill
    skill = DeleteEntitySkill()
    success = skill.execute(db, "def-test-foo")
    assert success is True

    # Verify entity is deleted from SQLite
    assert db.find_entity("def-test-foo") is None
    # Verify dependencies are cascaded
    assert len(db.get_dependencies("prop-test-bar")) == 0
    assert len(db.get_used_by("def-test-foo").used_by) == 0

    # Verify physical file deletion
    assert tex_file.exists() is False
    assert lean_file.exists() is False
    # Referenced file should still exist
    assert ref_file.exists() is True

def test_rename_entity_skill(setup_test_env, monkeypatch):
    db, tmp_path, tex_file, ref_file, lean_file, ref_lean_file = setup_test_env

    # Monkeypatch project root resolution to target our tmp_path
    original_resolve = Path.resolve
    def mock_resolve(self):
        if "rename_skill" in str(self):
            return tmp_path / "pipeline" / "skills" / "rename_skill.py"
        return original_resolve(self)
    monkeypatch.setattr(Path, "resolve", mock_resolve)

    # Execute Rename skill
    skill = RenameEntitySkill()
    success = skill.execute(db, "def-test-foo", new_id="def-test-renamed")
    assert success is True

    # Verify old entity is removed, new exists
    assert db.find_entity("def-test-foo") is None
    new_ent = db.find_entity("def-test-renamed")
    assert new_ent is not None
    assert new_ent.id == "def-test-renamed"

    # Verify database reference propagation (dependency cascaded updates)
    assert len(db.get_dependencies("prop-test-bar")) == 1
    assert db.get_dependencies("prop-test-bar")[0].id == "def-test-renamed"

    # Verify physical filename renames
    expected_new_tex = tex_file.parent / "Test [def-test-renamed].tex"
    expected_new_lean = lean_file.parent / "def-test-renamed.lean"
    assert expected_new_tex.exists() is True
    assert expected_new_lean.exists() is True
    assert tex_file.exists() is False
    assert lean_file.exists() is False

    # Verify internal LaTeX and Lean tag updates
    tex_content = expected_new_tex.read_text(encoding="utf-8")
    assert "% entity-id: def-test-renamed" in tex_content
    assert "\\hypertarget{def-test-renamed}" in tex_content

    # Verify cross-reference propagation in LaTeX
    ref_tex_content = ref_file.read_text(encoding="utf-8")
    assert "\\entityref{def-test-renamed}" in ref_tex_content
    assert "\\entityref{def-test-foo}" not in ref_tex_content

    # Verify cross-reference propagation in Lean
    ref_lean_content = ref_lean_file.read_text(encoding="utf-8")
    assert "def-test-renamed" in ref_lean_content
    assert "def-test-foo" not in ref_lean_content

def test_change_type_skill(setup_test_env, monkeypatch):
    db, tmp_path, tex_file, ref_file, lean_file, ref_lean_file = setup_test_env

    # Monkeypatch project root resolution to target our tmp_path
    original_resolve = Path.resolve
    def mock_resolve(self):
        if "change_type_skill" in str(self):
            return tmp_path / "pipeline" / "skills" / "change_type_skill.py"
        elif "rename_skill" in str(self):
            return tmp_path / "pipeline" / "skills" / "rename_skill.py"
        return original_resolve(self)
    monkeypatch.setattr(Path, "resolve", mock_resolve)

    # Execute ChangeType skill (def -> prop)
    skill = ChangeTypeSkill()
    success = skill.execute(db, "def-test-foo", new_type="prop")
    assert success is True

    # Note: because ID contains prefix 'def-', ChangeTypeSkill delegates to RenameEntitySkill first,
    # which renames 'def-test-foo' to 'prop-test-foo'.
    assert db.find_entity("def-test-foo") is None
    new_ent = db.find_entity("prop-test-foo")
    assert new_ent is not None
    assert new_ent.kind == "prop"

    # Verify file is relocated to props/ directory
    expected_new_tex = tmp_path / "content" / "props" / "Test [prop-test-foo].tex"
    assert expected_new_tex.exists() is True
    assert tex_file.exists() is False

    # Verify LaTeX tags and environments are changed
    tex_content = expected_new_tex.read_text(encoding="utf-8")
    assert "% entity-type: prop" in tex_content
    assert "\\begin{proposition}" in tex_content
    assert "\\end{proposition}" in tex_content


def test_rename_skill_reports_failure_on_file_error(setup_test_env, monkeypatch):
    """Stage A contract: a critical file operation that fails must make the skill return
    False (so the dispatcher logs an Incident) instead of silently claiming success."""
    db, tmp_path, tex_file, ref_file, lean_file, ref_lean_file = setup_test_env

    original_resolve = Path.resolve
    def mock_resolve(self):
        if "rename_skill" in str(self):
            return tmp_path / "pipeline" / "skills" / "rename_skill.py"
        return original_resolve(self)
    monkeypatch.setattr(Path, "resolve", mock_resolve)

    # Simulate a disk failure when writing the renamed physical files.
    original_write = Path.write_text
    def failing_write(self, *a, **kw):
        if "def-test-renamed" in self.name:
            raise OSError("simulated disk failure")
        return original_write(self, *a, **kw)
    monkeypatch.setattr(Path, "write_text", failing_write)

    skill = RenameEntitySkill()
    success = skill.execute(db, "def-test-foo", new_id="def-test-renamed")

    # Contract: skill must NOT report success when a critical file op failed.
    assert success is False
    # The DB transaction committed before the file step (Stage A surfaces the resulting
    # DB<->FS divergence as a failure; full crash-atomicity is Stage F).
    assert db.find_entity("def-test-renamed") is not None


def test_entity_manager_incident_persists_after_init(tmp_path):
    """Fail-Safe contract (design.md §7.4): a failed refactor must register a structured
    Incident. This only works if the schema (the `incident` table) exists — which main()
    now guarantees via db.init_db(). Without init_db the incident was silently lost."""
    import pipeline.entity_manager as em
    from pipeline.orchestration.store import open_incidents

    db = MathesisDB(str(tmp_path / "db.sqlite"))
    db.connect()
    db.init_db()  # mirrors the guarantee added to entity_manager.main()
    try:
        em.register_incident_on_failure(db, "def-foo", "rename", "broken references: ['x']")
        incidents = open_incidents(db.conn)
        assert len(incidents) == 1
        assert incidents[0]["node"] == "entity_manager.rename"
        assert incidents[0]["status"] == "failed"
    finally:
        db.close()
