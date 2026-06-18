from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


ROOT = Path("data/raw/finalhopes")
OUT = Path("data/processed/finalhopes/pdf_images")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ["guizhizupu.pdf", "lindadong-min.pdf"]:
        path = ROOT / name
        reader = PdfReader(str(path))
        print(name, "pages", len(reader.pages))
        for page_index, page in enumerate(reader.pages, start=1):
            try:
                images = list(page.images)
            except Exception as exc:  # noqa: BLE001
                print(" page", page_index, "images_error", type(exc).__name__, exc)
                continue
            print(" page", page_index, "images", len(images))
            for image_index, image in enumerate(images[:3], start=1):
                print("  image", image_index, image.name, len(image.data))
                if page_index <= 2 and image_index <= 2:
                    suffix = Path(image.name).suffix or ".bin"
                    target = OUT / f"{Path(name).stem}-p{page_index}-i{image_index}{suffix}"
                    target.write_bytes(image.data)


if __name__ == "__main__":
    main()

