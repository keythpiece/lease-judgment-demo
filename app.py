from __future__ import annotations

import tempfile
from copy import deepcopy
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.display import display_text, display_value
from src.excel_writer import write_excel_assessment
from src.lease_judgment_engine import LeaseJudgmentEngine
from src.llm_client import build_llm_client
from src.pdf_highlighter import highlight_pdf
from src.pdf_reader import PDFReader
from src.report_writer import write_pdf_report
from src.utils import ensure_output_dir, safe_filename, save_json


st.set_page_config(page_title="リース会計 契約判定プロトタイプ", layout="wide")


def main() -> None:
    st.title("リース会計 契約判定プロトタイプ")
    st.caption("契約書PDFをローカルで読み取り、リース識別・分類の一次判定JSONを生成します。")
    st.warning(
        "デモ版です。実際の契約書、機密情報、個人情報、取引先を特定できる情報はアップロードしないでください。"
        "Copilot等で作成した合成サンプル、または十分に匿名化・架空化した資料のみ使用してください。"
    )

    with st.sidebar:
        st.header("設定")
        provider = _select_with_labels(
            "LLMプロバイダー",
            {"ルールベース（現行）": "rule_based", "OpenAI（検証用）": "openai"},
        )
        if provider == "openai":
            st.warning("OpenAI検証用です。抽出した契約書テキストがOpenAI APIへ送信されます。実契約書はアップロードしないでください。")
        ocr_engine = _select_with_labels("OCRエンジン", {"なし": "none", "Tesseract": "tesseract"})
        template_upload = st.file_uploader("任意: 既存Excelテンプレート", type=["xlsx"])
        st.info(
            "APIキーはローカルでは .env、Streamlit Community Cloudでは Secrets から読み込みます。"
            "デモ版では実契約書をアップロードしないでください。"
        )

    uploaded = st.file_uploader("契約書PDF", type=["pdf"])
    col_run, col_clear = st.columns([1, 5])
    with col_run:
        run = st.button("判定実行", type="primary", disabled=uploaded is None)
    with col_clear:
        if st.button("結果クリア"):
            st.session_state.clear()
            st.rerun()

    if uploaded and run:
        with st.spinner("PDFを読み取り、判定しています..."):
            tmp_pdf = _write_temp(uploaded.getvalue(), suffix=".pdf")
            try:
                reader = PDFReader()
                if ocr_engine != "none":
                    from src.ocr_reader import build_ocr_reader

                    reader = PDFReader(build_ocr_reader(ocr_engine))
                pages = reader.read(tmp_pdf)
                try:
                    llm_client = build_llm_client(provider)
                except Exception as exc:
                    st.error(f"LLMプロバイダーを初期化できませんでした: {exc}")
                    return
                result = LeaseJudgmentEngine(llm_client=llm_client).judge(pages, uploaded.name)
                st.session_state["result"] = result
                st.session_state["pages"] = pages
                st.session_state["provider"] = provider
                st.session_state["user_answers"] = {}
                st.session_state["judgment_round"] = 1
                st.session_state["pdf_bytes"] = uploaded.getvalue()
                st.session_state["pdf_name"] = uploaded.name
                st.session_state["template_bytes"] = template_upload.getvalue() if template_upload else None
            finally:
                Path(tmp_pdf).unlink(missing_ok=True)

    result = st.session_state.get("result")
    if result:
        _render_summary(result)
        _render_knowledge_applied(result)
        _render_clarification_form(result)
        _render_llm_assessment(result)
        _render_step_table(result)
        _render_evidence(result)
        _render_outputs(result)


def _select_with_labels(label: str, options: dict[str, str]) -> str:
    selected_label = st.selectbox(label, list(options.keys()), index=0)
    return options[selected_label]


def _render_summary(result: dict[str, Any]) -> None:
    final = result.get("final_result", {})
    guidance = final.get("human_review_guidance", []) or []
    has_review_items = bool(guidance or final.get("missing_information"))

    st.subheader("判定サマリー")
    _summary_styles()
    c1, c2, c3, c4 = st.columns([1.0, 1.35, 0.65, 0.9])
    _summary_value(c1, "リース対象判定", display_value(final.get("lease_applicability", "")))
    _summary_value(c2, "リース分類", display_value(final.get("lease_classification", "")))
    _summary_value(c3, "信頼度", display_value(final.get("confidence", "")))
    _summary_value(c4, "確認状態", "確認事項あり" if has_review_items else "確認不要")

    if guidance:
        st.warning("暫定判定です。上記のリース対象判定・リース分類は、現在読み取れた根拠に基づく一次判定です。Step別判定表の「要確認」を確認してください。")
        items = "、".join(item.get("item", "") for item in guidance[:5] if item.get("item"))
        st.warning(f"確認必要: {items}")
        first = guidance[0]
        st.info(f"次に確認: {first.get('item', '')} - {first.get('short_check', first.get('question', ''))}")
        st.caption(_branch_summary(first))
    elif final.get("missing_information"):
        st.warning("暫定判定です。上記のリース対象判定・リース分類は、現在読み取れた根拠に基づく一次判定です。表示された不足情報を確認してください。")
        st.warning("確認必要: " + "、".join(final.get("missing_information", [])))

    st.write(display_text(final.get("summary_reason", "")))
    _render_human_review_guidance(guidance)


def _summary_styles() -> None:
    st.markdown(
        """
        <style>
        .lease-summary-label {
            font-size: 0.92rem;
            line-height: 1.35;
            color: #334155;
            margin-bottom: 0.25rem;
        }
        .lease-summary-value {
            font-size: 2.05rem;
            font-weight: 500;
            line-height: 1.2;
            color: #111827;
            word-break: keep-all;
            overflow-wrap: anywhere;
            white-space: normal;
        }
        .lease-summary-value.long-value {
            font-size: 1.55rem;
            line-height: 1.25;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _summary_value(column: Any, label: str, value: Any) -> None:
    value_text = "" if value is None else str(value)
    value_class = "lease-summary-value long-value" if len(value_text) >= 9 else "lease-summary-value"
    column.markdown(
        f"""
        <div class="lease-summary-label">{escape(label)}</div>
        <div class="{value_class}">{escape(value_text)}</div>
        """,
        unsafe_allow_html=True,
    )


def _render_human_review_guidance(guidance: list[dict[str, Any]]) -> None:
    if not guidance:
        return
    st.subheader("人手確認ガイド")
    rows = []
    for item in guidance:
        rows.append(
            {
                "Step": item.get("step", ""),
                "確認項目": item.get("item", ""),
                "確認すること": item.get("short_check", ""),
                "Yesなら": item.get("if_yes_result", ""),
                "Noなら": item.get("if_no_result", ""),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander("確認ガイドの詳細を開く"):
        for item in guidance:
            st.markdown(f"**{item.get('item', '')}: {item.get('short_check', '')}**")
            st.write(item.get("question", ""))
            st.caption("確認方法: " + item.get("how_to_check", ""))
            cols = st.columns(2)
            cols[0].success(f"Yes -> {item.get('if_yes_result', '')}")
            cols[0].write(item.get("if_yes", ""))
            cols[1].warning(f"No -> {item.get('if_no_result', '')}")
            cols[1].write(item.get("if_no", ""))
            st.divider()


def _render_knowledge_applied(result: dict[str, Any]) -> None:
    knowledge = result.get("knowledge_applied") or {}
    notes = knowledge.get("notes") or []
    overrides = knowledge.get("threshold_overrides") or {}
    if not notes and not overrides:
        return
    with st.expander(f"参照した社内ナレッジ（{len(notes)}件）と判定ルール調整", expanded=False):
        if overrides:
            st.caption("管理者設定により、以下のしきい値を標準値から変更して判定しています。")
            st.json(overrides)
        for note in notes:
            matched = note.get("matched_keywords") or []
            match_label = f"（一致キーワード: {'、'.join(matched)}）" if matched else "（全契約に適用）"
            st.markdown(f"**[{note.get('category', '')}] {note.get('title', '')}** {match_label}")
            st.write(note.get("content", ""))
            st.divider()
        st.caption("ナレッジは管理者設定ページで追加・編集できます。LLMプロバイダー利用時は判定プロンプトにも注入されます。")


_STEP2_ANSWER_OPTIONS: dict[str, list[tuple[str, str | None]]] = {
    "right_to_direct_use": [
        ("未回答（不明のまま）", None),
        ("借手・利用者が使用方法・目的を決定する", "Lessee"),
        ("貸手・提供者が決定し、利用者は成果のみ受け取る", "Lessor"),
        ("契約開始前に使用方法が固定され、双方変更できない", "Neither"),
    ],
    "asset_type": [
        ("未回答（不明のまま）", None),
        ("動産（機器・車両・設備等）", "Movable"),
        ("不動産（建物・土地等）", "RealEstate"),
    ],
}

_STEP3_NUMERIC_FIELDS = {
    "economic_life_months": ("経済的耐用年数（か月）", 1, 1200),
    "fair_value": ("原資産の公正価値（円）", 1, 100_000_000_000),
    "fixed_lease_payment": ("固定リース料 月額（円）", 1, 10_000_000_000),
}


def _render_clarification_form(result: dict[str, Any]) -> None:
    guidance = result.get("final_result", {}).get("human_review_guidance", []) or []
    confirmations = result.get("audit", {}).get("user_confirmations", []) or []

    if confirmations:
        with st.expander(f"これまでの追加確認の回答履歴（{len(confirmations)}件）"):
            rows = [
                {
                    "Step": c.get("step", ""),
                    "項目": c.get("key", ""),
                    "AI初期判定": display_value(c.get("original_answer", "")),
                    "回答": display_value(c.get("user_answer", "")),
                    "補足": c.get("note", ""),
                    "回答日時": c.get("answered_at", ""),
                }
                for c in confirmations
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)

    if not guidance:
        if confirmations:
            st.success("追加確認はすべて回答済みです。上記の判定は回答を反映した再判定結果です。")
        return

    st.subheader("追加確認と再判定")
    st.caption(
        "契約書だけでは判定できなかった項目です。分かる範囲で回答して「回答を反映して再判定」を押すと、"
        "回答を反映した再判定を行います。未回答のままでも構いません。回答は判定JSONに監査証跡として記録されます。"
    )

    with st.form("clarification_form"):
        step2_widgets: dict[str, str] = {}
        step3_present = False
        for item in guidance:
            key = item.get("key", "")
            step = item.get("step", "")
            st.markdown(f"**{item.get('item', '')}**: {item.get('question', '')}")
            if item.get("how_to_check"):
                st.caption("確認方法: " + item.get("how_to_check", ""))
            if step == "Step2":
                options = _STEP2_ANSWER_OPTIONS.get(key) or [
                    ("未回答（不明のまま）", None),
                    (f"はい → {item.get('if_yes_result', '')}", "Yes"),
                    (f"いいえ → {item.get('if_no_result', '')}", "No"),
                ]
                labels = [label for label, _ in options]
                st.radio("回答", labels, index=0, key=f"clarify_{key}", horizontal=True, label_visibility="collapsed")
                step2_widgets[key] = "answered"
            elif key in _STEP3_NUMERIC_FIELDS:
                label, min_v, max_v = _STEP3_NUMERIC_FIELDS[key]
                st.number_input(label, min_value=0, max_value=max_v, value=0, step=1, key=f"clarify_num_{key}", help="0のままなら未回答として扱います。")
                step3_present = True
            st.text_input("補足（任意・自由記述）", key=f"clarify_note_{key}", placeholder="根拠資料名、社内確認先、判断メモなど")
            st.divider()
        if step3_present:
            st.number_input(
                "割引率（年利%・任意）",
                min_value=0.0,
                max_value=50.0,
                value=0.0,
                step=0.1,
                key="clarify_num_discount_rate",
                help="90%現在価値テストに使用します。0のままなら割引なしで計算します。",
            )
        submitted = st.form_submit_button("回答を反映して再判定", type="primary")

    if submitted:
        new_answers = _collect_form_answers(guidance)
        if not _has_any_answer(new_answers):
            st.info("回答が入力されていません。少なくとも1項目に回答するか、数値を入力してください。")
            return
        _rejudge_with_answers(new_answers)


def _collect_form_answers(guidance: list[dict[str, Any]]) -> dict[str, Any]:
    answers: dict[str, Any] = {"step2": {}, "step3": {"notes": {}}}
    for item in guidance:
        key = item.get("key", "")
        note = str(st.session_state.get(f"clarify_note_{key}", "")).strip()
        if item.get("step") == "Step2":
            options = _STEP2_ANSWER_OPTIONS.get(key) or [
                ("未回答（不明のまま）", None),
                (f"はい → {item.get('if_yes_result', '')}", "Yes"),
                (f"いいえ → {item.get('if_no_result', '')}", "No"),
            ]
            selected_label = st.session_state.get(f"clarify_{key}")
            value = dict(options).get(selected_label)
            if value:
                answers["step2"][key] = {"answer": value, "note": note}
        elif key in _STEP3_NUMERIC_FIELDS:
            value = st.session_state.get(f"clarify_num_{key}", 0)
            if value:
                answers["step3"][key] = int(value)
                if note:
                    answers["step3"]["notes"][key] = note
    rate = st.session_state.get("clarify_num_discount_rate", 0.0)
    if rate:
        answers["step3"]["discount_rate"] = float(rate) / 100
    return answers


def _has_any_answer(answers: dict[str, Any]) -> bool:
    step3 = {k: v for k, v in answers.get("step3", {}).items() if k != "notes"}
    return bool(answers.get("step2")) or bool(step3)


def _rejudge_with_answers(new_answers: dict[str, Any]) -> None:
    pages = st.session_state.get("pages")
    if not pages:
        st.error("契約書の読み取り結果が見つかりません。もう一度PDFをアップロードして判定してください。")
        return
    merged = st.session_state.get("user_answers") or {"step2": {}, "step3": {"notes": {}}}
    merged.setdefault("step2", {}).update(new_answers.get("step2", {}))
    step3_merged = merged.setdefault("step3", {"notes": {}})
    for k, v in new_answers.get("step3", {}).items():
        if k == "notes":
            step3_merged.setdefault("notes", {}).update(v)
        else:
            step3_merged[k] = v
    with st.spinner("回答を反映して再判定しています..."):
        try:
            llm_client = build_llm_client(st.session_state.get("provider", "rule_based"))
        except Exception as exc:
            st.error(f"LLMプロバイダーを初期化できませんでした: {exc}")
            return
        result = LeaseJudgmentEngine(llm_client=llm_client).judge(
            pages,
            st.session_state.get("pdf_name", ""),
            user_answers=merged,
        )
    st.session_state["user_answers"] = merged
    st.session_state["result"] = result
    st.session_state["judgment_round"] = st.session_state.get("judgment_round", 1) + 1
    for key in [k for k in st.session_state if str(k).startswith("clarify_")]:
        del st.session_state[key]
    st.rerun()


def _render_llm_assessment(result: dict[str, Any]) -> None:
    assessment = result.get("llm_assessment")
    if not assessment:
        return

    st.subheader("OpenAI補助判定（検証用）")
    if assessment.get("error"):
        st.error(f"OpenAI補助判定でエラーが発生しました: {assessment.get('error')}")
        return

    provider = assessment.get("provider", "openai")
    model = assessment.get("model", "")
    st.caption(f"provider: {provider} / model: {model}")

    final = assessment.get("final_result", {}) or {}
    c1, c2, c3 = st.columns(3)
    _summary_value(c1, "OpenAI リース対象", display_value(final.get("lease_applicability", "")))
    _summary_value(c2, "OpenAI リース分類", display_value(final.get("lease_classification", "")))
    _summary_value(c3, "OpenAI 信頼度", display_value(final.get("confidence", "")))
    if final.get("summary_reason"):
        st.write(display_text(final.get("summary_reason", "")))

    rows = []
    for item in assessment.get("step_results", []) or []:
        evidence = item.get("evidence", []) or []
        rows.append(
            {
                "Step": item.get("step", ""),
                "判定項目": item.get("item", ""),
                "OpenAI判定": display_value(item.get("answer", "")),
                "理由": _short_reason(item.get("reason", ""), 80),
                "根拠ページ": ", ".join(str(ev.get("page")) for ev in evidence if ev.get("page")),
            }
        )
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander("OpenAI補助判定のJSONを開く"):
        st.json(_translated_result(assessment))


def _render_step_table(result: dict[str, Any]) -> None:
    st.subheader("Step別判定表")
    rows = []
    labels = {
        "contract_period_within_one_month": "契約期間1か月以内",
        "obvious_lease_contract": "リース等の文言",
        "low_value_assets_only": "少額資産のみ",
        "formal_assessment": "形式判定",
        "asset_item_assessment": "取引アイテム判定",
        "identified_asset": "資産の特定",
        "substitution_right": "入替権",
        "economic_benefits": "経済的便益",
        "right_to_direct_use": "指図権",
        "operation_right_or_design_involvement": "稼働権・設計関与",
        "asset_type": "資産種別",
    }
    guidance_by_key = {
        item.get("key"): item for item in result.get("final_result", {}).get("human_review_guidance", [])
    }
    for step_name in ("step1", "step2"):
        for key, item in result.get(step_name, {}).items():
            if not isinstance(item, dict):
                continue
            evidence = item.get("evidence", []) or []
            guidance = guidance_by_key.get(key) or {}
            needs_review = item.get("answer") == "Unknown" or bool(guidance)
            rows.append(
                {
                    "状態": "要確認" if needs_review else "OK",
                    "Step": step_name.replace("step", "Step"),
                    "判定項目": labels.get(key, key),
                    "AI判定": display_value(item.get("answer", "")),
                    "判断理由": _short_reason(item.get("reason", "")),
                    "次に確認": guidance.get("short_check", "確認不要" if not needs_review else "契約条項"),
                    "確認後の分岐": _branch_summary(guidance) if guidance else "",
                    "根拠ページ": ", ".join(str(ev.get("page")) for ev in evidence if ev.get("page")),
                    "_needs_review": needs_review,
                    "_detail": {
                        "key": key,
                        "label": labels.get(key, key),
                        "reason": item.get("reason", ""),
                        "evidence": evidence,
                        "guidance": guidance,
                    },
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        return

    visible_df = df.drop(columns=["_needs_review", "_detail"])
    styled = visible_df.style.apply(
        lambda row: ["background-color: #fff6bf" if df.loc[row.name, "_needs_review"] else "" for _ in row],
        axis=1,
    )
    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "状態": st.column_config.TextColumn(width="small"),
            "Step": st.column_config.TextColumn(width="small"),
            "判定項目": st.column_config.TextColumn(width="medium"),
            "AI判定": st.column_config.TextColumn(width="small"),
            "判断理由": st.column_config.TextColumn(width="large"),
            "次に確認": st.column_config.TextColumn(width="medium"),
            "確認後の分岐": st.column_config.TextColumn(width="large"),
            "根拠ページ": st.column_config.TextColumn(width="small"),
        },
    )

    review_details = [row["_detail"] for row in rows if row["_needs_review"]]
    if review_details:
        with st.expander("Step別判定の詳細を開く"):
            for detail in review_details:
                guidance = detail.get("guidance")
                st.markdown(f"**{detail.get('label', '')}**")
                st.write(detail.get("reason", ""))
                if guidance:
                    st.info(guidance.get("question", ""))
                    cols = st.columns(2)
                    cols[0].success(f"Yes -> {guidance.get('if_yes_result', '')}")
                    cols[0].write(guidance.get("if_yes", ""))
                    cols[1].warning(f"No -> {guidance.get('if_no_result', '')}")
                    cols[1].write(guidance.get("if_no", ""))
                evidence = detail.get("evidence", []) or []
                if evidence:
                    st.caption("根拠候補")
                    for ev in evidence[:3]:
                        st.markdown(f"- p.{ev.get('page')}: {ev.get('text', '')}")
                st.divider()


def _branch_summary(guidance: dict[str, Any] | None) -> str:
    if not guidance:
        return ""
    yes_result = guidance.get("if_yes_result", "")
    no_result = guidance.get("if_no_result", "")
    if yes_result or no_result:
        return f"Yes -> {yes_result} / No -> {no_result}"
    return ""


def _short_reason(reason: str, max_chars: int = 54) -> str:
    reason = (reason or "").strip()
    if len(reason) <= max_chars:
        return reason
    return reason[: max_chars - 1] + "..."


def _render_evidence(result: dict[str, Any]) -> None:
    st.subheader("根拠表示")
    for ev in result.get("final_result", {}).get("key_evidence", []):
        st.markdown(f"**p.{ev.get('page')}** {ev.get('text', '')}")


def _render_outputs(result: dict[str, Any]) -> None:
    st.subheader("出力")
    output_dir = ensure_output_dir()
    original = st.session_state.get("pdf_name", "contract.pdf")
    stem = safe_filename(original)
    pdf_bytes = st.session_state.get("pdf_bytes", b"")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("判定結果PDFを出力"):
            path = output_dir / f"{stem}_lease_report.pdf"
            write_pdf_report(result, path)
            st.download_button("PDFをダウンロード", path.read_bytes(), file_name=path.name, mime="application/pdf")
    with col2:
        if st.button("ハイライト済みPDFを出力"):
            tmp_pdf = _write_temp(pdf_bytes, suffix=".pdf")
            try:
                path = output_dir / f"{stem}_highlighted.pdf"
                status = highlight_pdf(tmp_pdf, result, path)
                misses = [s for s in status["status"] if not s["highlighted"]]
                if misses:
                    st.warning(f"ハイライト未検出: {len(misses)}件")
                st.download_button("PDFをダウンロード", path.read_bytes(), file_name=path.name, mime="application/pdf")
            finally:
                Path(tmp_pdf).unlink(missing_ok=True)
    with col3:
        if st.button("Excel判定シートへ転記して出力"):
            template_path = None
            if st.session_state.get("template_bytes"):
                template_path = _write_temp(st.session_state["template_bytes"], suffix=".xlsx")
            try:
                path = output_dir / f"{stem}_lease_assessment.xlsx"
                write_excel_assessment(result, path, template_path=template_path)
                st.download_button(
                    "Excelをダウンロード",
                    path.read_bytes(),
                    file_name=path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            finally:
                if template_path:
                    Path(template_path).unlink(missing_ok=True)
    with col4:
        if st.button("JSONを出力"):
            path = output_dir / f"{stem}_judgment.json"
            save_json(result, path)
            st.download_button("JSONをダウンロード", path.read_bytes(), file_name=path.name, mime="application/json")

    with st.expander("判定JSON（画面表示用）"):
        st.json(_translated_result(result))


def _translated_result(result: dict[str, Any]) -> dict[str, Any]:
    translated = deepcopy(result)
    _walk_translate(translated)
    return translated


def _walk_translate(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str):
                value[key] = display_value(item)
            else:
                _walk_translate(item)
    elif isinstance(value, list):
        for item in value:
            _walk_translate(item)


def _write_temp(data: bytes, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    f.write(data)
    f.close()
    return f.name


if __name__ == "__main__":
    main()
