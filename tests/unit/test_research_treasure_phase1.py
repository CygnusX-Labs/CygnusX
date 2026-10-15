"""Phase 1 discovery contract and side-effect boundary tests."""

from __future__ import annotations

import pytest

from cygnusx.application.services.research_treasure_service import card_to_proposal


@pytest.mark.unit
def test_dataset_card_maps_to_unverified_discovery_proposal_without_asset_fields() -> None:
    proposal = card_to_proposal(
        {
            "tool": "seqout_search_geo",
            "accession": "GSE123456",
            "title": "Example study",
            "summary": "Public metadata",
            "meta": {"organism": "Mus musculus", "sample_count": "8"},
        },
        session_id="session-1",
        project_id="project-1",
    )

    assert proposal.metadata_status == "unverified"
    assert proposal.project_id == "project-1"
    assert proposal.source_links == ["https://www.ncbi.nlm.nih.gov/bioproject/?term=GSE123456"]
    assert not hasattr(proposal, "dataset_id")
    assert not hasattr(proposal, "task_id")


@pytest.mark.unit
def test_untrusted_accession_does_not_create_external_link() -> None:
    proposal = card_to_proposal(
        {"tool": "external", "accession": "javascript:alert(1)", "title": "x"},
        session_id="session-1",
        project_id=None,
    )
    assert proposal.source_links == []
    assert proposal.metadata_status == "unverified"


@pytest.mark.unit
def test_native_write_capability_is_backend_constant_false() -> None:
    from cygnusx.application.schemas.research_agent import ResearchAgentCapabilities

    capabilities = ResearchAgentCapabilities(native_ui_enabled=True)
    assert capabilities.write_tools_enabled is False

