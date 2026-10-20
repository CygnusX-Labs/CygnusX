"""Memory config drift fails closed without evaluating application configuration."""

from pathlib import Path
from runpy import run_path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[2]
_check = run_path(str(_ROOT / "scripts/check_env_example_drift.py"))["check_drift"]
_CONFIG = """
class Settings:
    memory_v2_enabled: bool = False
    memory_settle_max_messages: int = Field(default=30, ge=1)
    memory_fact_time_decay_lambda: float = 0.02
    agent_memory_embedding_model: str = ""
"""
_EXAMPLE = """
MEMORY_V2_ENABLED=false
MEMORY_SETTLE_MAX_MESSAGES=30
MEMORY_FACT_TIME_DECAY_LAMBDA=0.02
AGENT_MEMORY_EMBEDDING_MODEL=
"""


def test_real_example_matches_literal_settings_defaults():
    assert (
        _check(
            (_ROOT / "src/cygnusx/core/config.py").read_text(), (_ROOT / ".env.example").read_text()
        )
        == []
    )


@pytest.mark.parametrize(
    "tail, expected",
    [
        ("MEMORY_V2_ENABLED=true", "duplicate assignment"),
        ("AGENT_MEMORY_OBSOLETE=secret-value", "no matching Settings field"),
    ],
)
def test_duplicates_and_unconsumed_memory_variables_are_rejected(tail, expected):
    issues = _check(_CONFIG, _EXAMPLE + tail)
    assert any(expected in issue for issue in issues)
    assert all("secret-value" not in issue for issue in issues)


def test_missing_and_changed_defaults_are_rejected_without_echoing_values():
    changed = _EXAMPLE.replace("MEMORY_V2_ENABLED=false", "MEMORY_V2_ENABLED=private-value")
    changed = changed.replace("MEMORY_SETTLE_MAX_MESSAGES=30", "# MEMORY_SETTLE_MAX_MESSAGES=30")
    issues = _check(_CONFIG, changed)
    assert any("MEMORY_V2_ENABLED: example differs" in item for item in issues)
    assert any("MEMORY_SETTLE_MAX_MESSAGES: missing" in item for item in issues)
    assert all("private-value" not in item for item in issues)


def test_comments_and_protected_mem0_remnants_are_ignored():
    assert _check(_CONFIG, _EXAMPLE + "\nMEM0_ENGINE_ENABLED=true\n# MEMORY_UNKNOWN=1") == []


def test_config_is_parsed_without_executing_code():
    assert _check("raise RuntimeError('must not execute')\n" + _CONFIG, _EXAMPLE) == []


@pytest.mark.parametrize("invalid", ["nan", "inf", "30.5"])
def test_invalid_numeric_example_fails(invalid):
    assert _check(_CONFIG, _EXAMPLE.replace("MESSAGES=30", "MESSAGES=" + invalid))


def test_unsupported_default_expression_fails_closed():
    with pytest.raises(ValueError, match="unsupported default expression"):
        _check(_CONFIG.replace("bool = False", "bool = get_runtime_default()"), _EXAMPLE)


def test_optional_numeric_default_must_remain_explicitly_unconfigured_in_example():
    config = _CONFIG + "\n    memory_hybrid_min_similarity: float | None = Field(default=None)\n"
    example = _EXAMPLE + "\nMEMORY_HYBRID_MIN_SIMILARITY=\n"
    assert _check(config, example) == []
    assert any(
        "differs" in item
        for item in _check(config, example.replace("SIMILARITY=", "SIMILARITY=0.5"))
    )
