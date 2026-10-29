"""Model table: IDs, prices and provider mappings, loaded from models.yaml.

Everything that needs a model ID or a price goes through here, so there is exactly one
file to edit when Token Factory changes a name or a price.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_TABLE_PATH = Path(__file__).with_name("models.yaml")


class UnknownModelError(KeyError):
    pass


class UnknownProviderError(KeyError):
    pass


@dataclass(frozen=True)
class ModelInfo:
    id: str
    display: str
    tier: str
    vendor: str
    size: str
    context: int | None
    input_per_1m: float | None
    output_per_1m: float | None
    cached_input_per_1m: float | None
    ids: dict[str, str]

    def cost(self, tokens_in: int, tokens_out: int) -> float | None:
        """Cost in USD for a call, or None when the model has no price."""
        if self.input_per_1m is None or self.output_per_1m is None:
            return None
        return (tokens_in * self.input_per_1m + tokens_out * self.output_per_1m) / 1_000_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display": self.display,
            "tier": self.tier,
            "vendor": self.vendor,
            "size": self.size,
            "context": self.context,
            "price_per_1m": {
                "input": self.input_per_1m,
                "output": self.output_per_1m,
                "cached_input": self.cached_input_per_1m,
            },
            "ids": dict(self.ids),
        }


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    label: str
    base_url: str
    api_key_env: str
    api_key_optional: bool
    reasoning: dict[str, dict[str, Any]]
    # Other variable names that may hold the same key (e.g. TOKEN_FACTORY_API_KEY for NEBIUS_API_KEY)
    api_key_env_aliases: tuple[str, ...] = ()

    def api_key(self) -> str | None:
        for name in (self.api_key_env, *self.api_key_env_aliases):
            if os.environ.get(name):
                return os.environ[name]
        return None

    def reasoning_params(self, setting: str | None) -> dict[str, Any]:
        """Extra request fields that express a harness `reasoning` setting on this provider."""
        if setting is None:
            return {}
        return dict(self.reasoning.get(str(setting), {}))


class ModelTable:
    def __init__(self, data: dict[str, Any], path: Path | None = None):
        self.path = path
        self.pricing = dict(data.get("pricing") or {})
        self._providers: dict[str, ProviderInfo] = {}
        for name, p in (data.get("providers") or {}).items():
            self._providers[name] = ProviderInfo(
                name=name,
                label=p.get("label", name),
                base_url=p["base_url"],
                api_key_env=p.get("api_key_env", ""),
                api_key_optional=bool(p.get("api_key_optional", False)),
                reasoning={str(k): dict(v or {}) for k, v in (p.get("reasoning") or {}).items()},
                api_key_env_aliases=tuple(p.get("api_key_env_aliases") or ()),
            )
        self._models: dict[str, ModelInfo] = {}
        for mid, m in (data.get("models") or {}).items():
            price = m.get("price_per_1m") or {}
            self._models[mid] = ModelInfo(
                id=mid,
                display=m.get("display", mid),
                tier=m.get("tier", ""),
                vendor=m.get("vendor", ""),
                size=m.get("size", ""),
                context=m.get("context"),
                input_per_1m=price.get("input"),
                output_per_1m=price.get("output"),
                cached_input_per_1m=price.get("cached_input"),
                ids={str(k): str(v) for k, v in (m.get("ids") or {}).items()},
            )

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "ModelTable":
        p = Path(path or os.environ.get("DOWNSHIFT_MODELS_FILE") or DEFAULT_TABLE_PATH)
        with open(p, "r", encoding="utf-8") as f:
            return cls(yaml.safe_load(f) or {}, path=p)

    @property
    def models(self) -> list[ModelInfo]:
        return list(self._models.values())

    @property
    def providers(self) -> list[ProviderInfo]:
        return list(self._providers.values())

    def has(self, model_id: str) -> bool:
        return model_id in self._models

    def get(self, model_id: str) -> ModelInfo:
        try:
            return self._models[model_id]
        except KeyError:
            known = ", ".join(sorted(self._models))
            raise UnknownModelError(f"Unknown model '{model_id}'. Known models: {known}") from None

    def provider(self, name: str) -> ProviderInfo:
        try:
            return self._providers[name]
        except KeyError:
            known = ", ".join(sorted(self._providers))
            raise UnknownProviderError(
                f"Unknown provider '{name}'. Known providers: {known}"
            ) from None

    def resolve(self, model_id: str, provider: str) -> str:
        """Provider-specific model string for a canonical model ID."""
        info = self.get(model_id)
        try:
            return info.ids[provider]
        except KeyError:
            raise UnknownModelError(
                f"Model '{model_id}' has no ID for provider '{provider}' "
                f"(available: {', '.join(sorted(info.ids)) or 'none'})"
            ) from None

    def cost(self, model_id: str, tokens_in: int, tokens_out: int) -> float | None:
        if model_id not in self._models:
            return None
        return self._models[model_id].cost(tokens_in, tokens_out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pricing": self.pricing,
            "models": [m.to_dict() for m in self.models],
            "providers": [
                {
                    "name": p.name,
                    "label": p.label,
                    "base_url": p.base_url,
                    "api_key_env": p.api_key_env,
                    "configured": bool(p.api_key()) or p.api_key_optional,
                }
                for p in self.providers
            ],
        }


@functools.lru_cache(maxsize=1)
def default_table() -> ModelTable:
    return ModelTable.load()
