#!/usr/bin/env python3
"""
doc2md.py — Convert .docx and .pdf files to Markdown.

Usage:
    python doc2md.py file.docx              → file.md (same directory)
    python doc2md.py file.pdf               → file.md
    python doc2md.py file.pdf -o out.md     → out.md
    python doc2md.py *.docx *.pdf           → batch convert, same dir as each input
    python doc2md.py dir/ -o outdir/        → convert all docx/pdf in dir/
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path


# ── Converters ────────────────────────────────────────────────────────────────

def convert_docx(src: Path, dst: Path) -> None:
    """LibreOffice headless → HTML, then html2text → Markdown."""
    import tempfile, html2text as h2t
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "html", "--outdir", tmp, str(src)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"libreoffice error: {result.stderr.strip()}")
        html_files = list(Path(tmp).glob("*.html"))
        if not html_files:
            raise RuntimeError("libreoffice produced no HTML output")
        html = html_files[0].read_text(encoding="utf-8", errors="replace")

    converter = h2t.HTML2Text()
    converter.ignore_images = True
    converter.body_width = 0  # no hard wraps
    dst.write_text(converter.handle(html), encoding="utf-8")


def convert_pdf(src: Path, dst: Path) -> None:
    """
    PDF → .md strategy:
      1. Try pdftotext -layout for clean text PDFs.
      2. Fall back to pdfplumber (better for multi-column / unusual layouts).
      3. Wrap output in minimal Markdown structure.
    Scanned-only PDFs will produce empty/garbled output — OCR is out of scope.
    """
    # --- attempt 1: pdftotext ---
    result = subprocess.run(
        ["pdftotext", "-layout", str(src), "-"],
        capture_output=True, text=True
    )
    text = result.stdout.strip()

    # --- attempt 2: pdfplumber if pdftotext gave nothing ---
    if not text:
        try:
            import pdfplumber
            with pdfplumber.open(str(src)) as pdf:
                pages = []
                for i, page in enumerate(pdf.pages, 1):
                    t = page.extract_text() or ""
                    if t.strip():
                        pages.append(f"<!-- page {i} -->\n\n{t.strip()}")
            text = "\n\n---\n\n".join(pages)
        except ImportError:
            pass

    if not text:
        # Warn but still write an empty file with a note
        text = (
            f"> **Warning:** No extractable text found in `{src.name}`.\n"
            "> The file may be scanned (image-only). OCR is required."
        )
        print(f"  ⚠  No text extracted from {src.name} — may be scanned.", file=sys.stderr)

    # Minimal Markdown wrapper
    title = src.stem.replace("_", " ").replace("-", " ").title()
    md = f"# {title}\n\n{text}\n"
    dst.write_text(md, encoding="utf-8")


# ── Main logic ─────────────────────────────────────────────────────────────────

CONVERTERS = {
    ".docx": convert_docx,
    ".pdf":  convert_pdf,
}


def resolve_pairs(inputs: list[str], output: str | None) -> list[tuple[Path, Path]]:
    """Return list of (src, dst) Path pairs."""
    pairs: list[tuple[Path, Path]] = []
    src_paths: list[Path] = []

    for inp in inputs:
        p = Path(inp)
        if p.is_dir():
            for ext in CONVERTERS:
                src_paths.extend(sorted(p.glob(f"*{ext}")))
        else:
            src_paths.append(p)

    if not src_paths:
        print("No input files found.", file=sys.stderr)
        sys.exit(1)

    out_path = Path(output) if output else None

    for src in src_paths:
        if out_path and out_path.is_dir():
            dst = out_path / src.with_suffix(".md").name
        elif out_path and len(src_paths) == 1:
            dst = out_path
        else:
            # same directory as source, same stem + .md
            dst = src.with_suffix(".md")
        pairs.append((src, dst))

    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert .docx / .pdf files to Markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("inputs", nargs="+", metavar="FILE_OR_DIR",
                        help=".docx / .pdf files or a directory containing them")
    parser.add_argument("-o", "--output", metavar="OUT",
                        help="output file (single input) or directory (batch)")
    args = parser.parse_args()

    pairs = resolve_pairs(args.inputs, args.output)
    ok = err = 0

    for src, dst in pairs:
        ext = src.suffix.lower()
        if ext not in CONVERTERS:
            print(f"  skip  {src}  (unsupported extension '{ext}')", file=sys.stderr)
            continue
        if not src.exists():
            print(f"  skip  {src}  (file not found)", file=sys.stderr)
            err += 1
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            CONVERTERS[ext](src, dst)
            print(f"  ✓  {src}  →  {dst}")
            ok += 1
        except Exception as e:
            print(f"  ✗  {src}: {e}", file=sys.stderr)
            err += 1

    print(f"\n{ok} converted, {err} failed.")
    if err:
        sys.exit(1)


if __name__ == "__main__":
    main()
