from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz

from .evidence_extractor import best_text_match, normalize_text
from .utils import flatten_evidence


def highlight_pdf(input_pdf: str | Path, result: dict[str, Any], output_pdf: str | Path) -> dict[str, Any]:
    input_pdf = Path(input_pdf)
    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    status: list[dict[str, Any]] = []

    with fitz.open(input_pdf) as doc:
        for ev in flatten_evidence(result):
            if not ev.get("highlight_required", True):
                continue
            page_no = ev.get("page")
            text = normalize_text(str(ev.get("text", "")))
            if not page_no or page_no < 1 or page_no > len(doc) or not text:
                continue
            page = doc[page_no - 1]
            rects = page.search_for(text)
            used_text = text
            if not rects:
                match = best_text_match(page.get_text("text"), text)
                used_text = match
                if match:
                    rects = page.search_for(match)
            if not rects and len(text) > 30:
                for size in (80, 50, 30):
                    fragment = text[:size]
                    rects = page.search_for(fragment)
                    if rects:
                        used_text = fragment
                        break
            for rect in rects:
                annot = page.add_highlight_annot(rect)
                annot.set_colors(stroke=(1, 0.92, 0))
                annot.update()
            status.append(
                {
                    "page": page_no,
                    "text": text,
                    "matched_text": used_text if rects else "",
                    "highlighted": bool(rects),
                    "rect_count": len(rects),
                }
            )
        doc.save(output_pdf, garbage=4, deflate=True)
    return {"output_pdf": str(output_pdf), "status": status}
