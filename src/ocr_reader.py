from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path


class OCRReader(ABC):
    @abstractmethod
    def extract_page_text(self, pdf_path: str | Path, page_index: int) -> str:
        raise NotImplementedError


class NoopOCRReader(OCRReader):
    def extract_page_text(self, pdf_path: str | Path, page_index: int) -> str:
        return ""


class TesseractOCRReader(OCRReader):
    def __init__(self, language: str = "jpn+eng", dpi: int = 220) -> None:
        self.language = language
        self.dpi = dpi
        cmd = os.getenv("TESSERACT_CMD", "").strip()
        if cmd:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = cmd

    def extract_page_text(self, pdf_path: str | Path, page_index: int) -> str:
        import fitz
        import pytesseract

        with fitz.open(pdf_path) as doc:
            page = doc[page_index]
            pix = page.get_pixmap(dpi=self.dpi, alpha=False)
            text = pytesseract.image_to_string(
                pix.pil_image(), lang=self.language, config="--psm 6"
            )
        return text.strip()


def build_ocr_reader(engine: str | None = None) -> OCRReader:
    engine = (engine or os.getenv("OCR_ENGINE", "none")).lower()
    if engine in {"tesseract", "pytesseract"}:
        return TesseractOCRReader()
    return NoopOCRReader()
