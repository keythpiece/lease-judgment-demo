from src.lease_judgment_engine import LeaseJudgmentEngine


def judge(text: str) -> dict:
    return LeaseJudgmentEngine().judge([{"page": 1, "text": text, "source": "text"}], "sample.pdf")


def test_clear_lease_contract_is_lease_candidate():
    result = judge(
        """
        複合機リース契約書
        契約期間 60か月
        対象物件: 複合機 型番 MX-9000 管理番号 A-001 設置場所 東京本社 台数 1台
        利用者は本物件を専用かつ独占して使用し、使用場所および使用目的を利用者が決定する。
        故障時の交換は利用者の承諾を得て保守目的に限り行う。
        月額リース料 100,000円
        経済的耐用年数 72か月
        公正価値 5,000,000円
        """
    )
    assert result["step2"]["step2_result"] == "Lease"
    assert result["final_result"]["lease_applicability"] == "Lease"


def test_cloud_service_without_physical_server_is_non_lease():
    result = judge(
        """
        クラウドサービス利用契約
        利用者はクラウド容量およびネットワークサービスを利用する。
        どの物理サーバーを使用するかは提供者が任意に決定し、複数顧客で共同利用する。
        サービスレベルと処理能力を提供し、利用者はサービス結果のみを受け取る。
        契約期間 24か月
        """
    )
    assert result["step2"]["step2_result"] == "Non-lease"
    assert result["final_result"]["lease_applicability"] == "Non-lease"


def test_physical_server_rental_is_lease_candidate():
    result = judge(
        """
        物理サーバー賃貸借契約
        対象物件: サーバー 型番 SV-100 製造番号 S12345 設置場所 データセンターA 台数 2台
        利用者は対象サーバーを独占して使用し、利用者の業務のために使用する。
        使用時期および使用量は利用者が決定する。交換は故障または保守の場合に限る。
        契約期間 36か月
        """
    )
    assert result["step2"]["step2_result"] == "Lease"


def test_gas_cylinder_supply_is_non_lease_candidate():
    result = judge(
        """
        ガス供給契約
        ガスボンベは供給量に応じて交換前提とし、同一個体を一定期間使用する権利はない。
        提供者は同等品に変更し、代替資産を提供できる。
        利用者はガスの供給サービスを受ける。
        契約期間 12か月
        """
    )
    assert result["final_result"]["lease_applicability"] in {"Non-lease", "Human review required"}


def test_copier_mixed_fee_requires_review_when_component_split_missing():
    result = judge(
        """
        複合機利用契約
        対象物件: 複合機 型番 CP-500 管理番号 C-200 台数 1台
        利用者は設置場所で専用使用する。
        料金は機器利用料と印刷料金を含むが、内訳は契約書に記載しない。
        契約期間 48か月
        """
    )
    assert result["final_result"]["lease_applicability"] in {"Lease", "Human review required"}


def test_manufacturing_outsourcing_is_non_lease_or_review():
    result = judge(
        """
        製造委託契約
        委託先が自社設備を操作して製品を製造し、利用者は成果物のみを受領する。
        対象設備の使用方法は委託先が管理する。
        契約期間 24か月
        """
    )
    assert result["final_result"]["lease_applicability"] in {"Non-lease", "Human review required"}


def test_tooling_contract_can_be_review_candidate():
    result = judge(
        """
        専用金型使用契約
        対象物件: 専用金型 型番 MOLD-01 管理番号 M-001
        利用者が仕様を指定し、量産期間中に当該金型を稼働させる権利を有する。
        契約期間 36か月
        """
    )
    assert result["final_result"]["lease_applicability"] in {"Lease", "Human review required"}


def test_economic_benefits_detect_lessee_business_use():
    result = judge(
        """
        ファイナンスリース契約書
        リース物件 高精度CNC加工設備 一式
        型式・製造番号 SPL-CNC9000 / 製造番号 CN-2026-001
        設置場所 借手第2工場
        借手は、本物件を自社の精密部品製造ラインにおける切削加工、試作加工および量産加工のために使用するものとする。
        借手は、契約期間中、製造計画、稼働時間、加工対象、使用場所および作業者の配置を自己の判断で決定することができる。
        本契約のリース期間は72か月とし、この期間は解約不能期間とする。
        経済的耐用年数 84か月
        原資産の公正価値 50,000,000円
        固定リース料 月額780,000円
        割引率 年3.0%
        """
    )
    economic = result["step2"]["economic_benefits"]
    assert economic["answer"] == "Yes"
    assert economic["evidence"]


def test_unknown_substitution_right_has_actionable_guidance():
    result = judge(
        """
        製造設備リース契約書
        契約期間 60か月
        対象物件: 製造設備 型番 EQ-100 製造番号 EQ-001 設置場所 第1工場 台数 1台
        借手は、本物件を自社の製造ラインにおける部品加工および量産加工のために使用するものとする。
        借手は、契約期間中、製造計画、稼働時間、加工対象、使用場所を自己の判断で決定することができる。
        """
    )
    final = result["final_result"]
    substitution = result["step2"]["substitution_right"]
    guidance = [g for g in final["human_review_guidance"] if g["key"] == "substitution_right"]
    assert substitution["answer"] == "Unknown"
    assert final["lease_applicability"] == "Human review required"
    assert guidance
    assert "自由に入れ替え" in guidance[0]["question"]
    assert "リース対象外候補" in guidance[0]["if_yes"]
    assert "リース候補" in guidance[0]["if_no"]


def test_building_lease_is_operating_lease_candidate():
    result = judge(
        """
        建物賃貸借契約書
        賃貸人サンプル個人不動産（以下「甲」という。）と、賃借人サンプル物流株式会社（以下「乙」という。）は、次のとおり建物賃貸借契約を締結する。
        第1条 甲は、東京都サンプル区倉庫町三丁目10番1号所在の建物を乙に賃貸し、乙はこれを賃借する。
        乙は本物件を事務所および倉庫として使用し、居住その他契約目的外の用途に供してはならない。
        第2条 賃貸借期間は2026年10月1日から2029年9月30日までの3年間とする。
        第3条 賃料は月額1,350,000円とし、乙は毎月末日までに支払う。
        """
    )
    assert result["final_result"]["lease_applicability"] == "Lease"
    assert result["final_result"]["lease_classification"] == "Operating lease"
    assert result["step2"]["identified_asset"]["answer"] == "Yes"
    assert result["step2"]["economic_benefits"]["answer"] == "Yes"
