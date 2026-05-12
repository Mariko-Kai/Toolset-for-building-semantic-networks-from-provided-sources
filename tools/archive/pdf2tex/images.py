"""images.py -- Detect and crop figures from page images using Gemini API.

Instead of extracting embedded images from the PDF (which catches logos,
decorative elements, etc.), this module asks Gemini to identify actual
figures, diagrams, and graphs on the page, then crops them from the
rendered page image using Pillow.
"""

import json
import re
import sys
from pathlib import Path


FIGURE_DETECTION_PROMPT = r"""Analyze this textbook page image. Identify ALL actual figures, diagrams, graphs, charts, or illustrations on the page.

IMPORTANT DISTINCTIONS:
- INCLUDE: mathematical graphs, geometric diagrams, plots, charts, illustrations, photographs, schematic drawings
- EXCLUDE: decorative text, fancy typography, mathematical formulas, tables, numbered lists, section headers

If there are NO figures on the page, respond with exactly: []

If there ARE figures, respond with a JSON array. Each element must have:
- "id": sequential number starting from 1
- "description": brief description of the figure (in English)
- "bbox": [x_min, y_min, x_max, y_max] as fractions of image dimensions (0.0 to 1.0)
  - x_min: left edge fraction
  - y_min: top edge fraction
  - x_max: right edge fraction
  - y_max: bottom edge fraction

Example response for a page with one graph:
[{"id": 1, "description": "Graph of f(x) = x^2", "bbox": [0.15, 0.45, 0.85, 0.80]}]

Respond with ONLY the JSON array, no other text.
"""


def detect_figures(
    image_path: Path,
    api_key: str,
    *,
    model: str = "gemini-2.0-flash",
    dry_run: bool = False,
) -> list[dict]:
    """Ask Gemini to identify figures on a page image.

    Args:
        image_path: Path to the rendered page PNG.
        api_key: Gemini API key.
        model: Gemini model name.

    Returns:
        List of dicts with 'id', 'description', 'bbox' keys.
        Empty list if no figures found.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("ERROR: google-genai not installed. Run: pip install google-genai")
        sys.exit(1)

    if not image_path.exists():
        return []

    if dry_run:
        return []

    img_data = image_path.read_bytes()
    ext = image_path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(ext, "image/png")

    client = genai.Client(api_key=api_key)

    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=img_data, mime_type=mime),
                        types.Part.from_text(text=FIGURE_DETECTION_PROMPT),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2048,
            ),
        )
    except Exception as e:
        print(f"  [WARN] Figure detection API error: {e}")
        return []

    text = response.text.strip()

    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, count=1)
    text = re.sub(r"\n?```\s*$", "", text, count=1)
    text = text.strip()

    if not text or text == "[]":
        return []

    try:
        figures = json.loads(text)
        if not isinstance(figures, list):
            return []
        # Validate each figure has required fields
        valid = []
        for fig in figures:
            if (
                isinstance(fig, dict)
                and "bbox" in fig
                and isinstance(fig["bbox"], list)
                and len(fig["bbox"]) == 4
            ):
                valid.append(fig)
        return valid
    except json.JSONDecodeError:
        print(f"  [WARN] Could not parse figure detection response: {text[:200]}")
        return []


def crop_figures(
    image_path: Path,
    figures: list[dict],
    output_dir: Path,
    page_num: int,
    *,
    padding: float = 0.02,
) -> list[dict]:
    """Crop detected figures from the page image using Pillow.

    Args:
        image_path: Path to the full page image.
        figures: List of figure dicts from detect_figures().
        output_dir: Directory to save cropped images.
        page_num: Page number for filename.
        padding: Extra padding around the crop box (fraction of image).

    Returns:
        List of dicts with 'path', 'filename', 'description', 'width', 'height'.
    """
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow not installed. Run: pip install Pillow")
        sys.exit(1)

    if not figures:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(image_path)
    img_w, img_h = img.size
    results = []

    for fig in figures:
        fig_id = fig.get("id", len(results) + 1)
        desc = fig.get("description", "")
        bbox = fig["bbox"]

        # Convert fractional coords to pixels, with padding
        x_min = max(0, bbox[0] - padding) * img_w
        y_min = max(0, bbox[1] - padding) * img_h
        x_max = min(1, bbox[2] + padding) * img_w
        y_max = min(1, bbox[3] + padding) * img_h

        # Sanity check
        if x_max <= x_min or y_max <= y_min:
            print(f"  [WARN] Invalid bbox for figure {fig_id}, skipping")
            continue

        cropped = img.crop((int(x_min), int(y_min), int(x_max), int(y_max)))

        filename = f"page_{page_num:03d}_fig_{fig_id}.png"
        out_path = output_dir / filename
        cropped.save(out_path, "PNG")

        results.append({
            "path": out_path,
            "filename": filename,
            "description": desc,
            "width": cropped.width,
            "height": cropped.height,
        })

    img.close()
    return results


def extract_page_figures(
    image_path: Path,
    page_num: int,
    output_dir: Path,
    api_key: str,
    *,
    model: str = "gemini-2.0-flash",
    dry_run: bool = False,
) -> list[dict]:
    """Full pipeline: detect figures via Gemini, then crop them.

    Args:
        image_path: Path to the rendered page PNG.
        page_num: Page number.
        output_dir: Directory for cropped images.
        api_key: Gemini API key.
        model: Gemini model name.

    Returns:
        List of cropped figure info dicts.
    """
    figures = detect_figures(image_path, api_key, model=model, dry_run=dry_run)

    if not figures:
        return []

    return crop_figures(image_path, figures, output_dir, page_num)
