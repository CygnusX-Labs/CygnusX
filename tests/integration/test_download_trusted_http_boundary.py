"""Authorized real-environment harness contract; default is explicitly NOT_TESTED.

An operations-owned pytest plugin may override trusted_http_driver after approval.
The driver MUST use real Task/Worker/CLI/registry and authenticated OS observations,
not doubles. This module never enables a gate, starts an origin or installs policy.
"""

from typing import Protocol
from uuid import UUID

import pytest

from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryObservation,
    require_quiescent,
)

pytestmark = pytest.mark.integration


class TrustedHttpDriver(Protocol):
    async def run_case(self, case: str) -> ExecutionBoundaryObservation:
        """Use explicitly approved targets/limits; return authenticated OS facts."""
        ...

    async def verify_registry_and_dataset(self, task_id: UUID, *, complete: bool) -> None:
        """Assert real FileRecord owner/task/source/size/SHA and Dataset policy.

        Save Task/scope, raw counter units/limits, quota reports, observed address
        decisions, empty process tree, stable file SHA and FileRecord IDs. Partial
        cases must inspect actual files and original reconcile, never insert a
        synthetic FileRecord or promote partial output to scientific READY.
        """
        ...


@pytest.fixture
def trusted_http_driver() -> TrustedHttpDriver:
    pytest.skip("NOT_TESTED: authorized OS supervisor and real HTTP driver unavailable")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("small_file", "completed"),
        ("unauthorized_address", "policy_denied"),
        ("unauthorized_redirect", "policy_denied"),
        ("unknown_length", "completed"),
        ("network_over_budget", "network_limit"),
        ("disk_quota_exhausted", "disk_limit"),
        ("cancel", "cancelled"),
        ("worker_sigkill", "worker_lost"),
        ("partial_reconciliation", "failed"),
    ],
)
async def test_real_http_boundary(
    trusted_http_driver: TrustedHttpDriver, case: str, reason: str
) -> None:
    observation = await trusted_http_driver.run_case(case)
    require_quiescent(observation, observation.task_id, observation.scope_ref)
    assert observation.reason == reason
    if reason == "completed":
        assert observation.returncode == 0
        assert observation.rx_admitted_bytes > 0
        assert observation.disk_peak_allocated_bytes > 0
        assert observation.inode_peak_used > 0
    await trusted_http_driver.verify_registry_and_dataset(
        observation.task_id, complete=reason == "completed"
    )
