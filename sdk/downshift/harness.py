"""The harness config: a versioned file that holds an agent's behaviour.

System prompt, tool descriptions, the step plan and the model + parameters for each step all
live here, not in Python. The SDK loads it at runtime; the optimizer writes new versions of it;
a pull request that changes this file is how improvements ship.

Two runtimes:
  research  the built-in research agent (plan / search / synthesize / verify steps, web_search and
            read_page tools). This is the default, so existing harness files keep working.
  custom    any other agent, run by its own code through an adapter (see downshift.adapter). Step
            kinds and tool names are whatever that agent uses; `contract` says what its code
            expects from the model, and the optimizer keeps steps, tools and contract unchanged.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

StepKind = Literal["plan", "search", "synthesize", "verify"]
RESEARCH_STEP_KINDS = ("plan", "search", "synthesize", "verify")
Runtime = Literal["research", "custom"]
Reasoning = Literal["on", "off", "low", "medium", "high"]


class HarnessError(ValueError):
    pass


def _reasoning(v: Any) -> Any:
    """YAML reads unquoted on/off as booleans; accept those (and "none") for the reasoning switch."""
    if v is True:
        return "on"
    if v is False:
        return "off"
    if isinstance(v, str) and v.strip().lower() in ("none", "false", "disabled"):
        return "off"
    if isinstance(v, str) and v.strip().lower() in ("true", "enabled"):
        return "on"
    return v


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    # JSON schema for the arguments. When omitted the agent uses its built-in schema for the tool.
    parameters: dict[str, Any] | None = None


class FewShot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str
    output: str


class Defaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    # null means "don't send it; use the provider's default" (how many agents call their model).
    temperature: float | None = 0.2
    max_tokens: int | None = 1024
    reasoning: Reasoning | None = None

    _norm_reasoning = field_validator("reasoning", mode="before")(_reasoning)


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    # research runtime: plan | search | synthesize | verify. custom runtime: any label the agent uses.
    kind: str
    # What the step does, in plain words. The optimizer reads it; custom agents should fill it in.
    description: str = ""
    prompt: str = ""
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    reasoning: Reasoning | None = None
    # search steps: cap on tool calls in the tool loop
    max_tool_calls: int | None = None
    few_shot: list[FewShot] = Field(default_factory=list)
    # verify steps: when the check fails, run the synthesize step once more with the findings
    retry_on_fail: bool = False
    enabled: bool = True

    _norm_reasoning = field_validator("reasoning", mode="before")(_reasoning)


class StepParams(BaseModel):
    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    reasoning: Reasoning | None = None


class Harness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: int | str = 1
    description: str = ""
    runtime: Runtime = "research"
    # custom runtime: what the agent's code requires of the model (output format, placeholders the
    # prompts may use). The optimizer must respect it and cannot change it.
    contract: str = ""
    defaults: Defaults
    system_prompt: str
    tools: dict[str, ToolSpec] = Field(default_factory=dict)
    steps: list[Step]
    # Free-form notes the optimizer leaves about what it changed and why.
    changelog: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_steps(self) -> "Harness":
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError(f"step ids must be unique, got {ids}")
        if not self.steps:
            raise ValueError("the harness needs at least one step")
        if any(not s.kind.strip() for s in self.steps):
            raise ValueError("every step needs a kind")
        if self.runtime == "research":
            bad = sorted({s.kind for s in self.steps if s.kind not in RESEARCH_STEP_KINDS})
            if bad:
                raise ValueError(f"research harness step kinds must be one of {list(RESEARCH_STEP_KINDS)}, got {bad} (set runtime: custom for other agents)")
            kinds = [s.kind for s in self.steps if s.enabled]
            if "search" not in kinds:
                raise ValueError("the harness needs an enabled step of kind 'search'")
            if "synthesize" not in kinds:
                raise ValueError("the harness needs an enabled step of kind 'synthesize'")
        elif not any(s.enabled for s in self.steps):
            raise ValueError("the harness needs at least one enabled step")
        return self

    @property
    def is_custom(self) -> bool:
        return self.runtime == "custom"

    # ---- lookups -------------------------------------------------------------------------
    def step(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise HarnessError(f"no step with id '{step_id}' (have {[s.id for s in self.steps]})")

    def steps_of_kind(self, kind: str) -> list[Step]:
        return [s for s in self.steps if s.kind == kind and s.enabled]

    def params(self, step: Step | str) -> StepParams:
        s = self.step(step) if isinstance(step, str) else step
        d = self.defaults
        return StepParams(
            model=s.model or d.model,
            temperature=d.temperature if s.temperature is None else s.temperature,
            max_tokens=d.max_tokens if s.max_tokens is None else s.max_tokens,
            reasoning=d.reasoning if s.reasoning is None else s.reasoning,
        )

    def models_used(self) -> list[str]:
        seen: list[str] = []
        for s in self.steps:
            if not s.enabled:
                continue
            m = self.params(s).model
            if m not in seen:
                seen.append(m)
        return seen

    def validate_models(self, table: Any, provider: str | None = None) -> None:
        """Raise HarnessError if a step uses a model the table doesn't know (or can't serve)."""
        for m in self.models_used():
            if not table.has(m):
                raise HarnessError(
                    f"model '{m}' is not in the model table ({', '.join(x.id for x in table.models)})"
                )
            if provider:
                table.resolve(m, provider)
        if provider and hasattr(table, "supports_reasoning"):
            for s in self.steps:
                if not s.enabled:
                    continue
                p = self.params(s)
                if p.reasoning is not None and not table.supports_reasoning(p.model, provider, p.reasoning):
                    raise HarnessError(
                        f"step '{s.id}': model '{p.model}' does not support reasoning: {p.reasoning} on provider '{provider}'"
                    )

    # ---- serialisation --------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json", exclude_none=True)
        # An explicit null default means "provider default"; keep it so it survives a round trip.
        for k in ("temperature", "max_tokens"):
            if getattr(self.defaults, k) is None:
                d["defaults"][k] = None
        if self.runtime == "research":
            d.pop("runtime", None)  # the default; keeps existing harness files and fingerprints unchanged
        if not self.contract:
            d.pop("contract", None)
        for step in d.get("steps") or []:
            if not step.get("description"):
                step.pop("description", None)
        return d

    def fingerprint(self) -> str:
        """Short content hash. Trailing whitespace and final newlines don't count as changes."""
        canon = json.dumps(_normalize_text(self.to_dict()), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]

    def to_yaml(self) -> str:
        return yaml.dump(
            self.to_dict(), Dumper=_BlockDumper, sort_keys=False, allow_unicode=True, width=100
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Harness":
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise HarnessError(_format_validation_error(e)) from None

    @classmethod
    def from_yaml(cls, text: str) -> "Harness":
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise HarnessError(f"harness is not valid YAML: {e}") from None
        if not isinstance(data, dict):
            raise HarnessError("harness YAML must be a mapping at the top level")
        return cls.from_dict(data)

    @classmethod
    def load(cls, path: str | Path) -> "Harness":
        p = Path(path)
        return cls.from_yaml(p.read_text(encoding="utf-8"))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_yaml(), encoding="utf-8")

    def copy_with(self, **changes: Any) -> "Harness":
        data = self.to_dict()
        data.update(changes)
        return Harness.from_dict(data)


def _normalize_text(value: Any) -> Any:
    if isinstance(value, str):
        return "\n".join(line.rstrip() for line in value.splitlines()).strip("\n")
    if isinstance(value, dict):
        return {k: _normalize_text(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_text(v) for v in value]
    return value


def _format_validation_error(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err.get("loc", ())) or "<root>"
        parts.append(f"{loc}: {err.get('msg')}")
    return "invalid harness: " + "; ".join(parts)


class _BlockDumper(yaml.SafeDumper):
    """YAML dumper that writes multi-line strings as readable `|` blocks."""


def _str_presenter(dumper: yaml.SafeDumper, data: str):  # type: ignore[no-untyped-def]
    if "\n" in data:
        cleaned = "\n".join(line.rstrip() for line in data.splitlines())
        if data.endswith("\n"):
            cleaned += "\n"
        return dumper.represent_scalar("tag:yaml.org,2002:str", cleaned, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_BlockDumper.add_representer(str, _str_presenter)
