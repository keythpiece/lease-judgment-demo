from src.knowledge_store import KnowledgeStore
from src.lease_judgment_engine import LeaseJudgmentEngine


UNKNOWN_SUBSTITUTION_CONTRACT = """
製造設備リース契約書
契約期間 60か月
対象物件: 製造設備 型番 EQ-100 製造番号 EQ-001 設置場所 第1工場 台数 1台
借手は、本物件を自社の製造ラインにおける部品加工および量産加工のために使用するものとする。
借手は、契約期間中、製造計画、稼働時間、加工対象、使用場所を自己の判断で決定することができる。
"""


def judge(text: str, engine: LeaseJudgmentEngine | None = None, user_answers: dict | None = None) -> dict:
    engine = engine or LeaseJudgmentEngine()
    return engine.judge([{"page": 1, "text": text, "source": "text"}], "sample.pdf", user_answers=user_answers)


def test_user_answer_resolves_unknown_and_rejudges_to_lease():
    initial = judge(UNKNOWN_SUBSTITUTION_CONTRACT)
    assert initial["final_result"]["lease_applicability"] == "Human review required"

    rejudged = judge(
        UNKNOWN_SUBSTITUTION_CONTRACT,
        user_answers={"step2": {"substitution_right": {"answer": "No", "note": "貸手に確認済み。交換は故障時のみ。"}}},
    )
    assert rejudged["step2"]["substitution_right"]["answer"] == "No"
    assert rejudged["step2"]["substitution_right"]["answered_by_user"] is True
    assert rejudged["final_result"]["lease_applicability"] == "Lease"
    assert not any(
        g["key"] == "substitution_right" for g in rejudged["final_result"]["human_review_guidance"]
    )
    confirmations = rejudged["audit"]["user_confirmations"]
    assert confirmations and confirmations[0]["original_answer"] == "Unknown"
    assert confirmations[0]["user_answer"] == "No"
    assert "貸手に確認済み" in confirmations[0]["note"]


def test_user_step3_values_enable_finance_classification():
    rejudged = judge(
        UNKNOWN_SUBSTITUTION_CONTRACT,
        user_answers={
            "step2": {"substitution_right": {"answer": "No", "note": ""}},
            "step3": {
                "economic_life_months": 70,
                "fair_value": 10_000_000,
                "fixed_lease_payment": 200_000,
                "notes": {"economic_life_months": "固定資産台帳より"},
            },
        },
    )
    assert rejudged["step3"]["economic_life_months"] == 70
    assert rejudged["step3"]["criterion_1_75_percent_test"]["answer"] == "Yes"
    assert rejudged["final_result"]["lease_classification"] == "Finance lease"


def test_invalid_user_answers_are_ignored():
    rejudged = judge(
        UNKNOWN_SUBSTITUTION_CONTRACT,
        user_answers={"step2": {"substitution_right": {"answer": "Maybe"}, "step2_result": {"answer": "Yes"}}},
    )
    assert rejudged["step2"]["substitution_right"]["answer"] == "Unknown"
    assert rejudged["audit"]["user_confirmations"] == []


def test_knowledge_threshold_override_changes_low_value_judgment(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.yaml")
    store.set_thresholds({"low_value_asset_jpy": 1_000_000})
    engine = LeaseJudgmentEngine(knowledge_store=store)
    assert engine.thresholds["low_value_asset_jpy"] == 1_000_000

    text = """
    複合機リース契約書
    契約期間 60か月
    対象物件: 複合機 型番 MX-9000 台数 1台
    月額リース料 500,000円
    """
    result = judge(text, engine=engine)
    assert result["knowledge_applied"]["threshold_overrides"] == {"low_value_asset_jpy": 1_000_000}
    assert result["step1"]["low_value_assets_only"]["answer"] == "Yes"

    default_result = judge(text, engine=LeaseJudgmentEngine(knowledge_store=KnowledgeStore(tmp_path / "empty.yaml")))
    assert default_result["step1"]["low_value_assets_only"]["answer"] == "No"


def test_knowledge_notes_match_contract_text(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.yaml")
    store.add_note(
        "複合機マニュアル",
        "カウンター料金契約は機器部分を分離して判定する。",
        category="社内マニュアル",
        match_keywords=["複合機"],
    )
    store.add_note("全社共通ルール", "最終判断は経理部承認を要する。", category="規程", match_keywords=[])
    engine = LeaseJudgmentEngine(knowledge_store=store)

    matched = judge("複合機リース契約書 契約期間 60か月", engine=engine)
    titles = [n["title"] for n in matched["knowledge_applied"]["notes"]]
    assert titles == ["複合機マニュアル", "全社共通ルール"]

    unmatched = judge("車両リース契約書 契約期間 36か月", engine=engine)
    titles = [n["title"] for n in unmatched["knowledge_applied"]["notes"]]
    assert titles == ["全社共通ルール"]


def test_extra_keywords_extend_rule_dictionary(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.yaml")
    store.set_extra_keywords("tangible_assets", ["特注検査ロボット"])
    engine = LeaseJudgmentEngine(knowledge_store=store)
    assert "特注検査ロボット" in engine.keywords["tangible_assets"]

    result = judge(
        """
        設備使用契約書
        対象物件: 特注検査ロボット 型番 RB-1 管理番号 R-001 設置場所 検査棟
        利用者は本物件を専用かつ独占して使用し、使用場所および使用目的を利用者が決定する。
        交換は故障または保守の場合に限る。
        契約期間 48か月
        """,
        engine=engine,
    )
    assert result["step2"]["asset_item_assessment"]["answer"] == "Yes"
