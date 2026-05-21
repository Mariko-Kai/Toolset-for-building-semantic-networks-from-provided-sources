"""Structured pipeline log formatting.

The web transport consumes stdout from several pipeline modules.  This module
keeps that output stable, English-only, and machine-readable.
"""

from __future__ import annotations

import json
import re
from typing import Any


def log_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"))

    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_.:/@+=,-]+", text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def log_event(event: str, **fields: Any) -> str:
    parts = [f"event={event}"]
    parts.extend(f"{key}={log_value(value)}" for key, value in fields.items())
    return " ".join(parts)


def parse_list_literal(value: str) -> Any:
    try:
        parsed = json.loads(value.replace("'", '"'))
    except Exception:
        parsed = None
    if isinstance(parsed, list):
        return parsed
    return value


def normalize_pipeline_log_line(line: str) -> str | None:
    line = line.strip()
    if not line:
        return None

    match = re.match(r"^=== DYNAMIC COMPILER: .*?(\[.*?\])", line)
    if match:
        return log_event(
            "graph_build.started",
            roots=parse_list_literal(match.group(1)),
            traversal="breadth_first",
        )

    match = re.match(r"^===\s+BFS\s+(?:from root|от корня):\s+(.+?)\s+===", line)
    if match:
        return log_event(
            "graph_traversal.root_started",
            root_id=match.group(1),
            traversal="breadth_first",
        )

    match = re.match(r"^Collected\s+(\d+)\s+unique entities\.?$", line)
    if match:
        return log_event("graph_collection.completed", entity_count=int(match.group(1)))

    match = re.match(r"^\[Validation loop\s+(\d+)\]\s+Found missing dependencies to enrich:\s+(.+)$", line)
    if match:
        return log_event(
            "lean_validation.missing_dependencies_detected",
            iteration=int(match.group(1)),
            terms=parse_list_literal(match.group(2)),
        )

    match = re.match(r"^Validation/enrichment loop finished after\s+(\d+)\s+iterations\.$", line)
    if match:
        return log_event("lean_validation.loop_completed", iteration_count=int(match.group(1)))

    match = re.match(r"^\[BFS\]\s+(\S+)\s+->\s+deps:\s+(.+)$", line)
    if match:
        return log_event(
            "dependency_scan.completed",
            entity_id=match.group(1),
            dependency_ids=parse_list_literal(match.group(2)),
        )

    match = re.match(r"^\[MISSING\]\s+(\S+)\s+.+file not found.+", line)
    if match:
        return log_event("entity_file.missing", entity_id=match.group(1), action="start_enrichment")

    match = re.match(r"^\[SKIP\]\s+(\S+)\s+.+--no-enrich", line)
    if match:
        return log_event("entity.skipped", entity_id=match.group(1), reason="file_missing_no_enrich")

    match = re.match(r"^\[SKIP\]\s+(\S+)\s+.+enrichment failed", line)
    if match:
        return log_event("entity.skipped", entity_id=match.group(1), reason="enrichment_failed")

    match = re.match(r"^\[SKIP\]\s+(\S+)\s+.+failed to generate or find", line)
    if match:
        return log_event("entity.skipped", entity_id=match.group(1), reason="entity_unresolved")

    match = re.match(r"^\[ERROR\]\s+Failed to run enrichment pipeline:\s+(.+)$", line)
    if match:
        return log_event("enrichment.failed", error=match.group(1))

    if "AUTO-ENRICHMENT" in line:
        return log_event("enrichment.started")

    match = re.match(r"^\[(\d+)/(\d+)\]\s+(.+)\.\.\.$", line)
    if match:
        step_label = match.group(3).lower()
        if "извлеч" in step_label or "extract" in step_label:
            step_name = "extraction"
        elif "вырав" in step_label or "align" in step_label:
            step_name = "alignment"
        elif "синт" in step_label or "synth" in step_label:
            step_name = "synthesis"
        else:
            step_name = "unknown"
        return log_event(
            "enrichment.step_started",
            step_index=int(match.group(1)),
            step_count=int(match.group(2)),
            step_name=step_name,
        )

    if "Конвейер обогащения завершен успешно" in line:
        return log_event("enrichment.completed", status="success")

    match = re.match(r"^\[\*\]\s+.+\(RU\):\s+'(.+)'$", line)
    if match and ("термин" in line or "Term" in line):
        return log_event("term.detected", language="ru", value_utf8_hex=match.group(1).encode("utf-8").hex())

    match = re.match(r"^\[\*\]\s+.+\(EN\):\s+'(.+)'$", line)
    if match and ("термин" in line or "Term" in line):
        return log_event("term.detected", language="en", value=match.group(1))

    match = re.match(r"^\[\*\]\s+.*(?:Provider|Провайдер):\s*([A-Za-z0-9_.-]+)\s+\(([^)]+)\)", line)
    if match:
        return log_event("provider.selected", provider=match.group(1), model=match.group(2))

    match = re.match(r"^\[\*\]\s+.*(?:Global search|Глобальный поиск):\s+RU='([^']*)',\s+EN='([^']*)'", line)
    if match:
        return log_event(
            "search.query_prepared",
            query_ru_utf8_hex=match.group(1).encode("utf-8").hex(),
            query_en=match.group(2),
        )

    match = re.match(r"^\[Queue\]\s+.+term.+:\s+'(.+)'$", line)
    if match:
        return log_event("queue.synthesis_started", term_utf8_hex=match.group(1).encode("utf-8").hex())

    match = re.match(r"^\[Queue\]\s+Lean.+entity:\s+'([^']+)'", line)
    if match:
        return log_event("lean_validation.started", entity_id=match.group(1))

    if "Конвейер полностью завершил работу" in line:
        return log_event("pipeline.completed", status="success")

    match = re.match(r"^\[\*\]\s+.*result\.pdf.*:\s+(.+)$", line)
    if match:
        return log_event("pdf_build.started", root_ids=match.group(1))

    match = re.match(r"^Generated\s+(.+)$", line)
    if match:
        return log_event("latex_source.generated", path=match.group(1))

    match = re.match(r"^Compiling result\.pdf \(pass\s+(\d+)", line)
    if match:
        return log_event("pdf_compilation.pass_started", pass_index=int(match.group(1)))

    if line == "PDF compilation successful! -> result.pdf":
        return log_event("pdf_compilation.completed", status="success", output_path="result.pdf")

    if line.startswith("PDF compilation issue."):
        return log_event("pdf_compilation.completed", status="failed")

    match = re.match(r"^\[synthesizer\]\s+ParsedDeps:\s+(.+)$", line)
    if match:
        return log_event("synthesizer.dependencies_parsed", payload=parse_list_literal(match.group(1)))

    match = re.match(r"^\[synthesizer\]\s+Parsed:\s+entity_id=([^,\s]+),\s+type=([^,\s]+),\s+title=(.*)$", line)
    if match:
        return log_event(
            "synthesizer.entity_parsed",
            entity_id=match.group(1),
            entity_type=match.group(2),
            title=match.group(3),
        )

    match = re.match(r"^\[synthesizer\]\s+\[OK\]\s+Saved:\s+(.+)$", line)
    if match:
        return log_event("synthesizer.file_saved", path=match.group(1))

    if line.isascii():
        return log_event("process.output", message=line)

    return log_event("process.output", raw_text_utf8_hex=line.encode("utf-8").hex())
