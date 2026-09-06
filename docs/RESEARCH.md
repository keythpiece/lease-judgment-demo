# 既存サービス調査（海外含む・2026年9月時点）

2027年度適用の新リース会計基準（ASBJ「リースに関する会計基準」、2027年4月1日以後開始事業年度から適用）に向けた、
契約書AI判定アプリの参考として、国内外の類似サービスを英語で調査した結果の要約。

## 海外（IFRS 16 / ASC 842 対応）

| サービス | 特徴 |
| --- | --- |
| Trullion | PDF/Excel契約書をワンクリックでアップロード、AI+OCRで日付・支払条件・更新オプション等を抽出。抽出値と契約原文をリンクさせた「ソースベースの監査証跡」が強み。分類・仕訳・償却スケジュールまで自動生成。 |
| MRI Contract Intelligence (旧LEVERTON) | IFRS 16 / ASC 842 用の抽出テンプレートを事前定義し、契約から会計データベースへ直接取り込む。 |
| Netgain NetLease | AIリース抽象化(lease abstraction)でASC 842コンプライアンスを支援。抽出データのレビューワークフロー付き。 |
| FinQuery (旧LeaseQuery) / Visual Lease / Nakisa / LeaseAccelerator | リース会計エンジン（分類・ROU資産/負債測定・開示）が中心。AI抽出は補助機能。 |
| iLeasePro | 無料の「AI ASC 842 Lease Analyzer」を公開。アップロード→即時分析という手軽さで見込み客を集める形。 |
| LeaseGPT / Kolena / V7 Labs 等のレビュー記事 | 業界の共通見解として human-in-the-loop（低信頼度の抽出項目を人にルーティングし、修正内容を監査証跡に残す）が必須とされる。 |

## 日本（新リース会計基準対応）

| サービス | 特徴 |
| --- | --- |
| Fast Accounting「リース会計AIエージェント」 | 2億件超の会計書類で学習したAI-OCRで複雑な契約書もデータ化。契約書取込→計上までのエンドツーエンド自動化。 |
| Deloitte トーマツ | AI-OCRで契約書をテキスト化し、生成AIがリース料・契約期間等を抽出、リース計算アプリへ自動連携するサービスを提供。 |

## 本アプリへの反映ポイント

1. **アップロード→実行→結果の単純なUX**（Trullion / iLeasePro型）: 既存実装を踏襲。
2. **Human-in-the-loop（追加確認→再判定）**: 業界標準の「低信頼度項目を人に確認」を、選択式+自由記述の追加確認フォームとして実装。
   回答は `audit.user_confirmations` に「AI初期判定・ユーザー回答・補足・回答日時」の監査証跡として記録（LeaseGPT等が推奨する監査証跡設計を踏襲）。
3. **管理者ナレッジ（社内マニュアル・判定ルール・規程）**: MRI Contract Intelligence のテンプレート思想を参考に、
   しきい値・キーワード辞書・ナレッジノートを管理者画面で設定し、判定エンジンとLLMプロンプトの双方から参照する構成とした。
4. **根拠リンク**: 抽出値と契約原文ページの紐付け（既存のevidence/ハイライト機能）は海外主要サービスと同じ設計思想であり継続。

## 主な出典（英語）

- https://trullion.com/products/leases/
- https://trullion.com/blog/lease-accounting-software-solutions-for-asc-842-ifrs-16-2026-guide/
- https://mricontractintelligence.com/solutions/ifrs-16-asc-842/
- https://www.netgain.tech/blog/netlease-complete-lease-abstraction-asc-842
- https://ileasepro.com/blog/free-ai-powered-asc-842-lease-analyzer/
- https://www.leasegpt.io/blog/human-in-the-loop-lease-review
- https://www.kolena.com/blog/best-ai-lease-abstraction-software-top-8-in-2026/
- https://www.fastaccounting.ai/en/en_news/14356/
- https://hls-global.jp/en/2024/09/30/the-new-lease-accounting-standard-to-be-adopted-in-japan/
