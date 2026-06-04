from __future__ import annotations

import math
import re
from datetime import date
from pathlib import Path
from typing import Any

from .evidence_extractor import any_keyword, find_keyword_evidence
from .llm_client import LLMClient, build_llm_client
from .schemas import empty_result
from .utils import load_yaml, now_local_iso


class LeaseJudgmentEngine:
    def __init__(
        self,
        rules_path: str | Path | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        base = Path(__file__).resolve().parents[1]
        self.rules = load_yaml(rules_path or base / "config" / "judgment_rules.yaml")
        self.keywords = self.rules.get("keywords", {})
        self.thresholds = self.rules.get("thresholds", {})
        self.llm_client = llm_client or build_llm_client()

    def judge(self, pages: list[dict[str, Any]], input_pdf_name: str = "") -> dict[str, Any]:
        result = empty_result()
        result["audit"]["input_pdf_name"] = input_pdf_name
        result["audit"]["judged_at"] = now_local_iso()
        text = "\n".join(str(p.get("text", "")) for p in pages)
        result["contract_summary"] = self._extract_summary(pages, text)
        self._judge_step1(result, pages, text)
        self._judge_step2(result, pages, text)
        self._judge_step3(result, pages, text)
        self._finalize(result)
        self._attach_llm_assessment(result, pages, text)
        return result

    def _attach_llm_assessment(self, result: dict[str, Any], pages: list[dict[str, Any]], text: str) -> None:
        provider = getattr(self.llm_client, "provider", "rule_based")
        result["audit"]["engine"] = provider
        result["audit"]["model"] = getattr(self.llm_client, "model", "")
        if provider == "rule_based":
            return

        prompt = self._build_llm_prompt(result, pages, text)
        schema_hint = {
            "final_result": {
                "lease_applicability": "Lease / Non-lease / Human review required",
                "lease_classification": "Finance lease / Operating lease / Not applicable / Unknown",
                "confidence": "High / Medium / Low",
                "summary_reason": "",
            },
            "step_results": [
                {
                    "step": "Step2-3",
                    "item": "資産の特定",
                    "answer": "Yes / No / Unknown / Lessee / Lessor / Neither",
                    "reason": "",
                    "evidence": [{"page": 1, "text": "", "why_relevant": ""}],
                    "missing_information": [],
                }
            ],
            "human_review_points": [],
        }
        try:
            assessment = self.llm_client.judge(prompt, schema_hint)
        except Exception as exc:
            result["llm_assessment"] = {
                "provider": provider,
                "model": getattr(self.llm_client, "model", ""),
                "error": str(exc),
            }
            return
        if isinstance(assessment, dict):
            assessment.setdefault("provider", provider)
            assessment.setdefault("model", getattr(self.llm_client, "model", ""))
            result["llm_assessment"] = assessment

    def _build_llm_prompt(self, result: dict[str, Any], pages: list[dict[str, Any]], text: str) -> str:
        page_text = "\n\n".join(
            f"[p.{page.get('page')}]\n{str(page.get('text', ''))[:6000]}"
            for page in pages
            if page.get("text")
        )
        rule_snapshot = {
            "contract_summary": result.get("contract_summary", {}),
            "step2": result.get("step2", {}),
            "step3": result.get("step3", {}),
            "final_result": result.get("final_result", {}),
        }
        return f"""以下の契約書テキストと、既存のルールベース一次判定をレビューしてください。

目的:
- ルールベース判定と比較するためのOpenAI補助判定を作成する
- 契約書本文に根拠がある場合だけYes/No等を判断する
- 根拠がない場合は推測せずUnknownまたはHuman review requiredにする
- 各判断には必ずページ番号と根拠テキストを付ける

出力ルール:
- JSONのみを返してください
- final_result、step_results、key_evidence_for_highlight、human_review_pointsを含めてください
- 日本語で理由を書いてください
- 根拠本文にない情報を補完しないでください

ルールベース一次判定:
{rule_snapshot}

契約書テキスト:
{page_text or text[:18000]}
"""

    def _extract_summary(self, pages: list[dict[str, Any]], text: str) -> dict[str, Any]:
        title = self._regex_first(text, [r"契約書名[:：]\s*([^\n]+)", r"^([^\n]{2,60}契約書)"], "")
        counterparty = self._regex_first(
            text,
            [r"(?:相手先|契約相手先|貸主|貸手|賃貸人|提供者)[:：]\s*([^\n]+)", r"甲[:：]\s*([^\n]+)"],
            "",
        )
        start_date = self._regex_first(text, [r"(?:開始日|契約開始日|リース開始日)[:：]?\s*([0-9０-９年月日/\-.]+)"], "")
        end_date = self._regex_first(text, [r"(?:終了日|契約終了日|リース終了日)[:：]?\s*([0-9０-９年月日/\-.]+)"], "")
        term = self._extract_months(text)
        monthly_amount = self._amount_near(text, ["月額", "月額料金", "月額リース料"])
        total_amount = self._amount_near(text, ["契約総額", "総額", "合計"])
        assets = self._extract_asset_names(text)
        asset_category = " / ".join(sorted(set(self._asset_categories(text))))[:100]
        return {
            "contract_title": title,
            "counterparty": counterparty,
            "start_date": start_date,
            "end_date": end_date,
            "contract_term_months": term,
            "payment_terms": self._regex_first(text, [r"(?:支払条件|支払方法)[:：]\s*([^\n]+)"], ""),
            "total_amount": total_amount,
            "monthly_amount": monthly_amount,
            "asset_names": assets,
            "asset_category": asset_category,
            "source_pages": [p.get("page") for p in pages if p.get("text")],
        }

    def _judge_step1(self, result: dict[str, Any], pages: list[dict[str, Any]], text: str) -> None:
        summary = result["contract_summary"]
        term = summary.get("contract_term_months")
        ev_period = find_keyword_evidence(pages, ["契約期間", "開始日", "終了日", "リース期間"], "契約期間の判断に使用")
        if term is None:
            answer = "Unknown"
            reason = "契約期間を月数として特定できません。"
        elif term <= self.thresholds.get("short_term_months", 1):
            answer = "Yes"
            reason = f"契約期間が{term}か月のため、通常のリース台帳登録対象外または短期処理候補です。"
        else:
            answer = "No"
            reason = f"契約期間が{term}か月と推定され、1か月以内ではありません。"
        result["step1"]["contract_period_within_one_month"] = {
            "answer": answer,
            "reason": reason,
            "evidence": ev_period,
        }

        formal_ev = find_keyword_evidence(pages, self.keywords.get("formal_lease", []), "リース等の形式文言を確認")
        result["step1"]["obvious_lease_contract"] = {
            "answer": "Yes" if formal_ev else "No",
            "reason": "契約名または本文にリース等の文言があります。" if formal_ev else "リース等の形式文言は検出されませんでした。ただし名称のみで最終判定しません。",
            "evidence": formal_ev,
        }

        amount = summary.get("monthly_amount") or summary.get("total_amount")
        low_value_limit = self.thresholds.get("low_value_asset_jpy", 300000)
        low_value_ev = find_keyword_evidence(pages, ["単価", "台", "価格", "金額", "料金"], "少額資産判定に使用")
        if amount is None:
            low_value_answer = "Unknown"
            low_value_reason = "単価または1資産あたりの金額を特定できません。"
        elif amount <= low_value_limit and len(summary.get("asset_names", [])) >= 1:
            low_value_answer = "Yes"
            low_value_reason = f"検出金額が少額基準{low_value_limit:,}円以下です。ただし1資産あたりの内訳確認が必要です。"
        else:
            low_value_answer = "No"
            low_value_reason = "少額資産のみで構成されるとは判断できません。"
        result["step1"]["low_value_assets_only"] = {
            "answer": low_value_answer,
            "reason": low_value_reason,
            "evidence": low_value_ev,
        }
        result["step1"]["step1_result"] = "Proceed to Step2"

    def _judge_step2(self, result: dict[str, Any], pages: list[dict[str, Any]], text: str) -> None:
        formal_ev = find_keyword_evidence(pages, self.keywords.get("formal_lease", []), "形式判定の根拠")
        result["step2"]["formal_assessment"] = {
            "answer": "Yes" if formal_ev else "No",
            "reason": "契約名または本文にリース・レンタル等の文言があります。" if formal_ev else "形式上リースであることを示す文言は十分ではありません。",
            "evidence": formal_ev,
        }

        asset_ev = find_keyword_evidence(pages, self.keywords.get("tangible_assets", []), "有形資産に該当する可能性")
        service_ev = find_keyword_evidence(pages, self.keywords.get("service_like", []), "サービス性を示す文言")
        if asset_ev:
            answer = "Yes"
            reason = "有形資産に該当し得る物件名が検出されました。"
        elif service_ev:
            answer = "No"
            reason = "サービス、容量提供、クラウド、成果物提供に近い文言が中心です。"
        else:
            answer = "Unknown"
            reason = "契約対象物が有形資産か判定する情報が不足しています。"
        result["step2"]["asset_item_assessment"] = {
            "answer": answer,
            "asset_category": result["contract_summary"].get("asset_category", ""),
            "reason": reason,
            "evidence": asset_ev or service_ev,
        }

        real_estate_marker_ev = find_keyword_evidence(pages, self.keywords.get("real_estate", []), "不動産を示す文言")
        real_estate_specific_ev = (
            find_keyword_evidence(
                pages,
                ["所在の建物", "所在の土地", "所在地", "住居表示", "家屋番号", "賃貸物件", "本物件"],
                "不動産の所在地・対象物件を示す情報",
            )
            if real_estate_marker_ev
            else []
        )
        ident_ev = find_keyword_evidence(pages, self.keywords.get("identification", []), "資産の特定性を示す情報")
        if (ident_ev or real_estate_specific_ev) and asset_ev:
            ident_answer = "Yes"
            ident_reason = "型番、台数、設置場所、所在地等により物理資産が特定される可能性があります。"
        elif service_ev and not ident_ev:
            ident_answer = "No"
            ident_reason = "クラウド・容量・サービス等の記載があり、特定の物理資産を示す情報は検出されません。"
        else:
            ident_answer = "Unknown"
            ident_reason = "特定の物理資産を一定期間使用する権利の有無が不明です。"
        result["step2"]["identified_asset"] = {
            "answer": ident_answer,
            "reason": ident_reason,
            "evidence": ident_ev or real_estate_specific_ev or service_ev,
        }

        free_sub_ev = find_keyword_evidence(pages, self.keywords.get("free_substitution", []), "提供者の自由な入替権を示す可能性")
        maint_sub_ev = find_keyword_evidence(pages, self.keywords.get("maintenance_substitution", []), "保守・故障等に限定された交換を示す可能性")
        if free_sub_ev and not maint_sub_ev:
            sub_answer = "Yes"
            sub_reason = "提供者が自由に資産を入れ替えられる可能性があります。"
        elif maint_sub_ev:
            sub_answer = "No"
            sub_reason = "交換は故障・保守・承諾等に限定される可能性があり、通常の自由な入替権とは区別します。"
        elif real_estate_specific_ev:
            sub_answer = "No"
            sub_reason = "所在地で特定された不動産であり、貸手が自由に別資産へ入れ替える権利は通常想定されません。"
        else:
            sub_answer = "Unknown"
            sub_reason = "提供者の実質的な入替権の有無が不明です。"
        result["step2"]["substitution_right"] = {
            "answer": sub_answer,
            "reason": sub_reason,
            "evidence": free_sub_ev or maint_sub_ev or real_estate_specific_ev,
        }

        benefit_ev = find_keyword_evidence(pages, self.keywords.get("exclusive_use", []), "経済的便益の帰属を示す可能性")
        benefit_use_ev = self._find_benefit_use_evidence(pages)
        service_result_ev = find_keyword_evidence(pages, ["共同利用", "複数顧客", "成果物のみ", "サービス結果"], "便益が資産使用ではなくサービス結果にある可能性")
        if service_result_ev:
            benefit_answer = "No"
            benefit_reason = "利用者が資産そのものではなく成果物またはサービス結果のみを受け取る可能性があります。"
        elif benefit_ev or benefit_use_ev:
            benefit_answer = "Yes"
            benefit_reason = "利用者が契約期間中に特定資産を使用し、その使用から生じる利用価値・成果・能力を主として享受する可能性があります。"
        else:
            benefit_answer = "Unknown"
            benefit_reason = "利用者が特定資産の使用から生じる利用価値・成果・能力を主として享受するか不明です。"
        result["step2"]["economic_benefits"] = {
            "answer": benefit_answer,
            "reason": benefit_reason,
            "evidence": benefit_ev or benefit_use_ev or service_result_ev,
        }

        real_estate_use_ev = find_keyword_evidence(
            pages,
            ["として使用", "使用目的", "用途", "目的外", "賃借する", "使用し"],
            "借手の使用目的・使用方法を示す可能性",
        )
        lessee_ev = find_keyword_evidence(pages, self.keywords.get("direction_lessee", []), "利用者の指図権を示す可能性")
        lessor_ev = find_keyword_evidence(pages, self.keywords.get("direction_lessor", []), "提供者の指図・操作を示す可能性")
        if lessee_ev or real_estate_use_ev:
            direct_answer = "Lessee"
            direct_reason = "利用者が使用場所、時期、量、目的等を決定できる可能性があります。"
        elif lessor_ev:
            direct_answer = "Lessor"
            direct_reason = "提供者が設備を操作し、利用者は成果のみを受け取る可能性があります。"
        else:
            direct_answer = "Unknown"
            direct_reason = "使用方法および使用目的の決定権者が不明です。"
        result["step2"]["right_to_direct_use"] = {
            "answer": direct_answer,
            "reason": direct_reason,
            "evidence": lessee_ev or real_estate_use_ev or lessor_ev,
        }

        design_ev = find_keyword_evidence(pages, ["稼働", "運転", "設計", "仕様を指定", "専用金型", "専用治具"], "稼働権または設計関与を示す可能性")
        result["step2"]["operation_right_or_design_involvement"] = {
            "answer": "Yes" if design_ev else "Unknown",
            "reason": "稼働権または設計関与を示す文言があります。" if design_ev else "稼働権または設計関与の有無が不明です。",
            "evidence": design_ev,
        }

        real_estate_ev = real_estate_marker_ev
        movable_ev = [ev for ev in asset_ev if not any(k in ev["text"] for k in self.keywords.get("real_estate", []))]
        if real_estate_ev:
            asset_type = "RealEstate"
            asset_type_reason = "不動産に該当する文言があります。"
        elif movable_ev:
            asset_type = "Movable"
            asset_type_reason = "動産に該当する機器・設備等の文言があります。"
        else:
            asset_type = "Unknown"
            asset_type_reason = "資産種別を判定する情報が不足しています。"
        result["step2"]["asset_type"] = {
            "answer": asset_type,
            "reason": asset_type_reason,
            "evidence": real_estate_ev or movable_ev,
        }

        result["step2"]["step2_result"] = self._derive_step2_result(result["step2"])

    def _judge_step3(self, result: dict[str, Any], pages: list[dict[str, Any]], text: str) -> None:
        step3 = result["step3"]
        summary = result["contract_summary"]
        lease_term = self._extract_months(text, ["リース期間", "契約期間"]) or summary.get("contract_term_months")
        non_cancel = self._extract_months(text, ["解約不能期間"]) or lease_term
        economic_life = self._extract_months(text, ["耐用年数", "経済的耐用年数"])
        fair_value = self._amount_near(text, ["公正価値", "時価", "資産価額"])
        fixed_payment = self._amount_near(text, ["固定リース料", "月額", "リース料"])
        rate = self._extract_rate(text)
        step3.update(
            {
                "lease_term_months": lease_term,
                "non_cancellable_period_months": non_cancel,
                "economic_life_months": economic_life,
                "fair_value": fair_value,
                "discount_rate": rate,
                "fixed_lease_payment": fixed_payment,
                "payment_frequency": "monthly" if fixed_payment else "",
            }
        )

        if non_cancel and economic_life:
            ratio = non_cancel / economic_life
            threshold = self.thresholds.get("finance_lease_term_ratio", 0.75)
            answer = "Yes" if ratio >= threshold else "No"
            reason = f"{non_cancel}か月 / {economic_life}か月 = {ratio:.1%}。閾値{threshold:.0%}との比較。"
            calc = reason
        else:
            answer = "Unknown"
            reason = "解約不能期間または経済的耐用年数が不足しています。"
            calc = ""
        step3["criterion_1_75_percent_test"] = {"calculation": calc, "answer": answer, "reason": reason}

        pv_answer = "Unknown"
        pv_reason = "割引後リース料総額または原資産の公正価値が不足しています。"
        pv_calc = ""
        if non_cancel and fixed_payment and fair_value:
            pv = self._present_value_monthly(fixed_payment, non_cancel, rate)
            ratio = pv / fair_value if fair_value else 0
            threshold = self.thresholds.get("finance_pv_ratio", 0.9)
            pv_answer = "Yes" if ratio >= threshold else "No"
            pv_reason = f"PV {pv:,.0f}円 / 公正価値 {fair_value:,.0f}円 = {ratio:.1%}。閾値{threshold:.0%}との比較。"
            pv_calc = pv_reason
        step3["criterion_2_90_percent_pv_test"] = {
            "calculation": pv_calc,
            "answer": pv_answer,
            "reason": pv_reason,
        }

        if result["step2"]["step2_result"] != "Lease":
            step3["classification_result"] = "Human review required" if result["step2"]["step2_result"] == "Human review required" else "Classification unavailable"
        elif result["step2"].get("asset_type", {}).get("answer") == "RealEstate" and answer != "Yes" and pv_answer != "Yes":
            step3["classification_result"] = "Operating lease"
            if answer == "Unknown":
                step3["criterion_1_75_percent_test"]["reason"] = (
                    step3["criterion_1_75_percent_test"]["reason"]
                    + " 不動産賃貸借で所有権移転等のファイナンス要件が検出されないため、通常はオペレーティングリース候補です。"
                )
        elif answer == "Unknown" and pv_answer == "Unknown":
            step3["classification_result"] = "Classification unavailable"
        elif answer == "Yes" or pv_answer == "Yes":
            step3["classification_result"] = "Finance lease"
        elif answer == "No" and pv_answer == "No":
            step3["classification_result"] = "Operating lease"
        else:
            step3["classification_result"] = "Human review required"

    def _derive_step2_result(self, step2: dict[str, Any]) -> str:
        if step2["asset_item_assessment"]["answer"] == "No":
            return "Non-lease"
        if step2["identified_asset"]["answer"] == "No":
            return "Non-lease"
        if step2["substitution_right"]["answer"] == "Yes":
            return "Non-lease"
        if step2["economic_benefits"]["answer"] == "No":
            return "Non-lease"
        if step2["right_to_direct_use"]["answer"] == "Lessor":
            return "Non-lease"
        lease_paths = [
            step2["formal_assessment"]["answer"] == "Yes",
            step2["asset_item_assessment"]["answer"] == "Yes",
            step2["identified_asset"]["answer"] == "Yes",
            step2["substitution_right"]["answer"] == "No",
            step2["economic_benefits"]["answer"] == "Yes",
            step2["right_to_direct_use"]["answer"] == "Lessee"
            or step2["operation_right_or_design_involvement"]["answer"] == "Yes",
        ]
        if all(lease_paths[1:]):
            return "Lease"
        if lease_paths[0] and lease_paths[1] and lease_paths[2]:
            return "Human review required"
        return "Human review required"

    def _finalize(self, result: dict[str, Any]) -> None:
        step2_result = result["step2"]["step2_result"]
        classification = result["step3"]["classification_result"]
        final = result["final_result"]
        if step2_result == "Lease":
            final["lease_applicability"] = "Lease"
            final["lease_classification"] = classification if classification in {"Finance lease", "Operating lease"} else "Unknown"
        elif step2_result == "Non-lease":
            final["lease_applicability"] = "Non-lease"
            final["lease_classification"] = "Not applicable"
        else:
            final["lease_applicability"] = "Human review required"
            final["lease_classification"] = "Unknown"

        missing = []
        for label, item in [
            ("資産の特定", result["step2"]["identified_asset"]),
            ("入替権", result["step2"]["substitution_right"]),
            ("経済的便益", result["step2"]["economic_benefits"]),
            ("指図権", result["step2"]["right_to_direct_use"]),
        ]:
            if item.get("answer") == "Unknown":
                missing.append(label)
        if result["step2"]["step2_result"] == "Lease" and classification not in {"Finance lease", "Operating lease"}:
            missing.extend(["経済的耐用年数", "公正価値", "割引率または固定リース料"])
        final["missing_information"] = sorted(set(missing))
        final["human_review_guidance"] = self._build_human_review_guidance(result)
        key_ev = []
        for section in ("formal_assessment", "asset_item_assessment", "identified_asset", "economic_benefits", "right_to_direct_use"):
            key_ev.extend(result["step2"].get(section, {}).get("evidence", [])[:1])
        final["key_evidence"] = key_ev[:8]
        final["confidence"] = self._confidence(result)
        final["summary_reason"] = self._summary_reason(result)
        final["recommended_user_action"] = (
            "不足情報を確認し、会計方針・専門部署レビューに回してください。"
            if final["lease_applicability"] == "Human review required" or final["missing_information"]
            else "判定根拠を確認し、必要に応じて会計方針に照らして承認してください。"
        )

    def _confidence(self, result: dict[str, Any]) -> str:
        unknowns = 0
        evidence_count = 0
        for section in ("step1", "step2"):
            for item in result.get(section, {}).values():
                if isinstance(item, dict):
                    if item.get("answer") == "Unknown":
                        unknowns += 1
                    evidence_count += len(item.get("evidence", []) or [])
        if unknowns <= 1 and evidence_count >= 4:
            return "High"
        if unknowns <= 4 and evidence_count >= 2:
            return "Medium"
        return "Low"

    def _summary_reason(self, result: dict[str, Any]) -> str:
        step2 = result["step2"]
        final = result["final_result"]
        if final["lease_applicability"] == "Non-lease":
            return f"リース識別要件を満たさない可能性があります。主な理由: {step2['step2_result']}。"
        if final["lease_applicability"] == "Lease":
            return f"特定資産、便益、指図権等のリース識別要件を満たす候補です。分類: {final['lease_classification']}。"
        return "重要なリース識別情報が不足しているため、要人手確認です。"

    def _build_human_review_guidance(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        step2 = result["step2"]
        step3 = result["step3"]
        guidance: list[dict[str, Any]] = []

        definitions = {
            "asset_item_assessment": {
                "item": "取引アイテム判定",
                "short_check": "有形資産の有無",
                "if_yes_result": "資産特定へ",
                "if_no_result": "対象外候補",
                "question": "契約対象に、建物・土地・設備・車両・PC・サーバー・複合機など、物理的に区分できる有形資産が含まれるかを確認してください。",
                "how_to_check": "契約書本文、別紙、仕様書、見積書、物件明細、請求明細を確認し、サービス名だけでなく資産利用部分の有無を見てください。",
                "if_yes": "有形資産が含まれる場合は、資産の特定判定へ進みます。",
                "if_no": "有形資産が含まれず、クラウド・容量提供・成果物提供のみであれば、リース対象外候補になります。",
            },
            "identified_asset": {
                "item": "資産の特定",
                "short_check": "特定資産の有無",
                "if_yes_result": "リース候補",
                "if_no_result": "対象外候補",
                "question": "対象資産が型番、製造番号、管理番号、車両番号、設置場所、台数、別紙明細などで特定され、契約期間中に同じ物理資産を使用する権利があるかを確認してください。",
                "how_to_check": "契約書の物件欄、別紙、仕様書、見積書、納入明細、設置場所一覧を確認してください。単に「サーバー」「設備」とあるだけでは足りません。",
                "if_yes": "特定資産ありとして、入替権・経済的便益・指図権の判定へ進みます。",
                "if_no": "特定された物理資産がなければ、通常はリース対象外候補になります。",
            },
            "substitution_right": {
                "item": "入替権",
                "short_check": "自由な入替権の有無",
                "if_yes_result": "対象外候補",
                "if_no_result": "リース候補",
                "question": "貸手・提供者が、借手・利用者の承諾なく、対象資産を他の資産へ自由に入れ替えられる実質的な権利を持つかを確認してください。",
                "how_to_check": "代替品、同等品、交換、入替、変更、保守、故障、アップグレード、承諾、事前書面承諾の条項を確認してください。保守・故障時だけの交換は自由な入替権とは区別します。",
                "if_yes": "自由な入替権がある場合、特定資産の使用権がない可能性が高く、リース対象外候補になります。",
                "if_no": "入替不可、借手承諾が必要、または保守・故障時の交換に限られる場合は、リース候補として経済的便益・指図権の判定へ進みます。",
            },
            "economic_benefits": {
                "item": "経済的便益",
                "short_check": "便益享受の有無",
                "if_yes_result": "リース候補",
                "if_no_result": "対象外候補",
                "question": "借手・利用者が契約期間中に特定資産を使用し、その使用から生じる利用価値・成果・能力を主として享受しているかを確認してください。",
                "how_to_check": "専用使用、独占使用、自社業務、製造ライン、加工、生産、検査、保管、運搬、処理能力、アウトプットの帰属、他顧客との共同利用の有無を確認してください。",
                "if_yes": "利用者が資産使用の便益を主として享受する場合は、指図権の判定へ進みます。",
                "if_no": "利用者が成果物やサービス結果だけを受け取り、資産使用の便益を支配していない場合は、リース対象外候補になります。",
            },
            "right_to_direct_use": {
                "item": "指図権",
                "short_check": "借手の指図権",
                "if_yes_result": "リース候補",
                "if_no_result": "対象外候補",
                "question": "借手・利用者が、契約期間中の使用方法・使用目的・使用場所・使用時期・使用量を決定できるかを確認してください。",
                "how_to_check": "使用目的、使用方法、稼働時間、製造計画、加工対象、設置場所、作業者配置、貸手の操作・管理条項を確認してください。",
                "if_yes": "借手が指図権を持つ場合は、リース候補として分類判定へ進みます。",
                "if_no": "貸手が使用方法・目的を決め、利用者が成果だけを受け取る場合は、リース対象外候補になります。契約開始前に使用方法が固定され双方変更不能なら、稼働権・設計関与を確認してください。",
            },
            "operation_right_or_design_involvement": {
                "item": "稼働権・設計関与",
                "short_check": "稼働権・設計関与",
                "if_yes_result": "リース候補",
                "if_no_result": "対象外候補",
                "question": "使用方法が契約開始前に固定されている場合、借手が資産を稼働させる権利を持つか、または資産設計に関与して使用方法・目的を事前に決めたかを確認してください。",
                "how_to_check": "専用設備、金型、治具、製造委託、無償貸与、仕様指定、設計承認、稼働指示の条項を確認してください。",
                "if_yes": "借手の稼働権または設計関与がある場合は、リース候補として分類判定へ進みます。",
                "if_no": "稼働権も設計関与もない場合は、リース対象外候補になります。",
            },
            "asset_type": {
                "item": "資産種別",
                "short_check": "動産/不動産",
                "if_yes_result": "分類へ",
                "if_no_result": "分類要確認",
                "question": "対象資産が動産か不動産かを確認してください。",
                "how_to_check": "物件明細、登記・所在地、設備明細、車両・機器明細を確認してください。",
                "if_yes": "動産なら通常のStep3分類判定へ進みます。不動産ならオペレーティング候補になりやすいですが、契約条件により追加確認してください。",
                "if_no": "資産種別が確認できない場合、分類と台帳登録要否を人手確認してください。",
            },
        }

        for key, definition in definitions.items():
            if key == "operation_right_or_design_involvement" and step2.get("right_to_direct_use", {}).get("answer") != "Neither":
                continue
            item = step2.get(key, {})
            if item.get("answer") == "Unknown":
                guidance.append({"step": "Step2", "key": key, **definition})

        if step2.get("step2_result") == "Lease" and step3.get("classification_result") not in {"Finance lease", "Operating lease"}:
            if not step3.get("economic_life_months"):
                guidance.append(
                    {
                        "step": "Step3",
                        "key": "economic_life_months",
                        "item": "経済的耐用年数",
                        "short_check": "耐用年数",
                        "if_yes_result": "75%テスト可能",
                        "if_no_result": "分類要確認",
                        "question": "原資産の経済的耐用年数を確認してください。",
                        "how_to_check": "固定資産台帳、耐用年数表、メーカー仕様書、社内会計方針、見積書を確認してください。",
                        "if_yes": "解約不能リース期間 ÷ 経済的耐用年数が75%以上ならファイナンスリース候補、75%未満なら90%PVテストも確認します。",
                        "if_no": "経済的耐用年数が確認できなければ、75%テストは判定不能です。",
                    }
                )
            if not step3.get("fair_value"):
                guidance.append(
                    {
                        "step": "Step3",
                        "key": "fair_value",
                        "item": "原資産の公正価値",
                        "short_check": "公正価値",
                        "if_yes_result": "90%PVテスト可能",
                        "if_no_result": "分類要確認",
                        "question": "リース開始日時点の原資産の公正価値を確認してください。",
                        "how_to_check": "見積書、購入価格、メーカー価格表、鑑定評価、貸手提示資料を確認してください。",
                        "if_yes": "割引後リース料総額 ÷ 公正価値が90%以上ならファイナンスリース候補です。",
                        "if_no": "公正価値が確認できなければ、90%PVテストは判定不能です。",
                    }
                )
            if not step3.get("fixed_lease_payment"):
                guidance.append(
                    {
                        "step": "Step3",
                        "key": "fixed_lease_payment",
                        "item": "固定リース料",
                        "short_check": "固定リース料",
                        "if_yes_result": "90%PVテスト可能",
                        "if_no_result": "分類要確認",
                        "question": "固定リース料、支払頻度、フリーレント、残価保証、インセンティブを確認してください。",
                        "how_to_check": "リース料条項、支払予定表、別紙料金表、請求明細を確認してください。サービス料や保守料が混在する場合は内訳を確認してください。",
                        "if_yes": "固定リース料が確認できれば90%PVテストを計算できます。",
                        "if_no": "固定リース料が確認できなければ、ファイナンス/オペレーティング分類は判定不能です。",
                    }
                )

        return guidance

    def _regex_first(self, text: str, patterns: list[str], default: str | None = None) -> str | None:
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.MULTILINE)
            if m:
                return m.group(1).strip()
        return default

    def _extract_months(self, text: str, labels: list[str] | None = None) -> int | None:
        explicit_labels = labels is not None
        labels = labels or ["契約期間", "リース期間", "期間", "解約不能期間", "耐用年数"]
        label_pattern = "|".join(map(re.escape, labels))
        labeled_lines = re.findall(rf"(?:{label_pattern})[^\n]{{0,120}}", text)
        if explicit_labels and not labeled_lines:
            return None
        search_targets = labeled_lines or [text]

        for target in search_targets:
            months = self._months_from_date_range(target)
            if months:
                return months

        for target in search_targets:
            m = re.search(r"([0-9０-９]+)\s*年間", target)
            if m:
                n = int(self._to_ascii_digits(m.group(1)))
                if n < 100:
                    return n * 12

        for target in search_targets:
            m = re.search(r"([0-9０-９]+)\s*(?:か月|ヶ月|ヵ月|カ月)", target)
            if m:
                return int(self._to_ascii_digits(m.group(1)))

        for target in search_targets:
            m = re.search(r"([0-9０-９]+)\s*年(?![0-9０-９]+\s*月)", target)
            if m:
                n = int(self._to_ascii_digits(m.group(1)))
                if n < 100:
                    return n * 12
        return None

    def _months_from_date_range(self, text: str) -> int | None:
        pattern = (
            r"([0-9０-９]{4})年\s*([0-9０-９]{1,2})月\s*([0-9０-９]{1,2})日"
            r".{0,20}?"
            r"([0-9０-９]{4})年\s*([0-9０-９]{1,2})月\s*([0-9０-９]{1,2})日"
        )
        m = re.search(pattern, text)
        if not m:
            return None
        sy, sm, sd, ey, em, ed = [int(self._to_ascii_digits(x)) for x in m.groups()]
        months = (ey - sy) * 12 + (em - sm)
        if ed >= sd:
            months += 1
        return months if months > 0 else None

    def _amount_near(self, text: str, labels: list[str]) -> int | None:
        label_pattern = "|".join(map(re.escape, labels))
        m = re.search(rf"(?:{label_pattern})[^\n0-9０-９]{{0,20}}([0-9０-９,，]+)\s*円", text)
        if not m:
            return None
        return int(self._to_ascii_digits(m.group(1)).replace(",", "").replace("，", ""))

    def _extract_rate(self, text: str) -> float | None:
        m = re.search(r"(?:割引率|利率)[^\n0-9０-９]{0,20}([0-9０-９.．]+)\s*%", text)
        if not m:
            return None
        return float(self._to_ascii_digits(m.group(1)).replace("．", ".")) / 100

    def _extract_asset_names(self, text: str) -> list[str]:
        names = re.findall(r"(?:資産名|物件名|対象物件|機器名)[:：]\s*([^\n,、]+)", text)
        keywords = self.keywords.get("tangible_assets", [])
        for kw in keywords:
            if kw in text and kw not in names:
                names.append(kw)
        return names[:10]

    def _asset_categories(self, text: str) -> list[str]:
        categories = []
        for kw in self.keywords.get("tangible_assets", []):
            if kw in text:
                categories.append(kw)
        return categories[:12]

    def _find_benefit_use_evidence(self, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        subjects = ["借手", "利用者", "賃借人", "使用者", "当社", "乙"]
        assets = ["本物件を", "対象資産を", "対象物件を", "リース物件を", "設備を", "機器を"]
        values = [
            "使用する", "使用し", "利用する", "稼働", "運転", "業務", "事業", "自社",
            "製造ライン", "製造", "加工", "生産", "試作", "量産", "検査",
            "運搬", "保管", "処理", "能力", "アウトプット", "便益", "利用価値",
        ]
        hits: list[dict[str, Any]] = []
        for page in pages:
            page_no = int(page["page"])
            for line in str(page.get("text", "")).splitlines():
                sentence = line.strip()
                if not sentence:
                    continue
                if (
                    any(term in sentence for term in subjects)
                    and any(term in sentence for term in assets)
                    and any(term in sentence for term in values)
                ):
                    hits.append(
                        {
                            "page": page_no,
                            "text": sentence[:700],
                            "highlight_required": True,
                            "why_relevant": "利用者が特定資産を使用し、その利用価値・成果・能力を享受する根拠",
                        }
                    )
                    if len(hits) >= 3:
                        return hits
        return hits

    def _present_value_monthly(self, monthly_payment: int, months: int, annual_rate: float | None) -> float:
        if not annual_rate:
            return float(monthly_payment * months)
        monthly_rate = annual_rate / 12
        return monthly_payment * (1 - math.pow(1 + monthly_rate, -months)) / monthly_rate

    def _to_ascii_digits(self, text: str) -> str:
        table = str.maketrans("０１２３４５６７８９", "0123456789")
        return text.translate(table)
