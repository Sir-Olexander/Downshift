"""A model may override how its `reasoning` levels are sent, or declare a level unsupported."""

import pytest

from downshift import Harness, HarnessError, UnsupportedReasoningError
from downshift.pricing import ModelTable

TABLE = ModelTable({
    "providers": {
        "ollama": {
            "base_url": "https://ollama.com/v1",
            "api_key_env": "OLLAMA_API_KEY",
            "reasoning": {"off": {"reasoning_effort": "none"}, "on": {}, "low": {"reasoning_effort": "low"}},
        },
        "tokenfactory": {
            "base_url": "https://api.tokenfactory.nebius.com/v1/",
            "api_key_env": "NEBIUS_API_KEY",
            "reasoning": {"off": {"chat_template_kwargs": {"enable_thinking": False}}, "on": {}},
        },
    },
    "models": {
        "plain": {"display": "Plain", "ids": {"ollama": "plain", "tokenfactory": "org/plain"}},
        # this family ignores reasoning_effort "none"; its smallest setting is "low"
        "oss": {"display": "OSS", "ids": {"ollama": "oss"}, "reasoning": {"ollama": {"off": {"reasoning_effort": "low"}}}},
        # this model cannot stop thinking on this provider at all
        "always-thinks": {"display": "AT", "ids": {"ollama": "at"}, "reasoning": {"ollama": {"off": None}}},
    },
})


def test_provider_mapping_applies_when_the_model_has_no_override():
    assert TABLE.reasoning_params("plain", "ollama", "off") == {"reasoning_effort": "none"}
    assert TABLE.reasoning_params("plain", "tokenfactory", "off") == {"chat_template_kwargs": {"enable_thinking": False}}
    assert TABLE.reasoning_params("plain", "ollama", None) == {}


def test_model_override_wins_only_for_the_levels_it_names():
    assert TABLE.reasoning_params("oss", "ollama", "off") == {"reasoning_effort": "low"}
    assert TABLE.reasoning_params("oss", "ollama", "low") == {"reasoning_effort": "low"}  # provider mapping
    assert TABLE.supports_reasoning("oss", "ollama", "off")


def test_null_level_is_unsupported():
    with pytest.raises(UnsupportedReasoningError):
        TABLE.reasoning_params("always-thinks", "ollama", "off")
    assert not TABLE.supports_reasoning("always-thinks", "ollama", "off")
    assert TABLE.supports_reasoning("always-thinks", "ollama", "on")


def _harness(model: str, reasoning: str) -> Harness:
    return Harness.from_dict({
        "name": "t", "version": 1, "runtime": "custom", "description": "test",
        "defaults": {"model": model, "temperature": None, "max_tokens": None, "reasoning": reasoning},
        "system_prompt": "x", "tools": {},
        "steps": [{"id": "agent", "kind": "tool_loop"}],
    })


def test_harness_validation_rejects_an_unsupported_reasoning_level():
    h = _harness("always-thinks", "off")
    h.validate_models(TABLE)  # without a provider only the model ids are checked
    with pytest.raises(HarnessError, match="does not support reasoning: off"):
        h.validate_models(TABLE, "ollama")
    _harness("oss", "off").validate_models(TABLE, "ollama")
    _harness("always-thinks", "on").validate_models(TABLE, "ollama")


def test_model_to_dict_exposes_overrides():
    assert TABLE.get("oss").to_dict()["reasoning"] == {"ollama": {"off": {"reasoning_effort": "low"}}}
    assert TABLE.get("plain").to_dict()["reasoning"] == {}
