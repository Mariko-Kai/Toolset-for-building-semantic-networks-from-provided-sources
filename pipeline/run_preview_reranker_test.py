import json
import sys
from pathlib import Path

# Local test for preview-reranker: monkeypatch query_llm to deterministic heuristic and run preview_scan

repo_root = Path(__file__).resolve().parent.parent
pdf_path = repo_root / "Books" / "Apostol, T.M. - Calculus Vol 1 - (EN) - [1991].pdf"

if not pdf_path.exists():
    print(f"ERROR: PDF not found at {pdf_path}")
    sys.exit(2)

try:
    from pipeline import ensemble_extractor as ee
    from pipeline import export_to_lean as el
except Exception as e:
    print(f"Import error: {e}")
    sys.exit(2)


def mock_query_llm(prompt, model=None, system_prompt=None, json_mode=False, provider=None):
    # Simple heuristic: look for strong markers and count keywords
    try:
        snippet = prompt.split("Page text (first 4000 chars):\n", 1)[1][:800]
    except Exception:
        snippet = prompt[:800]
    s = snippet.lower()
    strong_markers = ["definition", "определен", "определение", "называется", ":="]
    score = 0.0
    if any(m in s for m in strong_markers):
        score = 0.9
    else:
        # weak score by keyword frequency
        cnt = s.count('function') + s.count('derivative') + s.count('deriv') + s.count('limit') + s.count('производн')
        score = min(1.0, 0.2 * cnt)
        if score < 0.05:
            score = 0.05
    found = score >= 0.2
    resp = {"found": found, "confidence": float(score), "reason": "heuristic", "snippet": snippet[:400], "page_ref": 0}
    return json.dumps(resp, ensure_ascii=False)

# Monkeypatch the query_llm used by preview_scan
el.query_llm = mock_query_llm

print(f"Running preview_scan on: {pdf_path.name}")

candidates = ee.preview_scan(pdf_path, query='derivative', preview_provider='mock', preview_model='mock')

if not candidates:
    print("No candidates returned by preview_scan.")
    sys.exit(0)

# candidates is list of (page, score). Print top-10
print('\nTop candidates (page, score):')
for i, (p, s) in enumerate(candidates[:10], start=1):
    print(f"{i}. page {p+1} — score: {s:.3f}")

# Show what ensemble_extractor would pick: pages list
top_pages = [p for p, s in candidates[:10]]
print('\nEnsemble would process these top-10 pages (1-indexed):', [p+1 for p in top_pages])

sys.exit(0)
