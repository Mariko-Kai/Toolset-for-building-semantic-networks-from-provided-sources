"""convert.py — Core converter: send page image to Gemini API, receive LaTeX."""

import base64
import re
import sys
import time
from pathlib import Path

from .prompt import get_system_prompt


def _read_image_base64(image_path: Path) -> str:
    """Read an image file and return its base64 encoding."""
    return base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")


def _mime_type(image_path: Path) -> str:
    """Infer MIME type from file extension."""
    ext = image_path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")


def _clean_response(text: str) -> str:
    """Strip markdown code fences if the model wraps output in them."""
    # Remove ```latex ... ``` wrapper
    text = re.sub(r"^```(?:latex|tex)?\s*\n", "", text, count=1)
    text = re.sub(r"\n```\s*$", "", text, count=1)
    return text.strip()


def convert_page(
    image_path: Path,
    api_key: str,
    *,
    lang: str = "en",
    model: str = "gemini-2.0-flash",
    page_num: int | None = None,
    extra_context: str = "",
    dry_run: bool = False,
) -> str:
    """Convert a single page image to LaTeX via Gemini API.

    Args:
        image_path: Path to the PNG/JPEG image of the page.
        api_key: Gemini API key.
        lang: Language of the book ('ru' or 'en').
        model: Gemini model name.
        page_num: Optional page number for context in the prompt.
        extra_context: Optional extra instructions appended to the prompt.
        dry_run: If True, return the prompt instead of calling the API.

    Returns:
        LaTeX source code as a string.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("ERROR: google-genai not installed. Run: pip install google-genai")
        sys.exit(1)

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Build user message
    user_text = "Transcribe this textbook page to LaTeX."
    if page_num is not None:
        user_text += f" This is page {page_num}."
    if extra_context:
        user_text += f"\n\n{extra_context}"

    if dry_run:
        prompt = get_system_prompt(lang)
        return f"=== SYSTEM PROMPT ({lang}) ===\n{prompt}\n\n=== USER ===\n{user_text}\n\n=== IMAGE ===\n{image_path}"

    # Create client and call API
    client = genai.Client(api_key=api_key)

    # Read image data
    img_data = image_path.read_bytes()
    mime = _mime_type(image_path)

    response = client.models.generate_content(
        model=model,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=img_data, mime_type=mime),
                    types.Part.from_text(text=user_text),
                ],
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=get_system_prompt(lang),
            temperature=0.1,  # Low temperature for faithful reproduction
            max_output_tokens=8192,
        ),
    )

    return _clean_response(response.text)


def convert_pages(
    pdf_path: Path,
    book_key: str,
    pages: list[int],
    api_key: str,
    *,
    lang: str = "en",
    output_dir: Path | None = None,
    images_dir: Path | None = None,
    dpi: int = 200,
    model: str = "gemini-2.0-flash",
    dry_run: bool = False,
    delay: float = 2.0,
    skip_existing: bool = True,
    compile: bool = True,
    max_fix_rounds: int = 3,
) -> list[Path]:
    """Convert multiple PDF pages to LaTeX.

    Pipeline:
        1. Render page to PNG (via pdf_to_images)
        2. Extract embedded images (via images.py)
        3. Send to Gemini API (via convert_page)
        4. Save .tex file

    Args:
        pdf_path: Path to the PDF file.
        book_key: Book identifier (e.g. 'zorich-1').
        pages: 1-indexed page numbers.
        api_key: Gemini API key.
        lang: Language of the book ('ru' or 'en').
        output_dir: Where to save .tex files. Default: sources/BOOK_KEY/
        images_dir: Where to save extracted images. Default: sources/BOOK_KEY/images/
        dpi: Resolution for rendering pages.
        model: Gemini model name.
        dry_run: If True, print prompts without calling API.
        delay: Seconds to wait between API calls (rate limiting).
        skip_existing: If True, skip pages that already have .tex files.
        compile: If True, generate master.tex and compile after conversion.
        max_fix_rounds: Max compile-fix cycles.

    Returns:
        List of paths to generated .tex files.
    """
    # Import here to reuse existing pdf_to_images logic
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pdf_to_images import render_pages, PROJECT_ROOT

    if output_dir is None:
        output_dir = PROJECT_ROOT / "sources" / book_key
    if images_dir is None:
        images_dir = output_dir / "images"

    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Render pages to PNG
    print(f"\n{'='*60}")
    print(f"  PDF -> LaTeX Converter")
    print(f"  Book: {book_key}  |  Pages: {pages[0]}-{pages[-1]}  |  Model: {model}")
    print(f"{'='*60}\n")

    print("[1/3] Rendering pages to PNG...")
    staging_images = render_pages(pdf_path, book_key, pages, dpi=dpi)
    print(f"      {len(staging_images)} image(s) rendered.\n")

    # Step 2: Detect and crop figures via Gemini
    print("[2/3] Detecting figures via Gemini...")
    from .images import extract_page_figures

    # Collect detected figures per page for Step 3
    page_figures: dict[int, list[dict]] = {}
    for page_num, image_path in zip(pages, staging_images):
        extracted = extract_page_figures(
            image_path, page_num, images_dir, api_key, model=model, dry_run=dry_run,
        )
        if extracted:
            page_figures[page_num] = extracted
            for img in extracted:
                print(f"      [FIG] {img['filename']}  ({img['width']}x{img['height']})  {img['description']}")
    print()

    # Step 3: Convert each page via Gemini API
    print("[3/3] Converting pages via Gemini API...")
    generated_tex = []

    for page_num, image_path in zip(pages, staging_images):
        tex_filename = f"page_{page_num:03d}.tex"
        tex_path = output_dir / tex_filename

        # Skip existing files
        if skip_existing and tex_path.exists() and tex_path.stat().st_size > 0:
            print(f"      Page {page_num}... [SKIP] {tex_filename} already exists")
            generated_tex.append(tex_path)
            continue

        # Build figure context for this page
        figures_ctx = ""
        figs = page_figures.get(page_num, [])
        if figs:
            fig_lines = []
            for fig in figs:
                fig_lines.append(f"- images/{fig['filename']} ({fig['description']})")
            figures_ctx = (
                "\n\nThe following figures were detected and cropped from this page. "
                "Use EXACTLY these filenames in \\includegraphics:\n"
                + "\n".join(fig_lines)
            )
        else:
            figures_ctx = (
                "\n\nNo figures were detected on this page. "
                "Do NOT use \\includegraphics on this page."
            )

        print(f"      Page {page_num}... ", end="", flush=True)

        try:
            latex_content = convert_page(
                image_path,
                api_key,
                lang=lang,
                model=model,
                page_num=page_num,
                extra_context=figures_ctx,
                dry_run=dry_run,
            )

            if dry_run:
                print("[DRY RUN]")
                print(latex_content[:200] + "...\n")
            else:
                tex_path.write_text(latex_content, encoding="utf-8")
                generated_tex.append(tex_path)
                print(f"[OK] -> {tex_filename}  ({len(latex_content)} chars)")

                # Rate limiting
                if delay > 0 and page_num != pages[-1]:
                    time.sleep(delay)

        except Exception as e:
            print(f"[ERROR] {e}")

    print(f"\nConversion done. {len(generated_tex)} .tex file(s) in {output_dir}/")

    # Step 4-6: Compile and auto-fix
    if compile and not dry_run:
        from .compile import compile_and_fix
        compile_and_fix(
            output_dir, book_key, api_key,
            model=model, max_fix_rounds=max_fix_rounds,
        )

    return generated_tex
