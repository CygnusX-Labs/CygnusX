"""Offline interface invariants only; no simulated runtime certification."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryObservation,
    ExecutionBoundaryRequest,
    require_quiescent,
)

pytestmark = pytest.mark.unit
TASK = UUID(int=1)
SCOPE = UUID(int=2)


@pytest.mark.parametrize("field", ["caller_kind", "certified", "argv", "env", "mounts"])
def test_request_cannot_carry_caller_claims_or_process_configuration(field: str) -> None:
    with pytest.raises(ValidationError):
        ExecutionBoundaryRequest.model_validate(
            {
                "task_id": TASK,
                "owner_id": UUID(int=3),
                "attempt_id": UUID(int=6),
                "execution_id": UUID(int=7),
                "execution_epoch": 1,
                "admission_ref": UUID(int=4),
                "budget_ref": UUID(int=5),
                field: "untrusted",
            }
        )


@pytest.mark.parametrize("protocol", ["https", "ftp", "sra.aws", "oss", "tos", "obs"])
def test_interface_does_not_implicitly_enable_other_protocols(protocol: str) -> None:
    with pytest.raises(ValidationError):
        ExecutionBoundaryRequest.model_validate(
            {
                "task_id": TASK,
                "owner_id": UUID(int=3),
                "attempt_id": UUID(int=6),
                "execution_id": UUID(int=7),
                "execution_epoch": 1,
                "admission_ref": UUID(int=4),
                "budget_ref": UUID(int=5),
                "protocol": protocol,
            }
        )


@pytest.mark.parametrize(
    "change",
    [
        {"task_id": UUID(int=99)},
        {"scope_ref": UUID(int=99)},
        {"state": "unknown"},
        {"live_processes": 1},
        {"cgroup_populated": True},
        {"egress_revoked": False},
        {"quota_enforced": False},
        {"cleanup_complete": False},
        {"reason": "unknown"},
        {"rx_admitted_bytes": 101, "rx_observed_bytes": 101},
        {"disk_peak_allocated_bytes": 101},
        {"inode_peak_used": 11},
    ],
)
def test_reconciliation_rejects_unsafe_or_unattributed_observations(
    change: dict[str, object],
) -> None:
    data: dict[str, object] = {
        "task_id": TASK,
        "scope_ref": SCOPE,
        "execution_id": UUID(int=7),
        "execution_epoch": 1,
        "policy_revision": "test-contract",
        "state": "stopped",
        "reason": "cancelled",
        "rx_admitted_bytes": 10,
        "rx_observed_bytes": 10,
        "rx_dropped_bytes": 0,
        "rx_limit_bytes": 100,
        "disk_peak_allocated_bytes": 10,
        "disk_limit_bytes": 100,
        "inode_peak_used": 2,
        "inode_limit": 10,
        "started_at": 1,
        "stopped_at": 2,
        "live_processes": 0,
        "cgroup_populated": False,
        "egress_revoked": True,
        "quota_enforced": True,
        "cleanup_complete": True,
        "returncode": -15,
    }
    data.update(change)
    observation = ExecutionBoundaryObservation.model_validate(data)
    with pytest.raises(ValueError, match="RECONCILIATION_REQUIRED"):
        require_quiescent(observation, TASK, SCOPE)


def test_observation_requires_measured_inode_usage() -> None:
    data: dict[str, object] = {
        "task_id": TASK,
        "scope_ref": SCOPE,
        "execution_id": UUID(int=7),
        "execution_epoch": 1,
        "policy_revision": "test-contract",
        "state": "stopped",
        "reason": "completed",
        "rx_admitted_bytes": 10,
        "rx_observed_bytes": 10,
        "rx_dropped_bytes": 0,
        "rx_limit_bytes": 100,
        "disk_peak_allocated_bytes": 10,
        "disk_limit_bytes": 100,
        "inode_limit": 10,
        "started_at": 1,
        "stopped_at": 2,
        "live_processes": 0,
        "cgroup_populated": False,
        "egress_revoked": True,
        "quota_enforced": True,
        "cleanup_complete": True,
        "returncode": 0,
    }
    with pytest.raises(ValidationError, match="inode_peak_used"):
        ExecutionBoundaryObservation.model_validate(data)


def test_rx_observation_distinguishes_admitted_and_dropped_host_traffic() -> None:
    data: dict[str, object] = {
        "task_id": TASK,
        "scope_ref": SCOPE,
        "execution_id": UUID(int=7),
        "execution_epoch": 1,
        "policy_revision": "test-contract",
        "state": "stopped",
        "reason": "network_limit",
        "rx_admitted_bytes": 100,
        "rx_observed_bytes": 120,
        "rx_dropped_bytes": 20,
        "rx_limit_bytes": 100,
        "disk_peak_allocated_bytes": 10,
        "disk_limit_bytes": 100,
        "inode_peak_used": 2,
        "inode_limit": 10,
        "started_at": 1,
        "stopped_at": 2,
        "live_processes": 0,
        "cgroup_populated": False,
        "egress_revoked": True,
        "quota_enforced": True,
        "cleanup_complete": True,
        "returncode": 1,
    }
    observation = ExecutionBoundaryObservation.model_validate(data)
    require_quiescent(observation, TASK, SCOPE)
