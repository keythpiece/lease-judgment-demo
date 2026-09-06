from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import yaml

from .utils import PROJECT_ROOT, now_local_iso


KNOWLEDGE_PATH = PROJECT_ROOT / "config" / "knowledge_base.yaml"

NOTE_CATEGORIES = ["判定ルール", "社内マニュアル", "規程", "会計方針", "その他"]
NOTE_APPLIES_TO = ["all", "step1", "step2", "step3"]

THRESHOLD_LABELS = {
    "short_term_months": "短期リース基準（か月以内）",
    "low_value_asset_jpy": "少額資産基準（円以下）",
    "finance_lease_term_ratio": "ファイナンス判定 75%テスト閾値",
    "finance_pv_ratio": "ファイナンス判定 90%PVテスト閾値",
}


def _empty_knowledge() -> dict[str, Any]:
    return {"thresholds": {}, "extra_keywords": {}, "notes": []}


class KnowledgeStore:
    """管理者が設定する社内ナレッジ（判定ルール・マニュアル・規程）の保存と参照。

    config/knowledge_base.yaml に保持し、判定エンジンは
    - thresholds: judgment_rules.yaml のしきい値を上書き
    - extra_keywords: キーワード辞書へ追加
    - notes: 契約テキストに関連するものを判定結果へ添付し、LLMプロンプトにも注入
    の3経路で参照する。
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else KNOWLEDGE_PATH
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return _empty_knowledge()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            return _empty_knowledge()
        base = _empty_knowledge()
        base.update({k: v for k, v in data.items() if v is not None})
        return base

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.data, f, allow_unicode=True, sort_keys=False)

    # --- しきい値 ---

    def threshold_overrides(self) -> dict[str, Any]:
        return dict(self.data.get("thresholds") or {})

    def set_thresholds(self, overrides: dict[str, Any]) -> None:
        self.data["thresholds"] = {k: v for k, v in overrides.items() if v is not None}
        self.save()

    # --- 追加キーワード ---

    def extra_keywords(self) -> dict[str, list[str]]:
        raw = self.data.get("extra_keywords") or {}
        return {k: [str(w).strip() for w in (v or []) if str(w).strip()] for k, v in raw.items()}

    def set_extra_keywords(self, category: str, words: list[str]) -> None:
        keywords = self.data.setdefault("extra_keywords", {})
        cleaned = [w.strip() for w in words if w.strip()]
        if cleaned:
            keywords[category] = cleaned
        else:
            keywords.pop(category, None)
        self.save()

    # --- ナレッジノート（マニュアル・規程・判定ルール） ---

    def notes(self) -> list[dict[str, Any]]:
        return list(self.data.get("notes") or [])

    def add_note(
        self,
        title: str,
        content: str,
        category: str = "その他",
        applies_to: str = "all",
        match_keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        note = {
            "id": uuid.uuid4().hex[:12],
            "title": title.strip(),
            "category": category if category in NOTE_CATEGORIES else "その他",
            "applies_to": applies_to if applies_to in NOTE_APPLIES_TO else "all",
            "match_keywords": [w.strip() for w in (match_keywords or []) if w.strip()],
            "content": content.strip(),
            "updated_at": now_local_iso(),
        }
        self.data.setdefault("notes", []).append(note)
        self.save()
        return note

    def delete_note(self, note_id: str) -> bool:
        notes = self.data.get("notes") or []
        remaining = [n for n in notes if n.get("id") != note_id]
        if len(remaining) == len(notes):
            return False
        self.data["notes"] = remaining
        self.save()
        return True

    def relevant_notes(self, contract_text: str) -> list[dict[str, Any]]:
        """契約テキストに関連するノートを返す。

        match_keywords が空のノートは常時適用（全契約共通の判定ルール等）。
        指定がある場合は、いずれかのキーワードが本文に含まれるときだけ適用する。
        """
        applied: list[dict[str, Any]] = []
        for note in self.notes():
            keywords = [w for w in note.get("match_keywords") or [] if w]
            matched = [w for w in keywords if w in contract_text]
            if not keywords or matched:
                applied.append(
                    {
                        "id": note.get("id", ""),
                        "title": note.get("title", ""),
                        "category": note.get("category", ""),
                        "applies_to": note.get("applies_to", "all"),
                        "matched_keywords": matched,
                        "content": note.get("content", ""),
                    }
                )
        return applied
