"""One small provider layer: every model call goes through LLM.chat().

A provider is an OpenAI-compatible base_url plus a key and a model-ID mapping (see models.yaml).
Switching from Ollama to Nebius Token Factory is a one-line env change (DOWNSHIFT_PROVIDER).
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any

import openai

from .pricing import ModelTable, ProviderInfo, default_table

PROVIDER_PREFERENCE = ("tokenfactory", "ollama", "ollama-local", "openai")


class LLMError(RuntimeError):
    pass


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
            "raw_arguments": self.raw_arguments,
        }


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCallRequest]
    reasoning: str | None
    tokens_in: int
    tokens_out: int
    latency_ms: int
    finish_reason: str | None
    model: str
    provider: str
    provider_model: str
    attempts: int = 1
    extra: dict[str, Any] = field(default_factory=dict)

    def response_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "reasoning": self.reasoning,
            "finish_reason": self.finish_reason,
        }

    def assistant_message(self) -> dict[str, Any]:
        """The assistant turn to append to a conversation (OpenAI format)."""
        msg: dict[str, Any] = {"role": "assistant", "content": self.content or None}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.raw_arguments},
                }
                for tc in self.tool_calls
            ]
        return msg


def active_provider_name(table: ModelTable | None = None) -> str:
    """Provider from DOWNSHIFT_PROVIDER, else the first preferred provider that has a key."""
    table = table or default_table()
    explicit = os.environ.get("DOWNSHIFT_PROVIDER")
    if explicit:
        return explicit
    for name in PROVIDER_PREFERENCE:
        try:
            p = table.provider(name)
        except KeyError:
            continue
        if p.api_key():
            return name
    return "ollama-local"


class LLM:
    """Thin OpenAI-compatible chat client with retries, pricing and reasoning controls."""

    def __init__(
        self,
        provider: str | None = None,
        *,
        table: ModelTable | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 180.0,
        max_retries: int = 3,
    ):
        self.table = table or default_table()
        self.provider_name = provider or active_provider_name(self.table)
        self.provider: ProviderInfo = self.table.provider(self.provider_name)
        key = api_key or os.environ.get("DOWNSHIFT_API_KEY_OVERRIDE") or self.provider.api_key()
        if not key:
            if self.provider.api_key_optional:
                key = "ollama"
            else:
                raise LLMError(
                    f"No API key for provider '{self.provider_name}': set {self.provider.api_key_env}"
                )
        self.base_url = base_url or os.environ.get("DOWNSHIFT_BASE_URL") or self.provider.base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = openai.OpenAI(
            base_url=self.base_url, api_key=key, timeout=timeout, max_retries=0
        )

    def resolve(self, model: str) -> str:
        return self.table.resolve(model, self.provider_name)

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning: str | None = None,
        response_format: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ChatResult:
        provider_model = self.resolve(model)
        kwargs: dict[str, Any] = {"model": provider_model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_format is not None:
            kwargs["response_format"] = response_format
        extra_body: dict[str, Any] = {}
        extra_body.update(self.provider.reasoning_params(reasoning))
        if extra:
            extra_body.update(extra)
        if extra_body:
            kwargs["extra_body"] = extra_body

        attempt = 0
        last_err: Exception | None = None
        while attempt < max(1, self.max_retries):
            attempt += 1
            t0 = time.perf_counter()
            try:
                resp = self._client.chat.completions.create(**kwargs)
                latency_ms = int((time.perf_counter() - t0) * 1000)
                return self._parse(resp, model, provider_model, latency_ms, attempt)
            except (
                openai.RateLimitError,
                openai.APIConnectionError,
                openai.APITimeoutError,
                openai.InternalServerError,
            ) as e:
                last_err = e
                if attempt >= self.max_retries:
                    break
                time.sleep(min(20.0, (2 ** (attempt - 1)) + random.random()))
            except openai.APIStatusError as e:
                raise LLMError(f"{self.provider_name} {provider_model}: {e}") from e
        raise LLMError(
            f"{self.provider_name} {provider_model}: giving up after {attempt} attempts: {last_err}"
        ) from last_err

    def _parse(self, resp: Any, model: str, provider_model: str, latency_ms: int, attempts: int) -> ChatResult:
        choice = resp.choices[0]
        message = choice.message
        content = message.content or ""
        tool_calls: list[ToolCallRequest] = []
        for tc in message.tool_calls or []:
            raw = tc.function.arguments or "{}"
            try:
                args = json.loads(raw)
                if not isinstance(args, dict):
                    args = {"value": args}
            except json.JSONDecodeError:
                args = {"_unparsed": raw}
            tool_calls.append(ToolCallRequest(id=tc.id or f"call_{len(tool_calls)}", name=tc.function.name, arguments=args, raw_arguments=raw))
        extra_fields = getattr(message, "model_extra", None) or {}
        reasoning = extra_fields.get("reasoning") or extra_fields.get("reasoning_content")
        usage = getattr(resp, "usage", None)
        tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
        return ChatResult(
            content=content,
            tool_calls=tool_calls,
            reasoning=reasoning if isinstance(reasoning, str) else None,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            finish_reason=getattr(choice, "finish_reason", None),
            model=model,
            provider=self.provider_name,
            provider_model=provider_model,
            attempts=attempts,
        )
