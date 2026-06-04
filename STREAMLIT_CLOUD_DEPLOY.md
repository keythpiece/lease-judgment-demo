# Streamlit Community Cloud 共有手順

この手順は、サンプル契約書または合成サンプル契約書だけを使うデモ用です。

実際の契約書、機密情報、個人情報、取引先を特定できる情報はアップロードしないでください。

## 1. GitHubに載せる前に確認する

このフォルダに次のファイルがあることを確認します。

- `app.py`
- `requirements.txt`
- `packages.txt`
- `runtime.txt`
- `.gitignore`
- `.env.example`
- `.streamlit/config.toml`
- `.streamlit/secrets.example.toml`
- `src/`
- `config/`
- `templates/`
- `テスト用サンプル契約書PDF/`

次のファイルやフォルダはGitHubに載せません。

- `.env`
- `.streamlit/secrets.toml`
- `.venv/`
- `outputs/`
- `dist/`
- `__pycache__/`

## 2. GitHubにリポジトリを作る

1. GitHubを開きます。
2. `New repository` を選びます。
3. リポジトリ名を例として `lease-judgment-demo` にします。
4. 公開範囲は、可能なら `Private` にします。
5. リポジトリを作成します。

## 3. ファイルをGitHubにアップロードする

GitHubの画面で `Add file` > `Upload files` を選び、このアプリのファイル一式をアップロードします。

アップロード前に `.env`、`outputs`、`dist` が含まれていないことを確認してください。

## 4. Streamlit Community Cloudでアプリを作る

1. Streamlit Community Cloudを開きます。
2. `New app` を選びます。
3. GitHubリポジトリを選びます。
4. Branchは通常 `main` を選びます。
5. Main file path は `app.py` を指定します。
6. App URLは任意の名前にします。

## 5. Secretsを設定する

サンプルデモだけなら、Secretsに次を入れます。

```toml
LLM_PROVIDER = "rule_based"
OCR_ENGINE = "none"
DEMO_MODE = "true"
OPENAI_MODEL = "gpt-5-mini"
```

OpenAI検証用を使う場合だけ、次を追加します。

```toml
OPENAI_API_KEY = "sk-..."
```

APIキーを使わないサンプル検証では、空欄のAPIキーを入れる必要はありません。

## 6. 社内共有時に添える注意文

社内の人にURLを共有するときは、次の文を添えてください。

```text
これはサンプル契約書専用のデモ版です。
実際の契約書、機密情報、個人情報、取引先を特定できる情報はアップロードしないでください。
Copilot等で作成した合成サンプル、または十分に匿名化・架空化した資料のみ使用してください。
```

## 7. 本物の契約書で検証したくなったら

Streamlit Community Cloudではなく、社内サーバー、社内VM、または社内承認済みクラウドに移してください。

その場合も、現在の `src/lease_judgment_engine.py` などの判定ロジックは流用できます。
