from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .display import display_text, display_value
from .utils import flatten_evidence


def write_pdf_report(result: dict[str, Any], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "Japanese",
        parent=styles["BodyText"],
        fontName="HeiseiKakuGo-W5",
        fontSize=9,
        leading=13,
    )
    title_style = ParagraphStyle(
        "TitleJa",
        parent=base,
        fontSize=16,
        leading=20,
        spaceAfter=8,
    )
    heading = ParagraphStyle(
        "HeadingJa",
        parent=base,
        fontSize=12,
        leading=16,
        spaceBefore=8,
        spaceAfter=5,
    )
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    story: list[Any] = []
    summary = result.get("contract_summary", {})
    final = result.get("final_result", {})
    audit = result.get("audit", {})
    story.append(Paragraph("リース会計 一次判定レポート", title_style))
    story.append(
        _kv_table(
            [
                ["契約書名", summary.get("contract_title") or audit.get("input_pdf_name", "")],
                ["判定日", audit.get("judged_at", "")],
                ["最終判定", display_value(final.get("lease_applicability", ""))],
                ["リース分類", display_value(final.get("lease_classification", ""))],
                ["信頼度", display_value(final.get("confidence", ""))],
                ["判断要約", display_text(final.get("summary_reason", ""))],
            ],
            base,
        )
    )
    for section_name, title in [("step1", "Step1 判定結果"), ("step2", "Step2 判定結果")]:
        story.append(Paragraph(title, heading))
        story.append(_section_table(result.get(section_name, {}), base))
    story.append(Paragraph("Step3 判定結果", heading))
    story.append(
        _kv_table(
            [
                ["リース期間（月）", result.get("step3", {}).get("lease_term_months")],
                ["解約不能期間（月）", result.get("step3", {}).get("non_cancellable_period_months")],
                ["経済的耐用年数（月）", result.get("step3", {}).get("economic_life_months")],
                ["公正価値", result.get("step3", {}).get("fair_value")],
                ["75%テスト", result.get("step3", {}).get("criterion_1_75_percent_test", {}).get("reason", "")],
                ["90%PVテスト", result.get("step3", {}).get("criterion_2_90_percent_pv_test", {}).get("reason", "")],
                ["分類結果", display_value(result.get("step3", {}).get("classification_result", ""))],
            ],
            base,
        )
    )
    story.append(Paragraph("判断根拠・契約書引用一覧", heading))
    story.append(_evidence_table(flatten_evidence(result), base))
    story.append(Paragraph("不足情報・要人手確認事項", heading))
    missing = final.get("missing_information", []) or ["なし"]
    story.append(Paragraph(_safe("、".join(map(str, missing))), base))
    guidance = final.get("human_review_guidance", []) or []
    if guidance:
        story.append(Paragraph("人手確認ガイド", heading))
        story.append(_guidance_table(guidance, base))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "注意: 本結果は契約書PDFに基づく一次判定であり、最終的な会計判断は会社の会計方針および専門部署の確認に従ってください。",
            base,
        )
    )
    doc.build(story)
    return output_path


def _kv_table(rows: list[list[Any]], style: ParagraphStyle) -> Table:
    data = [[Paragraph(_safe(k), style), Paragraph(_safe(v), style)] for k, v in rows]
    table = Table(data, colWidths=[42 * mm, 138 * mm])
    table.setStyle(_table_style())
    return table


def _section_table(section: dict[str, Any], style: ParagraphStyle) -> Table:
    rows = [["項目", "判定", "理由", "根拠ページ"]]
    for key, value in section.items():
        if not isinstance(value, dict):
            continue
        pages = ", ".join(str(ev.get("page")) for ev in value.get("evidence", []) if ev.get("page"))
        rows.append([key, display_value(value.get("answer", "")), value.get("reason", ""), pages])
    data = [[Paragraph(_safe(cell), style) for cell in row] for row in rows]
    table = Table(data, colWidths=[42 * mm, 24 * mm, 88 * mm, 26 * mm], repeatRows=1)
    table.setStyle(_table_style(header=True))
    return table


def _evidence_table(evidence_items: list[dict[str, Any]], style: ParagraphStyle) -> Table:
    rows = [["ページ", "項目", "根拠テキスト", "状態"]]
    for ev in evidence_items or []:
        rows.append(
            [
                ev.get("page", ""),
                ev.get("source_item", ""),
                ev.get("text", ""),
                "ハイライト対象" if ev.get("highlight_required", True) else "",
            ]
        )
    if len(rows) == 1:
        rows.append(["", "", "根拠引用が検出されていません。", ""])
    data = [[Paragraph(_safe(cell), style) for cell in row] for row in rows]
    table = Table(data, colWidths=[18 * mm, 38 * mm, 120 * mm, 24 * mm], repeatRows=1)
    table.setStyle(_table_style(header=True))
    return table


def _guidance_table(guidance_items: list[dict[str, Any]], style: ParagraphStyle) -> Table:
    rows = [["確認項目", "何を確認するか", "Yesの場合", "Noの場合"]]
    for item in guidance_items:
        rows.append(
            [
                item.get("item", ""),
                item.get("question", ""),
                item.get("if_yes", ""),
                item.get("if_no", ""),
            ]
        )
    data = [[Paragraph(_safe(cell), style) for cell in row] for row in rows]
    table = Table(data, colWidths=[28 * mm, 72 * mm, 50 * mm, 50 * mm], repeatRows=1)
    table.setStyle(_table_style(header=True))
    return table


def _table_style(header: bool = False) -> TableStyle:
    commands = [
        ("FONTNAME", (0, 0), (-1, -1), "HeiseiKakuGo-W5"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")))
    return TableStyle(commands)


def _safe(value: Any) -> str:
    return html.escape("" if value is None else str(value))
