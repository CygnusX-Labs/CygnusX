from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cygnusx.infrastructure.database.models.download_execution import (
    DownloadExecutionAdmissionModel,
    DownloadExecutionBudgetModel,
)
from cygnusx.infrastructure.database.repositories.download_execution_admission import (
    DownloadExecutionAdmissionError,
    consume_execution_admission,
    issue_processed_http_admission,
    reserve_execution_budget,
    resolve_execution_admission,
    revoke_execution_admission,
)

pytestmark = pytest.mark.unit


class _AsyncSessionFacade:
    def __init__(self, engine) -> None:
        self.session = Session(engine)

    def get_bind(self):
        return self.session.get_bind()

    def add(self, instance) -> None:
        self.session.add(instance)

    async def execute(self, statement):
        return self.session.execute(statement)

    async def flush(self) -> None:
        self.session.flush()

    async def commit(self) -> None:
        self.session.commit()

    async def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        self.session.close()


@pytest.fixture
def admission_db():
    engine = create_engine("sqlite://")
    DownloadExecutionBudgetModel.__table__.create(engine)
    DownloadExecutionAdmissionModel.__table__.create(engine)
    yield engine
    engine.dispose()


def _ids() -> dict[str, UUID]:
    return {name: UUID(int=value) for name, value in {
        "ingestion": 9101,
        "task": 9102,
        "owner": 9103,
        "project": 9104,
    }.items()}


async def test_processed_http_admission_is_bound_and_consumed_once(admission_db):
    ids = _ids()
    session = _AsyncSessionFacade(admission_db)
    expires = datetime.now(UTC) + timedelta(minutes=5)
    admission = await issue_processed_http_admission(
        session,
        ingestion_id=ids["ingestion"],
        task_id=ids["task"],
        owner_id=ids["owner"],
        project_id=ids["project"],
        confirmation_id="confirmation-1",
        request_digest="a" * 64,
        limit_bytes=100,
        policy_revision="http-policy-v1",
        environment_id="acceptance-linux-v1",
        caller_id="worker-1",
        allowed_destinations=[{"host": "source.example", "port": 443}],
        expires_at=expires,
    )
    await session.commit()

    consumed = await consume_execution_admission(
        session,
        admission.id,
        task_id=ids["task"],
        owner_id=ids["owner"],
        request_digest="a" * 64,
        caller_id="worker-1",
    )
    assert consumed.status == "CONSUMED"
    assert consumed.execution_epoch == 1
    await session.commit()

    with pytest.raises(DownloadExecutionAdmissionError, match="DOWNLOAD_ADMISSION_REJECTED"):
        await resolve_execution_admission(
            session,
            admission.id,
            UUID(int=9999),
            task_id=ids["task"],
            owner_id=ids["owner"],
            caller_id="worker-1",
        )

    with pytest.raises(DownloadExecutionAdmissionError, match="DOWNLOAD_ADMISSION_REJECTED"):
        await consume_execution_admission(
            session,
            admission.id,
            task_id=ids["task"],
            owner_id=ids["owner"],
            request_digest="a" * 64,
            caller_id="worker-1",
        )
    session.close()


async def test_resolver_requires_both_server_issued_references(admission_db):
    ids = _ids()
    session = _AsyncSessionFacade(admission_db)
    admission = await issue_processed_http_admission(
        session,
        ingestion_id=ids["ingestion"],
        task_id=ids["task"],
        owner_id=ids["owner"],
        project_id=ids["project"],
        confirmation_id="confirmation-resolve",
        request_digest="d" * 64,
        limit_bytes=100,
        policy_revision="http-policy-v1",
        environment_id="acceptance-linux-v1",
        caller_id="worker-1",
        allowed_destinations=[{"host": "source.example", "port": 443}],
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    await session.commit()
    resolved, budget = await resolve_execution_admission(
        session,
        admission.id,
        admission.budget_id,
        task_id=ids["task"],
        owner_id=ids["owner"],
        caller_id="worker-1",
    )
    assert resolved.id == admission.id
    assert budget.id == admission.budget_id
    session.close()


async def test_budget_reservation_is_conditional_and_revoke_blocks_consumption(admission_db):
    ids = _ids()
    session = _AsyncSessionFacade(admission_db)
    admission = await issue_processed_http_admission(
        session,
        ingestion_id=ids["ingestion"],
        task_id=ids["task"],
        owner_id=ids["owner"],
        project_id=ids["project"],
        confirmation_id="confirmation-2",
        request_digest="b" * 64,
        limit_bytes=100,
        policy_revision="http-policy-v1",
        environment_id="acceptance-linux-v1",
        caller_id="worker-1",
        allowed_destinations=[{"host": "source.example", "port": 443}],
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    await session.commit()
    budget = await reserve_execution_budget(session, admission.budget_id, amount=80)
    assert budget.reserved_bytes == 80
    await session.commit()
    with pytest.raises(DownloadExecutionAdmissionError, match="DOWNLOAD_BUDGET_EXCEEDED"):
        await reserve_execution_budget(session, admission.budget_id, amount=21)
    await revoke_execution_admission(session, admission.id)
    await session.commit()
    with pytest.raises(DownloadExecutionAdmissionError, match="DOWNLOAD_ADMISSION_REJECTED"):
        await consume_execution_admission(
            session,
            admission.id,
            task_id=ids["task"],
            owner_id=ids["owner"],
            request_digest="b" * 64,
            caller_id="worker-1",
        )
    session.close()


async def test_mismatched_caller_cannot_consume_admission(admission_db):
    ids = _ids()
    session = _AsyncSessionFacade(admission_db)
    admission = await issue_processed_http_admission(
        session,
        ingestion_id=ids["ingestion"],
        task_id=ids["task"],
        owner_id=ids["owner"],
        project_id=ids["project"],
        confirmation_id="confirmation-3",
        request_digest="c" * 64,
        limit_bytes=100,
        policy_revision="http-policy-v1",
        environment_id="acceptance-linux-v1",
        caller_id="worker-1",
        allowed_destinations=[{"host": "source.example", "port": 443}],
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    await session.commit()
    with pytest.raises(DownloadExecutionAdmissionError, match="DOWNLOAD_ADMISSION_REJECTED"):
        await consume_execution_admission(
            session,
            admission.id,
            task_id=ids["task"],
            owner_id=ids["owner"],
            request_digest="c" * 64,
            caller_id="worker-evil",
        )
    session.close()
