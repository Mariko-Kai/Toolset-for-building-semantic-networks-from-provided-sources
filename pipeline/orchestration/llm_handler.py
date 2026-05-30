"""Агентный обработчик инцидентов на LLM (ТЗ Этап 5.6).

Реализация `IncidentHandler`, которая поручает LLM: расследование (root-cause,
код-ревью) и составление плана патча. Промпты вынесены в pipeline/prompts (Этап
4.3). Патч ВСЕГДА `auto_applicable=False` — применение только после явного
подтверждения человека (gate в оркестраторе) и через git+тесты.

LLM-вызов инъектируется (`query_fn`) — для тестов и для выбора провайдера.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from pipeline.orchestration.incidents import Incident, Investigation, PatchPlan


def _extract_json(text: str) -> dict:
    """Достаёт первый JSON-объект из ответа LLM; {} при неудаче (без падения)."""
    if not text:
        return {}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


class LLMIncidentHandler:
    """Расследует инцидент и предлагает план патча средствами LLM."""

    def __init__(self, query_fn: Optional[Callable[[str], str]] = None, role: str = "synth"):
        self._query = query_fn
        self.role = role

    def _ask(self, prompt: str) -> str:
        if self._query is not None:
            return self._query(prompt)
        from pipeline.model_manager import ModelManager
        return ModelManager.get_instance().query_llm(prompt, json_mode=True, role=self.role)

    def investigate(self, incident: Incident) -> Investigation:
        from pipeline.prompts import load_prompt
        prompt = load_prompt(
            "incident_investigate",
            node=incident.node, status=incident.status, message=incident.message,
            signals=", ".join(incident.signals) or "none",
            context=json.dumps(incident.context, ensure_ascii=False),
        )
        data = _extract_json(self._ask(prompt))
        return Investigation(
            incident=incident,
            root_cause=data.get("root_cause", "(LLM не вернул root_cause)"),
            findings=list(data.get("findings", [])),
            reviewed_files=list(data.get("reviewed_files", [])),
        )

    def propose_patch(self, investigation: Investigation) -> PatchPlan:
        from pipeline.prompts import load_prompt
        prompt = load_prompt(
            "incident_patch",
            root_cause=investigation.root_cause,
            findings=json.dumps(investigation.findings, ensure_ascii=False),
        )
        data = _extract_json(self._ask(prompt))
        return PatchPlan(
            summary=data.get("summary", "(LLM не вернул summary)"),
            steps=list(data.get("steps", [])),
            files=list(data.get("files", [])),
            tests=list(data.get("tests", [])),
            risk=data.get("risk", "unknown"),
            auto_applicable=False,   # ВСЕГДА требует подтверждения человека
        )
