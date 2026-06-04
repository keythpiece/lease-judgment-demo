from __future__ import annotations

from typing import Any


VALUE_LABELS = {
    "Yes": "はい",
    "No": "いいえ",
    "Unknown": "要確認",
    "Lease": "リース対象",
    "Non-lease": "対象外",
    "Human review required": "確認必要",
    "Finance lease": "ファイナンスリース",
    "Operating lease": "オペレーティングリース",
    "Classification unavailable": "分類要確認",
    "Not applicable": "該当なし",
    "High": "高",
    "Medium": "中",
    "Low": "低",
    "Lessee": "借手",
    "Lessor": "貸手",
    "Neither": "どちらでもない",
    "Movable": "動産",
    "RealEstate": "不動産",
    "Proceed to Step2": "Step2へ進む",
    "Excluded candidate": "対象外候補",
}


def display_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return VALUE_LABELS.get(value, value)


def display_text(text: Any) -> Any:
    if not isinstance(text, str):
        return text
    converted = text
    for source, label in sorted(VALUE_LABELS.items(), key=lambda item: len(item[0]), reverse=True):
        converted = converted.replace(source, label)
    return converted


def review_text(guidance: dict[str, Any] | None, fallback: str = "") -> str:
    if not guidance:
        return fallback
    parts = [
        guidance.get("question", ""),
        f"Yesの場合: {guidance.get('if_yes', '')}" if guidance.get("if_yes") else "",
        f"Noの場合: {guidance.get('if_no', '')}" if guidance.get("if_no") else "",
    ]
    return "\n".join(part for part in parts if part)
