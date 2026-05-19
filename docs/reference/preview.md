# Preview LLM — Two-tier search (Preview Model)

This document describes the preview (fast) LLM introduced in the extraction pipeline.

## Purpose

- Provide a fast, low-cost scanning stage over candidate pages identified by PyMuPDF (fitz).
- Detect *introducing* formulations where an entity is explicitly defined/introduced (not mere mentions).
- Reduce the number of pages sent to the main, expensive LLM by filtering only likely pages.

## Defaults

- Default provider: `ollama` (config.py DEFAULTS.preview)
- Default model for ollama preview: `phi4-mini:latest` (config.py _MODULE_MODEL_OVERRIDES.preview)
- CLI flags: `--extract-preview-provider`, `--extract-preview-model`, `--extract-preview-api-key` (override defaults)

## Sampling strategy

1. Collect pages that contain any of the stemmed search roots (from the query).
2. Rank pages by number of matching roots (higher → more relevant).
3. Take top 40 pages by this score, then randomly sample 20 pages from these top 40.
4. If no pages contain roots, sample up to 20 pages uniformly across the document.

Rationale: this produces "almost random" variety while biasing towards highly relevant pages.

## Preview prompt and output

The preview model is instructed to detect *introducing* formulations (i.e., where a concept is explicitly defined or assigned a symbol). The model must return ONLY valid JSON with the following schema:

```
{
  "found": true|false,
  "confidence": 0.0-1.0,
  "reason": "short explanation (e.g. 'heading + phrase called')",
  "snippet": "short text excerpt (<=400 chars)",
  "page_ref": <0-indexed page number>
}
```

Confidence guidelines:
- 1.0 — explicit marker(s) present (heading "Definition", phrase "называется", explicit assignment `X := ...`).
- 0.7 — strong but partial evidence (heading without explicit assignment, or explicit phrase in running text).
- 0.3 — weak / ambiguous indicators.
- 0.0 — not found.

## What preview detects

- Headings like "Определение" / "Definition"
- Introductory phrases: "называется", "будем называть", "определяется как", "обозначим"
- Assignments: `X := ...`, `X - это ...`

## Integration with the pipeline

- The ensemble_extractor builds the candidate set and calls preview_scan() over sampled pages.
- Only pages returned by preview (where `found=true`) are passed to the main extraction LLM for full parsing.
- If preview is disabled (no preview provider/model) or produces no hits, the pipeline falls back to ToC → fulltext search (max 6 pages).

## CLI and config

- Use `pipeline/config.py` to change default preview model/provider.
- CLI flags override config defaults: `--extract-preview-provider`, `--extract-preview-model`, `--extract-preview-api-key`.

## Prompt (concise template)

```
Задача: определить, содержит ли эта страница вводящую формулировку для термина '%s', где сущность непосредственно задаётся.
ИЩИ явные маркеры: заголовки "Определение"/"Definition", вводные фразы "называется", "будем называть", "определяется как", "обозначим", записи вида "X := ..." или конструкции "X - это ...".
Верни ТОЛЬКО корректный JSON: {"found": true, "confidence": 0.0-1.0, "reason": "короткое объяснение", "snippet": "до 400 символов", "page_ref": N}.

Page text (first 4000 chars):
%s
```

Note: the actual implementation uses JSON-mode routing and enforces the response parser to tolerate minor wrapper formatting (code fences) but insists on extracting a valid JSON object.
