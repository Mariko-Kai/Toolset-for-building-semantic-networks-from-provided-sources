"""cli.py — Command-line interface for pdf2tex converter."""

import argparse
import os
import sys
from pathlib import Path

# Add parent tools dir to path for pdf_to_images imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdf_to_images import BOOK_REGISTRY, BOOKS_DIR, parse_page_range
from .convert import convert_pages


def main():
    parser = argparse.ArgumentParser(
        prog="pdf2tex",
        description="Convert PDF textbook pages to LaTeX via Gemini API.",
        epilog=(
            "Examples:\n"
            "  python -m tools.pdf2tex zorich-1 --pages 85-90 --api-key YOUR_KEY\n"
            "  python -m tools.pdf2tex zorich-1 --pages 85 --api-key-env GEMINI_API_KEY\n"
            "  python -m tools.pdf2tex zorich-1 --pages 85 --api-key KEY --dry-run\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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

    # API key: either direct or from environment variable
    key_group = parser.add_mutually_exclusive_group(required=True)
    key_group.add_argument(
        "--api-key",
        help="Gemini API key (direct value)",
    )
    key_group.add_argument(
        "--api-key-env",
        metavar="ENV_VAR",
        help="Environment variable containing the Gemini API key",
    )

    parser.add_argument(
        "--model", "-m",
        default="gemini-2.0-flash",
        help="Gemini model (default: gemini-2.0-flash)",
    )
    parser.add_argument(
        "--dpi", "-d",
        type=int,
        default=200,
        help="Render DPI (default: 200)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="Output directory for .tex files (default: sources/BOOK/)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between API calls in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompts without calling the API",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Re-convert pages even if .tex already exists",
    )
    parser.add_argument(
        "--no-compile",
        action="store_true",
        help="Skip compilation and auto-fix step",
    )
    parser.add_argument(
        "--max-fix-rounds",
        type=int,
        default=3,
        help="Max compile-fix cycles (default: 3)",
    )
    parser.add_argument(
        "--list-books",
        action="store_true",
        help="List available books and exit",
    )

    args = parser.parse_args()

    # List books mode
    if args.list_books:
        print("Available books:")
        for key, info in sorted(BOOK_REGISTRY.items()):
            filename = info["file"]
            lang = info["lang"]
            status = "+" if filename and (BOOKS_DIR / filename).exists() else "-"
            print(f"  {status} {key:20s} [{lang}]  {filename or '(not available)'}")
        return

    # Resolve API key
    if args.api_key:
        api_key = args.api_key
    else:
        api_key = os.environ.get(args.api_key_env, "")
        if not api_key:
            print(f"ERROR: Environment variable '{args.api_key_env}' is not set or empty.")
            sys.exit(1)

    # Resolve PDF
    book_info = BOOK_REGISTRY.get(args.book)
    if not book_info or not book_info["file"]:
        print(f"ERROR: Book '{args.book}' has no PDF registered.")
        sys.exit(1)

    filename = book_info["file"]
    lang = book_info["lang"]

    pdf_path = BOOKS_DIR / filename
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    pages = parse_page_range(args.pages)

    convert_pages(
        pdf_path=pdf_path,
        book_key=args.book,
        pages=pages,
        api_key=api_key,
        lang=lang,
        output_dir=args.output_dir,
        dpi=args.dpi,
        model=args.model,
        dry_run=args.dry_run,
        delay=args.delay,
        skip_existing=not args.no_skip,
        compile=not args.no_compile,
        max_fix_rounds=args.max_fix_rounds,
    )


if __name__ == "__main__":
    main()
