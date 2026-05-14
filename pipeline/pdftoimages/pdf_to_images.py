"""pdf_to_images.py — Render PDF pages as PNG images for transcription.

Usage:
    python pipeline/pdf_to_images.py BOOK_KEY [OPTIONS]

Examples:
    # Render pages 85-120 of Zorich Vol 1
    python pipeline/pdf_to_images.py zorich-1 --pages 85-120

    # Render page 90, split into top and bottom halves
    python pipeline/pdf_to_images.py zorich-1 --pages 90 --half

    # Render all pages of Rudin Ch.3 at 200 DPI
    python pipeline/pdf_to_images.py rudin --pages 43-68 --dpi 200

Output goes to:  staging/BOOK_KEY/page_NNN.png  (or page_NNN_top.png / _bottom.png)
"""

import argparse
import sys
from pathlib import Path

# Resolve project root relative to this script
# Resolve project root relative to this script
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BOOKS_DIR = PROJECT_ROOT / "Books"
STAGING_DIR = Path(__file__).resolve().parent / "staging"

# Book registry — maps key to {file, lang}
BOOK_REGISTRY = {
    "zorich-1":     {"file": "Zorich, V.A. - Mathematical Analysis Vol 1 - (RU) - [10th ed].pdf", "lang": "ru"},
    "zorich-2":     {"file": "Zorich, V.A. - Mathematical Analysis Vol 2 - (RU) - [9th ed].pdf", "lang": "ru"},
    "zorich-12":    {"file": "Zorich, V.A. - Mathematical Analysis Vol 1-2 - (RU) - [2018].pdf", "lang": "ru"},
    "rudin":        {"file": None, "lang": "en"},
    "spivak":       {"file": "Spivak, M. - Calculus - (EN).pdf", "lang": "en"},
    "kudryavtsev-1": {"file": "Kudryavtsev, L.D. - Course of Mathematical Analysis Vol 1 - (RU).pdf", "lang": "ru"},
    "kudryavtsev-2": {"file": "Kudryavtsev, L.D. - Course of Mathematical Analysis Vol 2 - (RU) - [2004].pdf", "lang": "ru"},
    "kudryavtsev-3": {"file": "Kudryavtsev, L.D. - Course of Mathematical Analysis Vol 3 - (RU) - [2006].pdf", "lang": "ru"},
    "apostol-1":    {"file": "Apostol, T.M. - Calculus Vol 1 - (EN) - [1991].pdf", "lang": "en"},
    "apostol-2":    {"file": "Apostol, T.M. - Calculus Vol 2 - (EN) - [1975].pdf", "lang": "en"},
    "hardy":        {"file": "Hardy, G.H. - A Course of Pure Mathematics - (EN).pdf", "lang": "en"},
    "nikolsky":     {"file": "Nikolsky, S.M. - A Course of Mathematical Analysis Vol 1 - (EN).pdf", "lang": "en"},
    "ilin-1":       {"file": "Ilin, V.A., Sadovnichii, V.A., Sendov, B.H. - Mathematical Analysis Vol 1 - (RU).pdf", "lang": "ru"},
    "ilin-2":       {"file": "Ilin, V.A., Sadovnichii, V.A., Sendov, B.H. - Mathematical Analysis Vol 2 - (RU).pdf", "lang": "ru"},
    # New additions
    "butuzov":      {"file": "Butuzov, B.F. - Mathematical Analysis in Questions and Problems - (EN) - [1988].pdf", "lang": "en"},
    "efimov":       {"file": "Efimov, Demidovich - Higher Mathematics Part 1 - (EN) - [1984].pdf", "lang": "en"},
    "elsgolts":     {"file": "Elsgolts, L.E. - Differential Equations and the Calculus of Variations - (EN) - [1970].pdf", "lang": "en"},
    "knuth-concrete": {"file": "Graham, R.L., Knuth, D.E., Patashnik, O. - Concrete Mathematics - (EN) - [1994].pdf", "lang": "en"},
    "kolmogorov-prob": {"file": "Kolmogorov, A.N. - Foundations of the Theory of Probability - (EN) - [1956].pdf", "lang": "en"},
    "herbert-logic": {"file": "Enderton, H.B. - A Mathematical Introduction to Logic - (EN) - [2001].pdf", "lang": "en"},
    "mendelson":    {"file": "Mendelson, E. - Introduction to Mathematical Logic - (RU) - [1971].pdf", "lang": "ru"},
    "shen-complexity": {"file": "Shen, A., Uspensky, V.A., Vereshchagin, N.K. - Kolmogorov Complexity and Algorithmic Randomness - (EN) - [2017].pdf", "lang": "en"},
    "spivak-manifolds-en": {"file": "Spivak, M. - Calculus on Manifolds - (EN) - [1965].pdf", "lang": "en"},
    "spivak-manifolds-ru": {"file": "Spivak, M. - Calculus on Manifolds - (RU) - [1968].pdf", "lang": "ru"},
    "russell-1":    {"file": "Whitehead, A.N., Russell, B. - Principia Mathematica Vol 1 - (EN) - [1925].pdf", "lang": "en"},
    "russell-2":    {"file": "Whitehead, A.N., Russell, B. - Principia Mathematica Vol 2 - (EN) - [1927].pdf", "lang": "en"},
    "russell-3":    {"file": "Whitehead, A.N., Russell, B. - Principia Mathematica Vol 3 - (EN) - [1927].pdf", "lang": "en"},
    "vereshchagin-1": {"file": "Vereshchagin, N.K., Shen, A. - Basic Set Theory - (RU) - [2012].pdf", "lang": "ru"},
    "vereshchagin-2": {"file": "Vereshchagin, N.K., Shen, A. - Languages and Calculi - (RU) - [2012].pdf", "lang": "ru"},
    "vereshchagin-3": {"file": "Vereshchagin, N.K., Shen, A. - Computable Functions - (RU) - [2012].pdf", "lang": "ru"},
}


def parse_page_range(spec: str) -> list[int]:
    """Parse a page range like '85-120' or '90' or '1,5,10-15'."""
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return sorted(set(pages))


def render_pages(
    pdf_path: Path,
    book_key: str,
    pages: list[int],
    dpi: int = 150,
    split_half: bool = False,
) -> list[Path]:
    """Render specified PDF pages as PNG images.

    Args:
        pdf_path: Path to the PDF file
        book_key: Book identifier for output directory
        pages: 1-indexed page numbers to render
        dpi: Resolution (default 150, good balance of quality/size)
        split_half: If True, split each page into top and bottom halves

    Returns:
        List of paths to generated PNG files
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("ERROR: PyMuPDF not installed. Run: pip install PyMuPDF")
        sys.exit(1)

    output_dir = STAGING_DIR / book_key
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    generated = []

    for page_num in pages:
        # PDF pages are 0-indexed in PyMuPDF
        idx = page_num - 1
        if idx < 0 or idx >= total_pages:
            print(f"  SKIP page {page_num}: out of range (PDF has {total_pages} pages)")
            continue

        page = doc[idx]
        zoom = dpi / 72  # 72 is the default PDF DPI
        mat = fitz.Matrix(zoom, zoom)

        if split_half:
            # Render top half
            rect = page.rect
            mid_y = rect.y0 + (rect.y1 - rect.y0) / 2

            clip_top = fitz.Rect(rect.x0, rect.y0, rect.x1, mid_y)
            pix_top = page.get_pixmap(matrix=mat, clip=clip_top)
            path_top = output_dir / f"page_{page_num:03d}_top.png"
            pix_top.save(str(path_top))
            generated.append(path_top)
            print(f"  [OK] {path_top.name}  ({pix_top.width}x{pix_top.height})")

            clip_bottom = fitz.Rect(rect.x0, mid_y, rect.x1, rect.y1)
            pix_bottom = page.get_pixmap(matrix=mat, clip=clip_bottom)
            path_bottom = output_dir / f"page_{page_num:03d}_bottom.png"
            pix_bottom.save(str(path_bottom))
            generated.append(path_bottom)
            print(f"  [OK] {path_bottom.name}  ({pix_bottom.width}x{pix_bottom.height})")
        else:
            pix = page.get_pixmap(matrix=mat)
            path_full = output_dir / f"page_{page_num:03d}.png"
            pix.save(str(path_full))
            generated.append(path_full)
            print(f"  [OK] {path_full.name}  ({pix.width}x{pix.height})")

    doc.close()
    return generated


def main():
    parser = argparse.ArgumentParser(
        description="Render PDF pages as PNG images for transcription.",
        epilog="Output: staging/BOOK_KEY/page_NNN.png",
    )
    parser.add_argument(
        "book",
        nargs="?",
        choices=sorted(BOOK_REGISTRY.keys()),
        help="Book key from the registry",
    )
    parser.add_argument(
        "--pages", "-p",
        required=True,
        help="Page range: '85-120', '90', '1,5,10-15'",
    )
    parser.add_argument(
        "--dpi", "-d",
        type=int,
        default=150,
        help="Resolution in DPI (default: 150)",
    )
    parser.add_argument(
        "--half",
        action="store_true",
        help="Split each page into top and bottom halves",
    )
    parser.add_argument(
        "--list-books",
        action="store_true",
        help="List available books and exit",
    )

    args = parser.parse_args()

    if args.list_books:
        print("Available books:")
        for key, info in sorted(BOOK_REGISTRY.items()):
            filename = info["file"]
            lang = info["lang"]
            status = "+" if filename and (BOOKS_DIR / filename).exists() else "-"
            print(f"  {status} {key:20s} [{lang}]  {filename or '(not available)'}")
        return

    book_info = BOOK_REGISTRY.get(args.book)
    if not book_info or not book_info["file"]:
        print(f"ERROR: Book '{args.book}' has no PDF registered.")
        sys.exit(1)

    filename = book_info["file"]

    pdf_path = BOOKS_DIR / filename
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    pages = parse_page_range(args.pages)
    print(f"Rendering {len(pages)} page(s) from '{args.book}' at {args.dpi} DPI...")
    print(f"PDF: {pdf_path.name}")
    print(f"Output: staging/{args.book}/")
    print()

    generated = render_pages(pdf_path, args.book, pages, args.dpi, args.half)

    print(f"\nDone. {len(generated)} image(s) saved to staging/{args.book}/")


if __name__ == "__main__":
    main()
