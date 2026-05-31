"""Тесты оркестрируемого драйвера обогащения (ТЗ: основной драйвер)."""
from __future__ import annotations

import sys
import types

sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline import enrichment_coordinator as ow  # noqa: E402
from pipeline.orchestration import load_run  # noqa: E402


def _runner_synth_ok(cmd, env, on_line, timeout):
    if cmd == ["synth"]:
        on_line("[synthesizer] Parsed: entity_id=def-limit, type=def")
        on_line('[synthesizer] ParsedDeps: {"entity_id": "def-limit", "deps": ["def-set"]}')
    return 0


def _runner_synth_empty(cmd, env, on_line, timeout):
    return 0  # синтез ничего не выдал


def test_orchestrated_success_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("MATHESIS_DB_PATH", str(tmp_path / "db.sqlite"))
    ok, entities, deps = ow.run_enrichment_orchestrated(
        ["extract"], ["align"], ["synth"], canonical_term="limit",
        run_id="t-ok", runner=_runner_synth_ok,
    )
    assert ok is True
    assert entities == ["def-limit"]
    assert deps == {"def-limit": ["def-set"]}

    from mathesis import db as mdb
    conn = mdb.connect(str(tmp_path / "db.sqlite"))
    try:
        loaded = load_run(conn, "t-ok")
    finally:
        conn.close()
    assert loaded["status"] == "completed"
    assert loaded["health"]["nodes_total"] == 3


def test_orchestrated_deviation_creates_incident(monkeypatch, tmp_path):
    monkeypatch.setenv("MATHESIS_DB_PATH", str(tmp_path / "db.sqlite"))
    ok, entities, deps = ow.run_enrichment_orchestrated(
        ["extract"], ["align"], ["synth"], canonical_term="limit",
        run_id="t-dev", runner=_runner_synth_empty,
    )
    assert ok is False                  # синтез без сущностей -> не completed
    from mathesis import db as mdb
    conn = mdb.connect(str(tmp_path / "db.sqlite"))
    try:
        loaded = load_run(conn, "t-dev")
    finally:
        conn.close()
    assert loaded["status"] == "paused"
    assert len(loaded["incidents"]) == 1
    assert loaded["incidents"][0]["node"] == "synth"


def test_build_enrichment_commands_shapes():
    ex, al, sy, env = ow._build_enrichment_commands(
        "предел", "limit", synth_provider="groq", no_validate=True, canonical_term="limit")
    assert "limit" in ex[2] and "предел" in ex[2]      # "term_ru|term_en"
    assert "--no-validate" in sy
    assert "--synth-provider" in sy and "groq" in sy
    assert env["PYTHONIOENCODING"] == "utf-8"
