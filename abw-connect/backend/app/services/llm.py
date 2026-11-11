"""LLM client interface: Bedrock Converse, plus a local/offline stub.

The stub raises so the generator falls back to extractive. Tests inject fakes.
"""
from __future__ import annotations

from typing import Protocol

from ..config import AWS_REGION, BEDROCK_MODEL_ID, LLM_TIMEOUT_S, use_aws


class LLMError(RuntimeError):
    pass


class LLMTimeout(LLMError):
    pass


class LLMClient(Protocol):
    name: str

    def complete(
        self,
        system: str,
        user: str,
        *,
        timeout_s: float = LLM_TIMEOUT_S,
        max_tokens: int = 2500,
    ) -> str: ...


class OfflineLLM:
    """No credentials / no network. Asking it to complete always fails closed."""

    name = "offline"

    def complete(self, system: str, user: str, *, timeout_s: float = LLM_TIMEOUT_S, max_tokens: int = 2500) -> str:
        raise LLMError("LLM is not configured; running in extractive/offline mode")


class BedrockConverseLLM:
    """Amazon Bedrock Converse API. Model id is configurable via BEDROCK_MODEL_ID."""

    def __init__(self, model_id: str | None = None, region: str | None = None):
        self.model_id = model_id or BEDROCK_MODEL_ID
        self.region = region or AWS_REGION
        self.name = f"bedrock:{self.model_id}"
        self._client = None

    def _client_get(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                config=Config(read_timeout=int(LLM_TIMEOUT_S) + 5, retries={"max_attempts": 1}),
            )
        return self._client

    def complete(
        self,
        system: str,
        user: str,
        *,
        timeout_s: float = LLM_TIMEOUT_S,
        max_tokens: int = 2500,
    ) -> str:
        import botocore.exceptions

        try:
            resp = self._client_get().converse(
                modelId=self.model_id,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
            )
        except botocore.exceptions.ReadTimeoutError as e:
            raise LLMTimeout(str(e)) from e
        except Exception as e:
            raise LLMError(f"{type(e).__name__}: {e}") from e
        parts = []
        for block in ((resp.get("output") or {}).get("message") or {}).get("content") or []:
            if "text" in block:
                parts.append(block["text"])
        return "\n".join(parts)


def get_llm() -> LLMClient:
    if use_aws():
        return BedrockConverseLLM()
    return OfflineLLM()
