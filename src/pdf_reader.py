from __future__ import annotations

from pathlib import Path

import fitz

from .ocr_reader import OCRReader, build_ocr_reader


class PDFReader:
    def __init__(self, ocr_reader: OCRReader | None = None, min_text_chars: int = 20) -> None:
        self.ocr_reader = ocr_reader or build_ocr_reader()
        self.min_text_chars = min_text_chars

    def read(self, pdf_path: str | Path) -> list[dict[str, str | int]]:
        pdf_path = Path(pdf_path)
        pages: list[dict[str, str | int]] = []
        with fitz.open(pdf_path) as doc:
            for idx, page in enumerate(doc):
                text = page.get_text("text").strip()
                source = "text"
                if len(text) < self.min_text_chars:
                    ocr_text = self.ocr_reader.extract_page_text(pdf_path, idx)
                    if ocr_text:
                        text = ocr_text
                        source = "ocr"
                pages.append({"page": idx + 1, "text": text, "source": source})
        return pages
