"""LLM access (Anthropic API locally, Amazon Bedrock Converse in AWS) with token/cost accounting."""
import json
import re
from contextvars import ContextVar
from functools import lru_cache

from app.config import settings

# Per-request usage accumulator (shared by reference across worker threads).
usage_var: ContextVar[dict | None] = ContextVar("llm_usage", default=None)


def _track(tokens_in: int, tokens_out: int) -> None:
    u = usage_var.get()
    if u is not None:
        u["in"] += tokens_in
        u["out"] += tokens_out
        u["calls"] += 1


def extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


class LLM:
    def complete(self, system: str, user: str, max_tokens: int = 2000) -> str:  # pragma: no cover
        raise NotImplementedError

    def complete_json(self, system: str, user: str, max_tokens: int = 2000) -> dict:
        text = self.complete(system, user, max_tokens)
        try:
            return extract_json(text)
        except ValueError:
            text = self.complete(system, user + "\n\nReturn ONLY a valid JSON object, no prose.", max_tokens)
            return extract_json(text)


class AnthropicLLM(LLM):
    def __init__(self):
        import anthropic

        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    def complete(self, system, user, max_tokens=2000):
        r = self.client.messages.create(
            model=settings.llm_model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        _track(r.usage.input_tokens, r.usage.output_tokens)
        return "".join(b.text for b in r.content if b.type == "text")


class BedrockLLM(LLM):
    def __init__(self):
        import boto3

        self.client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    def complete(self, system, user, max_tokens=2000):
        r = self.client.converse(
            modelId=settings.bedrock_model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": max_tokens},
        )
        _track(r["usage"]["inputTokens"], r["usage"]["outputTokens"])
        return "".join(p.get("text", "") for p in r["output"]["message"]["content"])


@lru_cache
def get_llm() -> LLM:
    return BedrockLLM() if settings.llm_provider == "bedrock" else AnthropicLLM()
