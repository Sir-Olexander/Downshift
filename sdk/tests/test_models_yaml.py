"""The shipped model table: every id resolves, prices exist, and the reasoning switches are explicit."""

import pytest

from downshift import UnsupportedReasoningError, default_table

LEVELS = ("on", "off", "low", "medium", "high")


def test_every_model_resolves_on_every_provider_it_lists():
    t = default_table()
    for m in t.models:
        assert m.ids, m.id
        for provider in m.ids:
            assert t.resolve(m.id, provider) == m.ids[provider]
            for level in LEVELS:  # every level is either a request mapping or an explicit "unsupported"
                try:
                    fields = t.reasoning_params(m.id, provider, level)
                except UnsupportedReasoningError:
                    continue
                assert isinstance(fields, dict)


def test_nemotron_levels_are_real_switches_not_silent_no_ops():
    t = default_table()
    assert not t.supports_reasoning("nemotron-3-nano", "tokenfactory", "low")
    assert t.reasoning_params("nemotron-3-super", "tokenfactory", "low") == {"chat_template_kwargs": {"low_effort": True}}
    assert t.reasoning_params("nemotron-3-ultra", "tokenfactory", "medium") == {"chat_template_kwargs": {"medium_effort": True}}
    assert t.reasoning_params("nemotron-3-nano", "tokenfactory", "off") == {"chat_template_kwargs": {"enable_thinking": False}}
    assert t.reasoning_params("nemotron-3-nano", "ollama", "off") == {"reasoning_effort": "none"}


def test_other_families_follow_their_probed_behaviour():
    t = default_table()
    assert t.reasoning_params("gpt-oss-20b", "ollama", "off") == {"reasoning_effort": "low"}
    assert t.reasoning_params("gemma-4-31b", "ollama", "off") == {}
    assert t.reasoning_params("gemma-4-31b", "ollama", "on") == {"reasoning_effort": "high"}
    assert t.reasoning_params("glm-5.3-flash", "ollama", "on") == {"reasoning_effort": "high"}
    assert t.reasoning_params("deepseek-v4.1-flash", "ollama", "off") == {"reasoning_effort": "none"}
    assert t.cost("gpt-oss-20b", 1_000_000, 0) == pytest.approx(0.03)
    assert len([m for m in t.models if m.vendor != "NVIDIA" and m.tier != "closed"]) == 7
