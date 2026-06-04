from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable

from .schemas import evidence


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def split_sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[。．.!?！？])\s*|\n+", text)
    return [normalize_text(s) for s in raw if normalize_text(s)]


def find_keyword_evidence(
    pages: list[dict[str, str | int]],
    keywords: Iterable[str],
    why: str,
    limit: int = 3,
) -> list[dict]:
    hits: list[dict] = []
    keys = [k for k in keywords if k]
    for page in pages:
        page_no = int(page["page"])
        for sentence in split_sentences(str(page.get("text", ""))):
            if any(k in sentence for k in keys):
                hits.append(evidence(page_no, sentence[:700], why))
                if len(hits) >= limit:
                    return hits
    return hits


def any_keyword(text: str, keywords: Iterable[str]) -> bool:
    return any(k in text for k in keywords if k)


def best_text_match(page_text: str, target: str) -> str:
    page_text = normalize_text(page_text)
    target = normalize_text(target)
    if not target or not page_text:
        return ""
    if target in page_text:
        return target
    target_words = target.split()
    if len(target_words) > 4:
        for size in range(min(len(target_words), 14), 3, -1):
            for idx in range(0, len(target_words) - size + 1):
                part = " ".join(target_words[idx : idx + size])
                if part in page_text:
                    return part
    sentences = split_sentences(page_text)
    best = ""
    score = 0.0
    for sentence in sentences:
        ratio = SequenceMatcher(None, sentence[:500], target[:500]).ratio()
        if ratio > score:
            score = ratio
            best = sentence
    return best if score >= 0.45 else ""
