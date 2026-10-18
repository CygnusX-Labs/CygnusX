"""Static Alembic/model contract; does not execute PostgreSQL DDL."""

import sqlite3
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import BigInteger, CheckConstraint, UniqueConstraint

from cygnusx.infrastructure.database.models.download_execution import (
    DownloadExecutionAdmissionModel,
    DownloadExecutionBudgetModel,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def migration(monkeypatch):
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/dwnbinding02_harden_download_admission.py"
    )
    spec = spec_from_file_location("p0a_migration_contract", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    operations = MagicMock()
    monkeypatch.setattr(module, "op", operations)
    return SimpleNamespace(module=module, op=operations)


def test_bigint_and_unknown_measurement_contract(migration):
    budget = DownloadExecutionBudgetModel.__table__
    for field in [
        "limit_bytes",
        "reserved_bytes",
        "admitted_bytes",
        "disk_block_limit_bytes",
        "disk_inodes_limit",
    ]:
        assert isinstance(budget.c[field].type, BigInteger)
    assert budget.c.admitted_bytes.nullable
    assert budget.c.admitted_bytes.default is None
    assert budget.c.admitted_bytes.server_default is None
    assert isinstance(DownloadExecutionAdmissionModel.__table__.c.reserved_bytes.type, BigInteger)
    migration.module.upgrade()
    altered = {
        call.args[1]: call.kwargs
        for call in migration.op.alter_column.call_args_list
        if call.args[0] == "download_execution_budgets"
    }
    for field in ["limit_bytes", "reserved_bytes", "admitted_bytes"]:
        assert isinstance(altered[field]["type_"], BigInteger)
    assert altered["admitted_bytes"]["nullable"] is True


def test_model_constraints_and_restricted_foreign_keys(migration):
    budget = DownloadExecutionBudgetModel.__table__
    admission = DownloadExecutionAdmissionModel.__table__
    checks = {
        constraint.name: str(constraint.sqltext)
        for table in [budget, admission]
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "reserved_bytes <= limit_bytes" in checks["ck_download_budget_reservation"]
    assert "admitted_bytes IS NULL" in checks["ck_download_budget_measurement"]
    assert "disk_inodes_limit > 0" in checks["ck_download_budget_disk"]
    assert "execution_epoch >= 0" in checks["ck_download_admission_epoch"]
    unique = {
        tuple(column.name for column in constraint.columns)
        for constraint in admission.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert {("task_id",), ("ingestion_id",), ("task_id", "attempt_id", "execution_epoch")} <= unique
    for field in ["budget_id", "ingestion_id", "task_id", "owner_id", "project_id"]:
        assert len(admission.c[field].foreign_keys) == 1
        assert next(iter(admission.c[field].foreign_keys)).ondelete == "RESTRICT"
    migration.module.upgrade()
    assert {call.args[0] for call in migration.op.create_check_constraint.call_args_list} == set(
        checks
    )


def test_legacy_rows_fail_closed_and_status_fits(migration):
    assert migration.module.down_revision == "dwnadmission01"
    migration.module.upgrade()
    sql = " ".join(str(call.args[0]) for call in migration.op.execute.call_args_list)
    assert "admitted_bytes = NULL" in sql
    assert "revoked = true" in sql
    assert sql.count("status = 'RECONCILIATION_REQUIRED'") == 2
    for model in [DownloadExecutionBudgetModel, DownloadExecutionAdmissionModel]:
        assert model.__table__.c.status.type.length >= len("RECONCILIATION_REQUIRED")


@pytest.mark.parametrize("counts", [(1, 0, 0), (0, 1, 0), (0, 0, 1)])
def test_downgrade_refuses_any_audit_data_before_mutation(migration, counts):
    connection = migration.op.get_bind.return_value
    connection.execute.side_effect = [
        SimpleNamespace(scalar_one=lambda value=value: value) for value in counts
    ]
    with pytest.raises(RuntimeError, match="Admission audit data exists"):
        migration.module.downgrade()
    migration.op.drop_constraint.assert_not_called()
    migration.op.drop_column.assert_not_called()
    migration.op.alter_column.assert_not_called()


def test_empty_database_downgrade_narrows_only_after_guard(migration):
    connection = migration.op.get_bind.return_value
    connection.execute.return_value.scalar_one.return_value = 0
    migration.module.downgrade()
    assert connection.execute.call_count == 3
    assert migration.op.drop_column.call_count > 0


def test_budget_checks_admit_large_unknown_but_reject_invalid_values():
    checks = [
        str(constraint.sqltext)
        for constraint in DownloadExecutionBudgetModel.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    ]
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE budget (limit_bytes BIGINT NOT NULL, reserved_bytes BIGINT NOT NULL, admitted_bytes BIGINT, disk_block_limit_bytes BIGINT NOT NULL, disk_inodes_limit BIGINT NOT NULL, "
            + ", ".join("CHECK (" + check + ")" for check in checks)
            + ")"
        )
        # SQLite evaluates the actual model checks; this is not PG type/locking proof.
        valid = (1 << 32, 1 << 31, None, 1 << 32, 100)
        connection.execute("INSERT INTO budget VALUES (?, ?, ?, ?, ?)", valid)
        assert connection.execute("SELECT admitted_bytes FROM budget").fetchone()[0] is None
        for invalid in [
            (0, 0, None, 1, 1),
            (10, -1, None, 1, 1),
            (10, 11, None, 1, 1),
            (10, 5, -1, 1, 1),
            (10, 5, 6, 1, 1),
            (10, 5, None, 0, 1),
            (10, 5, None, 1, 0),
        ]:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO budget VALUES (?, ?, ?, ?, ?)", invalid)
    finally:
        connection.close()
