from pathlib import Path

import pytest

from downshift import Harness, HarnessError, default_table

BASELINE = Path(__file__).resolve().parents[2] / "demo_agent" / "harness.yaml"


def test_baseline_loads_and_merges_params():
    h = Harness.load(BASELINE)
    assert h.name == "research-agent"
    p = h.params("plan")
    assert p.model == "nemotron-3-ultra"
    assert p.max_tokens == 1200  # step override
    assert p.temperature == 0.2  # default
    assert h.models_used() == ["nemotron-3-ultra"]
    h.validate_models(default_table(), "ollama")


def test_yaml_roundtrip_keeps_fingerprint():
    h = Harness.load(BASELINE)
    again = Harness.from_yaml(h.to_yaml())
    assert again.fingerprint() == h.fingerprint()
    assert "|" in h.to_yaml()  # multi-line prompts are block scalars


def test_rejects_unknown_fields_and_missing_steps():
    h = Harness.load(BASELINE).to_dict()
    h["unknown_key"] = 1
    with pytest.raises(HarnessError):
        Harness.from_dict(h)
    h.pop("unknown_key")
    h["steps"] = [s for s in h["steps"] if s["kind"] != "synthesize"]
    with pytest.raises(HarnessError):
        Harness.from_dict(h)


def test_unknown_model_is_rejected_by_validate_models():
    h = Harness.load(BASELINE).copy_with(defaults={"model": "nemotron-9000"})
    with pytest.raises(HarnessError):
        h.validate_models(default_table())
