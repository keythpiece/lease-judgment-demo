from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"


def load_environment() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def now_local_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_filename(name: str, fallback: str = "contract") -> str:
    stem = Path(name or fallback).stem
    stem = re.sub(r'[\\/:*?"<>|]+', "_", stem).strip(" ._")
    return stem or fallback


def ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_json(data: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return target


def chunks(text: str, max_chars: int = 12000, overlap: int = 600) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        parts.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return parts


def flatten_evidence(result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for section_name in ("step1", "step2"):
        section = result.get(section_name, {})
        for key, value in section.items():
            if isinstance(value, dict):
                for ev in value.get("evidence", []) or []:
                    row = dict(ev)
                    row["source_item"] = key
                    items.append(row)
    items.extend(result.get("final_result", {}).get("key_evidence", []) or [])
    seen: set[tuple[Any, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        token = (item.get("page"), item.get("text", ""))
        if token not in seen and item.get("text"):
            unique.append(item)
            seen.add(token)
    return unique


def first_non_empty(values: Iterable[Any], default: Any = "") -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return default


def env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        try:
            import streamlit as st

            value = st.secrets.get(name)  # type: ignore[assignment]
        except Exception:
            value = None
    return str(value if value is not None else default).strip()
