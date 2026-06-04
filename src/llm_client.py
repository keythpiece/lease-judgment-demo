from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from .utils import env, load_environment


SYSTEM_PROMPT = """あなたはリース会計の契約識別レビュー担当です。
契約書本文に基づき、リース対象か否かを判定してください。
契約名や請求名だけで判断せず、特定された物理資産を一定期間使用する権利があるかを最重視してください。
サービス提供、容量提供、クラウド利用、成果物提供は原則としてリース対象外候補ですが、特定の物理資産を利用者が一定期間使用する権利を有する場合はリース候補です。
提供者が自由に資産を入れ替えられる場合は特定資産なし候補です。
経済的便益を誰が得るか、使用方法・使用目的を誰が決めるかを必ず確認してください。
情報不足の場合は推測せず要人手確認としてください。
各判定には契約書本文の根拠引用を付け、根拠引用がない判定はしないでください。
出力は必ず指定JSON形式にしてください。"""


class LLMClient(ABC):
    provider = "unknown"
    model = ""

    @abstractmethod
    def judge(self, prompt: str, schema_hint: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError


class RuleBasedClient(LLMClient):
    provider = "rule_based"

    def judge(self, prompt: str, schema_hint: dict[str, Any]) -> dict[str, Any] | None:
        return None


class OpenAIClient(LLMClient):
    provider = "openai"

    def __init__(self) -> None:
        from openai import OpenAI

        self.model = env("OPENAI_MODEL", "gpt-5-mini")
        api_key = env("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env or Streamlit Secrets.")
        self.client = OpenAI(api_key=api_key)

    def judge(self, prompt: str, schema_hint: dict[str, Any]) -> dict[str, Any] | None:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)


class ClaudeClient(LLMClient):
    provider = "claude"

    def __init__(self) -> None:
        import anthropic

        self.model = env("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
        self.client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))

    def judge(self, prompt: str, schema_hint: dict[str, Any]) -> dict[str, Any] | None:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
        return json.loads(text)


def build_llm_client(provider: str | None = None) -> LLMClient:
    load_environment()
    provider = (provider or env("LLM_PROVIDER", "rule_based")).lower()
    if provider == "openai":
        return OpenAIClient()
    if provider in {"claude", "anthropic"}:
        return ClaudeClient()
    return RuleBasedClient()
