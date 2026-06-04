# リース会計 契約判定プロトタイプ

契約書PDFをローカルPCで読み取り、リース会計上の「リース対象か否か」と「ファイナンスリース／オペレーティングリース分類」を一次判定する Streamlit アプリです。

会社固有名詞、社内システム名、特定企業名に依存しない横展開可能な構成にしています。

## ファイル構成

```text
lease_judgment_app/
  app.py
  requirements.txt
  README.md
  .env.example
  config/
    cell_mapping.yaml
    judgment_rules.yaml
  src/
    pdf_reader.py
    ocr_reader.py
    llm_client.py
    lease_judgment_engine.py
    evidence_extractor.py
    pdf_highlighter.py
    excel_writer.py
    report_writer.py
    schemas.py
    utils.py
  templates/
    lease_assessment_template.xlsx
  outputs/
  tests/
    test_engine.py
```

## 設計概要

判定結果は `src/schemas.py` のJSON構造で保持します。`src/lease_judgment_engine.py` がStep1、Step2、Step3の判定を集約し、UI・PDFレポート・Excel転記・PDFハイライトは同じJSONを再利用します。

PDF読取は `src/pdf_reader.py` が PyMuPDF でテキストPDFを抽出します。テキストが少ないページは `src/ocr_reader.py` のOCRインターフェースに渡せるため、Tesseractや別OCRエンジンへ差し替えできます。

LLM呼び出しは `src/llm_client.py` に抽象化しています。既定は `rule_based` で、APIキーなしでも判定できます。OpenAIを選択した場合は、ルールベース判定に加えてOpenAI補助判定を検証用に表示します。

## セットアップ

Python 3.10以上を推奨します。

```powershell
cd C:\Users\hswkg\OneDrive\Documents\Playground\lease_judgment_app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

必要に応じて `.env` を編集します。

```text
LLM_PROVIDER=rule_based
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
OCR_ENGINE=none
```

OCRにTesseractを使う場合は、Tesseract本体を別途インストールし、必要に応じて `TESSERACT_CMD` を設定してください。

## 起動方法

```powershell
streamlit run app.py
```

画面で契約書PDFをアップロードし、「判定実行」を押します。

簡単に起動する場合は、デスクトップのショートカット「リース判定アプリを起動」をダブルクリックしてください。アプリ用のサーバー画面が開き、ブラウザで `http://127.0.0.1:8501` を開きます。

サーバー画面を閉じるとアプリも停止します。ブラウザだけを閉じた場合は、サーバー画面が残っていれば再度 `http://127.0.0.1:8501` にアクセスできます。

## PC起動後の自動起動

`http://127.0.0.1:8501` は、PC内でStreamlitアプリが起動している間だけ開けるローカルURLです。PCを再起動するとアプリのプロセスも終了するため、ログオン時に自動起動するタスクを登録します。

```powershell
cd C:\Users\hswkg\OneDrive\Documents\Playground\lease_judgment_app
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-AutoStartTask.ps1
```

手動で起動する場合:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LeaseJudgmentApp.ps1
```

手動で停止する場合:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Stop-LeaseJudgmentApp.ps1
```

自動起動を解除する場合:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Uninstall-AutoStartTask.ps1
```

## 判定結果の見方

画面には以下を表示します。

- 判定サマリー: リース対象判定、リース分類、信頼度、要人手確認理由
- Step別判定表: Step、判定項目、AI判定、判断理由、根拠ページ、根拠テキスト、要確認事項
- 根拠表示: 契約書から引用した文章、ページ番号
- JSON: 監査・レビュー用の判定過程

## 出力方法

判定後に以下のボタンで明示的にファイル出力します。契約本文や判定結果は、ユーザーが出力操作をした場合のみ `outputs/` に保存されます。

- 判定結果PDFを出力: `original_filename_lease_report.pdf`
- ハイライト済みPDFを出力: `original_filename_highlighted.pdf`
- Excel判定シートへ転記して出力: `original_filename_lease_assessment.xlsx`
- JSONを出力: `original_filename_judgment.json`

## Excelセルマッピング

既存テンプレートのセル位置は `config/cell_mapping.yaml` で変更できます。

```yaml
step1:
  contract_title: "B5"
  counterparty: "B6"
  start_date: "B7"
  end_date: "B8"
step2:
  formal_assessment_answer: "F20"
  formal_assessment_comment: "G20"
step3:
  economic_life_months: "C20"
  fair_value: "C30"
```

長い根拠テキストは別シート「AI判定根拠」に一覧化します。既存テンプレートをサイドバーからアップロードした場合、openpyxlで読み込み、可能な限り数式・書式を保持して転記します。

## LLMプロバイダー差し替え

`src/llm_client.py` の `LLMClient` を継承して `judge()` を実装してください。`.env` の `LLM_PROVIDER` またはUI選択により provider を切り替える構成を拡張できます。

プロンプト中核は `SYSTEM_PROMPT` に定義しています。必ず根拠引用付きJSONを返すようにしてください。

## セキュリティ上の注意

- APIキーはコードに直書きせず、環境変数または `.env` から読み込みます。
- 契約書本文は通常処理では永続保存しません。
- 明示的に出力したPDF、Excel、JSONのみ `outputs/` に保存されます。
- 外部LLMを使う場合、契約本文がAPI送信される可能性があります。社内規程、機密区分、DPA、ログ保持条件を確認してください。

## 会計判断上の注意

本アプリの判定は契約書PDFに基づく一次判定です。最終的な会計判断は会社の会計方針、重要性基準、リース会計基準、監査人・専門部署の確認に従ってください。

## 既知の制約

- 既定の `rule_based` はプロトタイプ用です。高度な条項解釈にはLLMまたはレビュー担当者の確認が必要です。
- OCR品質は導入するOCRエンジンに依存します。
- PDFハイライトはPDF内テキスト検索に基づきます。OCR文字列や改行差異により未検出になる場合があります。
- Step3の90%PVテストは、月額固定料・期間・公正価値が抽出できた場合の簡易計算です。
- 少額基準や閾値は `config/judgment_rules.yaml` で調整してください。

## テスト

```powershell
pytest
```

7つの代表ケースを `tests/test_engine.py` に用意しています。

## 社内ネットワークで共有してテストする方法

このアプリは通常、本人PCだけで開ける `http://127.0.0.1:8501` で起動します。他の社内PCからもテストできるようにする場合は、社内共有モードで起動してください。

一番簡単な方法は、アプリフォルダ内の次のファイルをダブルクリックすることです。

```text
Open-LeaseJudgmentApp-LAN.bat
```

起動すると画面に次のような共有URLが表示されます。

```text
Company network share URL: http://192.168.x.x:8501
```

このURLを、同じ社内ネットワークまたはVPNに接続している人に共有してください。共有される側はブラウザでそのURLを開くだけでテストできます。

共有URLだけを確認したい場合は、次を実行します。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Show-LeaseJudgmentShareUrl.ps1
```

他の人がURLを開けない場合は、Windows Defender ファイアウォールで TCP 8501 の受信がブロックされている可能性があります。社内ルールに従い、必要であれば管理者権限のPowerShellで次を実行してください。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Enable-LeaseJudgmentFirewall.ps1
```

PC起動後に自動で社内共有モードを開始したい場合は、次を実行します。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-AutoStartTask-LAN.ps1
```

注意点:

- この共有方法では、アプリを起動しているPCがサーバーになります。そのPCの電源が入っていて、ネットワークに接続されている必要があります。
- DHCP環境では `192.168.x.x` のIPアドレスが変わることがあります。開けなくなった場合は、共有URLを再確認してください。
- 現在のプロトタイプにはログイン認証がありません。社外公開やインターネット公開には使わず、社内LANまたはVPN内の限定テストにしてください。
- アップロードされた契約書PDFは、アプリを起動しているPC上で処理されます。社内の機密情報ルールに従って利用してください。
- 複数部署・多数ユーザーで継続利用する場合は、共有PCではなく社内サーバー、仮想マシン、または社内クラウドに配置し、認証・アクセス制御・ログ管理を追加してください。

## Streamlit Community Cloudでサンプルデモを共有する方法

サンプル契約書、または十分に匿名化・架空化した合成サンプル契約書だけを使う前提で、Streamlit Community Cloudにデプロイできます。利用者はブラウザでURLを開くだけで使えます。

重要: 実際の契約書、機密情報、個人情報、取引先を特定できる情報はアップロードしないでください。外部クラウド上でPDF処理が実行されるため、本物の契約書検証には社内承認済み環境を使ってください。

### GitHubにアップロードするもの

このフォルダのうち、以下はアップロードして構いません。

- `app.py`
- `src/`
- `config/`
- `templates/`
- `requirements.txt`
- `packages.txt`
- `runtime.txt`
- `.streamlit/config.toml`
- `.streamlit/secrets.example.toml`
- `.env.example`
- サンプル契約書PDF

以下はアップロードしないでください。`.gitignore` で除外しています。

- `.env`
- `.streamlit/secrets.toml`
- `.venv/`
- `outputs/`
- `dist/`
- `__pycache__/`

### デプロイ手順

1. GitHubに、このアプリ用のリポジトリを作成します。
2. `lease_judgment_app` の中身をGitHubにアップロードします。
3. Streamlit Community Cloudで `New app` を選びます。
4. GitHubリポジトリを選びます。
5. Main file path に `app.py` を指定します。
6. Secretsには、サンプルデモだけなら以下を設定します。

```toml
LLM_PROVIDER = "rule_based"
OCR_ENGINE = "none"
DEMO_MODE = "true"
```

OpenAIまたはClaudeを使う場合だけ、SecretsにAPIキーを追加してください。

```toml
OPENAI_API_KEY = "sk-..."
ANTHROPIC_API_KEY = "sk-ant-..."
```

### デモ運用ルール

- 画面上に「実契約書・機密情報アップロード禁止」の注意書きを表示しています。
- 社内共有時も、サンプル契約書または合成サンプル契約書だけを使ってください。
- Copilot等で本物に近い合成サンプルを作る場合は、会社名、住所、金額、日付、物件番号、製造番号、担当者名、口座情報、社内固有の条項・名称を架空化してください。
- 本物の契約書で検証する段階では、Streamlit Community Cloudではなく、社内サーバーや社内承認済みクラウドへ移してください。
