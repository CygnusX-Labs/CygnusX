"""Disposable, offline probes of the current project management implementation."""
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from tests.unit.test_dataset_phase3 import registry as registry
from tests.unit.test_project_lifecycle import lifecycle as lifecycle
from cygnusx.application.services.chat.session_management import ChatSessionManagement
from cygnusx.application.services.agentteams_service import AgentTeamsService
from cygnusx.application.services import agentteams_service as case_module
from cygnusx.infrastructure.database.models.dataset import DatasetModel
from cygnusx.infrastructure.database.models.project import ProjectModel, ProjectTombstoneModel

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_default_project_creation_reuses_a_tombstoned_slug(lifecycle):
    service, db, owner, _, _, factory = lifecycle
    original = await service.create_project(owner, ChatSessionManagement.DEFAULT_PROJECT_NAME)
    await service.delete_project(owner, UUID(original['id']))
    manager = ChatSessionManagement()
    manager._db = db
    replacement_id = await manager._resolve_default_project_id(str(owner))
    await db.commit()
    replacement = db.sync.get(ProjectModel, UUID(replacement_id))
    assert replacement_id != original['id']
    assert replacement.slug == original['slug']
    assert db.sync.get(ProjectTombstoneModel, UUID(original['id'])) is not None


async def test_case_run_after_project_rename_uses_new_name_instead_of_stable_slug(
    lifecycle, monkeypatch
):
    service, db, owner, _, project_id, factory = lifecycle
    renamed = await service.update_project(owner, project_id, {'name': 'renamed-project'})
    monkeypatch.setattr(case_module, 'get_path_factory', lambda: factory)
    case_service = AgentTeamsService.__new__(AgentTeamsService)
    _, reference = await case_service._prepare_case_run(
        requester_ref=str(owner), project_id=str(project_id), project_name=None,
        context_refs=[], db=db,
    )
    assert renamed['slug'] == 'owned'
    assert reference['id'] == str(project_id)
    assert reference['location'].startswith('projects/renamed-project/runs/')
    assert not reference['location'].startswith('projects/owned/runs/')


async def test_dataset_retention_surfaces_an_integrity_error_on_project_delete(lifecycle):
    service, db, owner, _, project_id, _ = lifecycle
    db.sync.execute(sa.text('PRAGMA foreign_keys=ON'))
    db.add(DatasetModel(
        user_id=owner, project_id=project_id, name='retained-dataset', assay_type='bulk_rnaseq'
    ))
    await db.commit()
    with pytest.raises(IntegrityError):
        await service.delete_project(owner, project_id)
    await db.rollback()
    assert db.sync.get(ProjectModel, project_id) is not None
    assert db.sync.get(ProjectTombstoneModel, project_id) is None
