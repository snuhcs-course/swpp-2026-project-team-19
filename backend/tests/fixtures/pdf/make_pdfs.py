"""Rebuilds the PDF fixtures of this folder (I4-P13). Not run by the tests or by CI.

Needs google-chrome, soffice (LibreOffice), the Noto CJK fonts, and the Python packages pypdf,
pypdfium2, pillow and numpy. Every menu here is made up: no real bar, menu or price.

    python make_pdfs.py

text_menu_design.pdf   one page, printed from text_menu_design.html with Chrome (a design-tool export)
text_menu_office.pdf   two pages, converted from text_menu_office.html with LibreOffice Writer
scanned_menu_1.pdf     one page: the first text menu as a picture, slightly turned, with noise
scanned_menu_2.pdf     two pages: the office menu's pages as pictures
rotated_text.pdf       text_menu_design.pdf with a 90 degree page rotation
encrypted.pdf          text_menu_design.pdf with a password
corrupt.pdf            the first 2000 bytes of text_menu_design.pdf
"""

import io
import subprocess
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader, PdfWriter

HERE = Path(__file__).resolve().parent


def render(pdf: Path, long_side: int = 1600) -> list[Image.Image]:
    document = pdfium.PdfDocument(pdf.read_bytes())
    pages = []
    for page in document:
        width, height = page.get_size()
        pages.append(page.render(scale=long_side / max(width, height)).to_pil().convert("RGB"))
    return pages


def as_scan(image: Image.Image, seed: int, turn: float) -> Image.Image:
    rng = np.random.default_rng(seed)
    image = image.rotate(turn, resample=Image.BICUBIC, expand=True, fillcolor=(236, 232, 224))
    pixels = np.asarray(image).astype(np.int16) + rng.normal(0, 6, (image.height, image.width, 3))
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def save_images(images: list[Image.Image], path: Path) -> None:
    out = io.BytesIO()
    images[0].save(out, format="PDF", save_all=True, append_images=images[1:], resolution=150, quality=80)
    path.write_bytes(out.getvalue())


def main() -> None:
    design, office = HERE / "text_menu_design.pdf", HERE / "text_menu_office.pdf"
    subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={design}", str(HERE / "text_menu_design.html")], check=True)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf:writer_web_pdf_Export", "--outdir", str(HERE),
                    str(HERE / "text_menu_office.html")], check=True)

    save_images([as_scan(render(design)[0], seed=1, turn=1.5)], HERE / "scanned_menu_1.pdf")
    scans = [as_scan(page, seed=2 + i, turn=-1.0) for i, page in enumerate(render(office))]
    save_images(scans, HERE / "scanned_menu_2.pdf")

    reader = PdfReader(design)
    rotated = PdfWriter()
    rotated.add_page(reader.pages[0]).rotate(90)
    rotated.write(HERE / "rotated_text.pdf")
    encrypted = PdfWriter()
    encrypted.add_page(reader.pages[0])
    encrypted.encrypt("menu-password")
    encrypted.write(HERE / "encrypted.pdf")
    (HERE / "corrupt.pdf").write_bytes(design.read_bytes()[:2000])


if __name__ == "__main__":
    main()
