from __future__ import annotations

from copy import deepcopy
from typing import Any


ANSWER = "Yes/No/Unknown"


DEFAULT_RESULT: dict[str, Any] = {
    "contract_summary": {
        "contract_title": "",
        "counterparty": "",
        "start_date": "",
        "end_date": "",
        "contract_term_months": None,
        "payment_terms": "",
        "total_amount": None,
        "monthly_amount": None,
        "asset_names": [],
        "asset_category": "",
        "source_pages": [],
    },
    "step1": {
        "contract_period_within_one_month": {
            "answer": "Unknown",
            "reason": "",
            "evidence": [],
        },
        "obvious_lease_contract": {
            "answer": "Unknown",
            "reason": "",
            "evidence": [],
        },
        "low_value_assets_only": {
            "answer": "Unknown",
            "reason": "",
            "evidence": [],
        },
        "step1_result": "Human review required",
    },
    "step2": {
        "formal_assessment": {
            "answer": "Unknown",
            "reason": "",
            "evidence": [],
        },
        "asset_item_assessment": {
            "answer": "Unknown",
            "asset_category": "",
            "reason": "",
            "evidence": [],
        },
        "identified_asset": {
            "answer": "Unknown",
            "reason": "",
            "evidence": [],
        },
        "substitution_right": {
            "answer": "Unknown",
            "reason": "",
            "evidence": [],
        },
        "economic_benefits": {
            "answer": "Unknown",
            "reason": "",
            "evidence": [],
        },
        "right_to_direct_use": {
            "answer": "Unknown",
            "reason": "",
            "evidence": [],
        },
        "operation_right_or_design_involvement": {
            "answer": "Unknown",
            "reason": "",
            "evidence": [],
        },
        "asset_type": {
            "answer": "Unknown",
            "reason": "",
            "evidence": [],
        },
        "step2_result": "Human review required",
    },
    "step3": {
        "lease_term_months": None,
        "non_cancellable_period_months": None,
        "economic_life_months": None,
        "fair_value": None,
        "discount_rate": None,
        "fixed_lease_payment": None,
        "payment_frequency": "",
        "criterion_1_75_percent_test": {
            "calculation": "",
            "answer": "Unknown",
            "reason": "",
        },
        "criterion_2_90_percent_pv_test": {
            "calculation": "",
            "answer": "Unknown",
            "reason": "",
        },
        "classification_result": "Human review required",
    },
    "final_result": {
        "lease_applicability": "Human review required",
        "lease_classification": "Unknown",
        "confidence": "Low",
        "summary_reason": "",
        "key_evidence": [],
        "missing_information": [],
        "human_review_guidance": [],
        "recommended_user_action": "",
    },
    "knowledge_applied": {
        "threshold_overrides": {},
        "notes": [],
    },
    "audit": {
        "input_pdf_name": "",
        "judged_at": "",
        "engine": "rule_based",
        "user_confirmations": [],
    },
}


def empty_result() -> dict[str, Any]:
    return deepcopy(DEFAULT_RESULT)


def evidence(page: int | None, text: str, reason: str = "", highlight_required: bool = True) -> dict[str, Any]:
    item: dict[str, Any] = {
        "page": page,
        "text": text.strip(),
        "highlight_required": highlight_required,
    }
    if reason:
        item["why_relevant"] = reason
    return item
