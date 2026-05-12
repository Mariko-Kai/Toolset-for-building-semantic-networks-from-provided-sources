"""compile.py -- Generate master.tex, compile to PDF, auto-fix errors via LLM."""

import re
import subprocess
import sys
from pathlib import Path


def generate_master_tex(output_dir: Path, book_key: str) -> Path:
    """Generate a master.tex that \\input's all page_NNN.tex files in order.

    Args:
        output_dir: Directory containing page_NNN.tex files.
        book_key: Book identifier for the title.

    Returns:
        Path to the generated master.tex.
    """
    # Collect all page files, sorted by page number
    page_files = sorted(output_dir.glob("page_*.tex"))
    if not page_files:
        print("  No page_*.tex files found.")
        return None

    # Build master.tex content
    lines = [
        r"\documentclass[a4paper,12pt]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1,T2A]{fontenc}",
        r"\usepackage[english,russian]{babel}",
        r"\usepackage{amsmath,amssymb,amsthm}",
        r"\usepackage{graphicx}",
        r"\usepackage{hyperref}",
        r"\usepackage{geometry}",
        r"\geometry{margin=2.5cm}",
        "",
        r"\graphicspath{{images/}}",
        "",
        f"\\title{{{book_key} -- Transcription}}",
        r"\author{pdf2tex}",
        r"\date{\today}",
        "",
        r"\begin{document}",
        r"\maketitle",
        "",
    ]

    for page_file in page_files:
        # Use relative path without extension
        rel = page_file.stem  # e.g. "page_085"
        lines.append(f"\\input{{{rel}}}")

    lines.append("")
    lines.append(r"\end{document}")
    lines.append("")

    master_path = output_dir / "master.tex"
    master_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  [OK] Generated {master_path}  ({len(page_files)} pages)")
    return master_path


def compile_tex(master_path: Path, *, max_runs: int = 2) -> tuple[bool, str]:
    """Compile master.tex using pdflatex.

    Args:
        master_path: Path to master.tex.
        max_runs: Number of pdflatex passes (2 for cross-references).

    Returns:
        Tuple of (success: bool, log_output: str).
    """
    if master_path is None:
        return False, "No master.tex to compile."

    cwd = master_path.parent
    log_output = ""

    for run in range(1, max_runs + 1):
        print(f"  pdflatex pass {run}/{max_runs}... ", end="", flush=True)
        result = subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                str(master_path.name),
            ],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=120,
        )
        log_output = result.stdout + result.stderr

        if result.returncode != 0:
            print("[FAIL]")
            return False, log_output
        else:
            print("[OK]")

    return True, log_output


def parse_latex_errors(log_output: str) -> list[dict]:
    """Parse pdflatex log output for errors.

    Returns:
        List of dicts with keys: 'file', 'line', 'message', 'context'.
    """
    errors = []

    # Pattern: ./page_NNN.tex:42: error message
    error_pattern = re.compile(
        r'^(.+?\.tex):(\d+):\s*(.+?)$',
        re.MULTILINE,
    )

    for m in error_pattern.finditer(log_output):
        filepath = m.group(1).strip()
        line_num = int(m.group(2))
        message = m.group(3).strip()

        # Get surrounding context (next few lines after the error)
        pos = m.end()
        context_end = log_output.find("\n\n", pos)
        if context_end == -1:
            context_end = min(pos + 300, len(log_output))
        context = log_output[pos:context_end].strip()

        errors.append({
            "file": filepath,
            "line": line_num,
            "message": message,
            "context": context[:500],
        })

    return errors


def fix_tex_with_llm(
    tex_path: Path,
    errors: list[dict],
    api_key: str,
    *,
    model: str = "gemini-2.0-flash",
) -> bool:
    """Send the .tex file + error messages to LLM for auto-fix.

    Args:
        tex_path: Path to the broken .tex file.
        errors: List of error dicts from parse_latex_errors.
        api_key: Gemini API key.
        model: Gemini model name.

    Returns:
        True if fix was applied.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("ERROR: google-genai not installed.")
        return False

    if not tex_path.exists():
        print(f"  File not found: {tex_path}")
        return False

    tex_content = tex_path.read_text(encoding="utf-8")

    # Build error description
    error_desc = ""
    for i, err in enumerate(errors, 1):
        error_desc += f"\nError {i}:\n"
        error_desc += f"  Line {err['line']}: {err['message']}\n"
        if err['context']:
            error_desc += f"  Context: {err['context']}\n"

    system_prompt = (
        "You are a LaTeX error-fixing assistant. "
        "You receive a .tex file that failed to compile, along with the pdflatex error messages. "
        "Your task is to fix the LaTeX errors and return the ENTIRE corrected .tex file. "
        "Rules:\n"
        "1. Fix ONLY the compilation errors. Do NOT change the content.\n"
        "2. Do NOT add \\documentclass, \\usepackage, or \\begin{document} (this is an \\input file).\n"
        "3. Return ONLY the corrected LaTeX source, no explanations or markdown fences.\n"
        "4. Preserve all original text, formulas, and formatting.\n"
    )

    user_text = (
        f"The following LaTeX file has compilation errors. Fix them.\n\n"
        f"=== ERRORS ===\n{error_desc}\n\n"
        f"=== FILE CONTENT ===\n{tex_content}"
    )

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model,
        contents=[
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_text)],
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,
            max_output_tokens=8192,
        ),
    )

    fixed_content = response.text.strip()

    # Strip markdown fences if present
    fixed_content = re.sub(r"^```(?:latex|tex)?\s*\n", "", fixed_content, count=1)
    fixed_content = re.sub(r"\n```\s*$", "", fixed_content, count=1)

    if fixed_content and fixed_content != tex_content:
        # Backup original
        backup_path = tex_path.with_suffix(".tex.bak")
        backup_path.write_text(tex_content, encoding="utf-8")
        # Write fix
        tex_path.write_text(fixed_content, encoding="utf-8")
        print(f"  [FIXED] {tex_path.name}  (backup: {backup_path.name})")
        return True
    else:
        print(f"  [NO CHANGE] LLM returned identical content for {tex_path.name}")
        return False


def compile_and_fix(
    output_dir: Path,
    book_key: str,
    api_key: str,
    *,
    model: str = "gemini-2.0-flash",
    max_fix_rounds: int = 3,
) -> bool:
    """Full pipeline: generate master.tex, compile, and auto-fix errors.

    Args:
        output_dir: Directory with page_NNN.tex files.
        book_key: Book identifier.
        api_key: Gemini API key.
        model: Gemini model name.
        max_fix_rounds: Maximum number of fix-compile cycles.

    Returns:
        True if compilation succeeds.
    """
    print("\n[4/6] Generating master.tex...")
    master_path = generate_master_tex(output_dir, book_key)
    if master_path is None:
        return False

    for round_num in range(1, max_fix_rounds + 1):
        print(f"\n[5/6] Compiling (round {round_num}/{max_fix_rounds})...")
        success, log_output = compile_tex(master_path)

        if success:
            pdf_path = master_path.with_suffix(".pdf")
            print(f"\n  Compilation successful!")
            print(f"  PDF: {pdf_path}")
            return True

        # Parse errors
        errors = parse_latex_errors(log_output)
        if not errors:
            print("  No parseable errors found. Raw log tail:")
            print(log_output[-1000:])
            return False

        print(f"\n  Found {len(errors)} error(s):")
        for err in errors[:5]:
            print(f"    {err['file']}:{err['line']} -- {err['message']}")

        # Group errors by file
        errors_by_file = {}
        for err in errors:
            fname = err["file"]
            # Normalize path (pdflatex may use ./ prefix)
            if fname.startswith("./"):
                fname = fname[2:]
            errors_by_file.setdefault(fname, []).append(err)

        # Fix each file
        print(f"\n[6/6] Auto-fixing with LLM (round {round_num})...")
        any_fixed = False
        for fname, file_errors in errors_by_file.items():
            tex_path = output_dir / fname
            if tex_path.exists():
                fixed = fix_tex_with_llm(tex_path, file_errors, api_key, model=model)
                any_fixed = any_fixed or fixed

        if not any_fixed:
            print("  LLM could not fix the errors. Manual intervention needed.")
            return False

        # Regenerate master.tex in case files changed
        generate_master_tex(output_dir, book_key)

    print(f"\n  Max fix rounds ({max_fix_rounds}) reached. Compilation still failing.")
    return False
