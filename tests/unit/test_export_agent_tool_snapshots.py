"""Tests for the isolated Agent snapshot export command."""

import pytest
from scripts.export_agent_tool_snapshots import _identity_ref


@pytest.mark.unit
def test_identity_ref_is_stable_and_does_not_expose_uuid() -> None:
    value = _identity_ref(__import__("uuid").UUID("00000000-0000-0000-0000-000000000001"))

    assert len(value) == 64
    assert "00000000-0000-0000-0000-000000000001" not in value
