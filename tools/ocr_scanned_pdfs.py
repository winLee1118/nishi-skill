from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from pypdf import PdfReader

from nihaixia_core.finalhopes_import import write_markdown
from nihaixia_core.ingest import build_index


def extract_page_images(pdf_path: Path, image_dir: Path) -> list[Path]:
    image_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(pdf_path))
    paths: list[Path] = []
    for page_index, page in enumerate(reader.pages, start=1):
        for image_index, image in enumerate(page.images, start=1):
            suffix = Path(image.name).suffix or ".bin"
            target = image_dir / f"{pdf_path.stem}-p{page_index:03d}-i{image_index:02d}{suffix}"
            target.write_bytes(image.data)
            paths.append(target)
    return paths


def ocr_image(image_path: Path, tesseract: str, lang: str) -> str:
    tessdata_dir = Path("data/ocr/tessdata")
    command = [tesseract, str(image_path), "stdout", "-l", lang, "--psm", "6"]
    if tessdata_dir.exists():
        command.extend(["--tessdata-dir", str(tessdata_dir)])
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def ocr_pdf(pdf_path: Path, output_root: Path, lang: str) -> Path:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        standard_path = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
        if standard_path.exists():
            tesseract = str(standard_path)
    if not tesseract:
        raise RuntimeError("tesseract is not installed or not in PATH.")
    image_dir = Path("data/processed/finalhopes/pdf_images")
    images = extract_page_images(pdf_path, image_dir)
    sections: list[str] = []
    for image in images:
        text = ocr_image(image, tesseract, lang)
        if text:
            sections.append(f"## {image.name}\n\n{text}")
    source_url = f"http://www.finalhopes.com/nihaixia/{pdf_path.name}"
    if pdf_path.name == "guizhizupu.pdf":
        source_url = "http://www.finalhopes.com/nihaixia/guizhizupu.pdf"
    elif pdf_path.name == "lindadong-min.pdf":
        source_url = "http://www.finalhopes.com/nihaixia/lindadong-min.pdf"
    return write_markdown(
        url=source_url,
        raw_path=pdf_path,
        text="\n\n".join(sections),
        note=f"OCR with tesseract lang={lang}",
        output_root=output_root,
        source_page="http://www.finalhopes.com/download.html",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR scanned finalhopes PDFs with local tesseract.")
    parser.add_argument("pdfs", nargs="+")
    parser.add_argument("--markdown-dir", default="knowledge/vault/_imported/finalhopes")
    parser.add_argument("--db", default="data/nihaixia.sqlite")
    parser.add_argument("--lang", default="chi_sim+eng")
    parser.add_argument("--build-index", action="store_true")
    args = parser.parse_args()

    for pdf in args.pdfs:
        markdown = ocr_pdf(Path(pdf), Path(args.markdown_dir), args.lang)
        print(markdown)
    if args.build_index:
        print(build_index("knowledge/vault", args.db))


if __name__ == "__main__":
    main()
