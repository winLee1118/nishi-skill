from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


ROOT = Path("data/raw/finalhopes")


def inspect_pdf(name: str) -> None:
    path = ROOT / name
    print(f"\n{name}")
    try:
        reader = PdfReader(str(path))
        print("pages", len(reader.pages), "encrypted", reader.is_encrypted)
        total = 0
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            total += len(text)
            if index <= 5:
                image_count = "unknown"
                try:
                    image_count = str(len(page.images))
                except Exception as exc:  # noqa: BLE001
                    image_count = f"err:{type(exc).__name__}"
                print("page", index, "chars", len(text), "images", image_count, repr(text[:160]))
        print("total_text_chars", total)
    except Exception as exc:  # noqa: BLE001
        print("ERR", type(exc).__name__, exc)


def inspect_doc(name: str) -> None:
    path = ROOT / name
    data = path.read_bytes()
    print(f"\n{name}")
    print("size", len(data))
    print("ole_header", data[:8].hex(" "))
    for needle in ["WordDocument", "Microsoft Office Word", "W\x00o\x00r\x00d\x00D\x00o\x00c\x00u\x00m\x00e\x00n\x00t"]:
        raw = needle.encode("utf-16le") if "\x00" in needle else needle.encode("ascii", errors="ignore")
        print("contains", needle.replace("\x00", ""), data.find(raw))


def main() -> None:
    inspect_doc("tianjishouxie.doc")
    inspect_doc("ziweidoushu.doc")
    inspect_pdf("guizhizupu.pdf")
    inspect_pdf("lindadong-min.pdf")


if __name__ == "__main__":
    main()

