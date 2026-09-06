from __future__ import annotations

import streamlit as st

from src.knowledge_store import (
    NOTE_APPLIES_TO,
    NOTE_CATEGORIES,
    THRESHOLD_LABELS,
    KnowledgeStore,
)
from src.utils import env, load_environment


st.set_page_config(page_title="管理者設定 | リース会計 契約判定", layout="wide")

KEYWORD_CATEGORY_LABELS = {
    "formal_lease": "形式リース文言（リース・レンタル等）",
    "tangible_assets": "有形資産の物件名",
    "service_like": "サービス性を示す文言",
    "identification": "資産の特定を示す文言",
    "exclusive_use": "専用・独占使用を示す文言",
    "free_substitution": "自由な入替権を示す文言",
    "maintenance_substitution": "保守・故障時交換を示す文言",
    "direction_lessee": "借手の指図権を示す文言",
    "direction_lessor": "貸手の指図を示す文言",
    "real_estate": "不動産を示す文言",
}


def main() -> None:
    st.title("管理者設定")
    st.caption("判定エンジンが参照する社内ナレッジ（判定ルール・マニュアル・規程）としきい値を設定します。")

    if not _check_admin_access():
        return

    store = KnowledgeStore()
    tab_notes, tab_thresholds, tab_keywords = st.tabs(
        ["ナレッジ（マニュアル・規程・判定ルール）", "判定しきい値", "判定キーワード"]
    )
    with tab_notes:
        _render_notes_tab(store)
    with tab_thresholds:
        _render_thresholds_tab(store)
    with tab_keywords:
        _render_keywords_tab(store)


def _check_admin_access() -> bool:
    load_environment()
    passcode = env("ADMIN_PASSCODE")
    if not passcode:
        st.info("デモモード: ADMIN_PASSCODE が未設定のため、認証なしで管理者設定を開いています。本番運用では必ず設定してください。")
        return True
    if st.session_state.get("admin_authenticated"):
        return True
    with st.form("admin_login"):
        entered = st.text_input("管理者パスコード", type="password")
        if st.form_submit_button("ログイン"):
            if entered == passcode:
                st.session_state["admin_authenticated"] = True
                st.rerun()
            else:
                st.error("パスコードが一致しません。")
    return False


def _render_notes_tab(store: KnowledgeStore) -> None:
    st.subheader("ナレッジの登録")
    st.caption(
        "登録したナレッジは判定結果画面の「参照した社内ナレッジ」に表示され、"
        "LLMプロバイダー利用時は判定プロンプトへ注入されます。"
        "一致キーワードを空にすると全契約に適用されます。"
    )
    with st.form("add_note", clear_on_submit=True):
        title = st.text_input("タイトル", placeholder="例: 少額リースの社内取扱い")
        c1, c2 = st.columns(2)
        category = c1.selectbox("分類", NOTE_CATEGORIES)
        applies_to = c2.selectbox(
            "適用対象ステップ",
            NOTE_APPLIES_TO,
            format_func=lambda v: {"all": "全ステップ", "step1": "Step1（事前確認）", "step2": "Step2（リース識別）", "step3": "Step3（分類）"}[v],
        )
        match_keywords = st.text_input(
            "一致キーワード（読点・カンマ区切り、空欄なら全契約に適用）",
            placeholder="例: 複合機、コピー機、プリンター",
        )
        content = st.text_area("内容（社内マニュアル・規程・判定ルールの本文）", height=160)
        upload = st.file_uploader("またはテキストファイルから読み込み（.txt / .md）", type=["txt", "md"])
        if st.form_submit_button("ナレッジを追加", type="primary"):
            body = content.strip()
            if upload is not None and not body:
                body = upload.getvalue().decode("utf-8", errors="replace").strip()
            if not title.strip() or not body:
                st.error("タイトルと内容を入力してください。")
            else:
                keywords = [w.strip() for w in match_keywords.replace("、", ",").replace("，", ",").split(",") if w.strip()]
                store.add_note(title, body, category=category, applies_to=applies_to, match_keywords=keywords)
                st.success("ナレッジを追加しました。次回の判定から参照されます。")
                st.rerun()

    notes = store.notes()
    st.subheader(f"登録済みナレッジ（{len(notes)}件）")
    if not notes:
        st.write("まだナレッジが登録されていません。")
    for note in notes:
        keywords = note.get("match_keywords") or []
        scope = "、".join(keywords) if keywords else "全契約に適用"
        with st.expander(f"[{note.get('category', '')}] {note.get('title', '')} — {scope}"):
            st.caption(f"適用対象: {note.get('applies_to', 'all')} / 更新: {note.get('updated_at', '')}")
            st.write(note.get("content", ""))
            if st.button("削除", key=f"delete_note_{note.get('id')}"):
                store.delete_note(note.get("id", ""))
                st.rerun()


def _render_thresholds_tab(store: KnowledgeStore) -> None:
    st.subheader("判定しきい値の調整")
    st.caption("標準値は config/judgment_rules.yaml に定義されています。ここでの設定が標準値を上書きします。")
    from src.utils import PROJECT_ROOT, load_yaml

    defaults = load_yaml(PROJECT_ROOT / "config" / "judgment_rules.yaml").get("thresholds", {})
    overrides = store.threshold_overrides()

    with st.form("thresholds"):
        short_term = st.number_input(
            THRESHOLD_LABELS["short_term_months"],
            min_value=1,
            max_value=24,
            value=int(overrides.get("short_term_months", defaults.get("short_term_months", 1))),
        )
        low_value = st.number_input(
            THRESHOLD_LABELS["low_value_asset_jpy"],
            min_value=0,
            max_value=100_000_000,
            step=10_000,
            value=int(overrides.get("low_value_asset_jpy", defaults.get("low_value_asset_jpy", 300000))),
        )
        term_ratio = st.number_input(
            THRESHOLD_LABELS["finance_lease_term_ratio"],
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            value=float(overrides.get("finance_lease_term_ratio", defaults.get("finance_lease_term_ratio", 0.75))),
        )
        pv_ratio = st.number_input(
            THRESHOLD_LABELS["finance_pv_ratio"],
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            value=float(overrides.get("finance_pv_ratio", defaults.get("finance_pv_ratio", 0.90))),
        )
        c1, c2 = st.columns([1, 1])
        save = c1.form_submit_button("保存", type="primary")
        reset = c2.form_submit_button("標準値に戻す")

    if save:
        new_overrides = {
            "short_term_months": int(short_term),
            "low_value_asset_jpy": int(low_value),
            "finance_lease_term_ratio": round(float(term_ratio), 4),
            "finance_pv_ratio": round(float(pv_ratio), 4),
        }
        store.set_thresholds({k: v for k, v in new_overrides.items() if v != defaults.get(k)})
        st.success("しきい値を保存しました。次回の判定から適用されます。")
        st.rerun()
    if reset:
        store.set_thresholds({})
        st.success("標準値に戻しました。")
        st.rerun()

    if store.threshold_overrides():
        st.warning("現在、標準値から変更されているしきい値: " + ", ".join(
            f"{THRESHOLD_LABELS.get(k, k)} = {v}" for k, v in store.threshold_overrides().items()
        ))
    else:
        st.info("現在は標準値で判定しています。")


def _render_keywords_tab(store: KnowledgeStore) -> None:
    st.subheader("判定キーワードの追加")
    st.caption(
        "ルールベース判定が契約書から根拠を探すときのキーワードを追加できます。"
        "標準キーワードは config/judgment_rules.yaml に定義されており、ここでの追加分はそれに加算されます。1行1キーワードで入力してください。"
    )
    extra = store.extra_keywords()
    with st.form("keywords"):
        inputs: dict[str, str] = {}
        for category, label in KEYWORD_CATEGORY_LABELS.items():
            inputs[category] = st.text_area(
                label,
                value="\n".join(extra.get(category, [])),
                height=80,
                key=f"kw_{category}",
            )
        if st.form_submit_button("保存", type="primary"):
            for category, raw in inputs.items():
                store.set_extra_keywords(category, raw.splitlines())
            st.success("追加キーワードを保存しました。次回の判定から適用されます。")
            st.rerun()


main()
