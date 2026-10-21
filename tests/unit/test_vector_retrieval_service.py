"""Hybrid knowledge retrieval query and ranking contracts."""

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from cygnusx.application.services.vector_retrieval_service import (
    KnowledgeCitation,
    VectorRetrievalService,
)
from cygnusx.infrastructure.database.models.knowledge_chunk import KbChunkModel
from cygnusx.infrastructure.database.models.knowledge_document import KbDocumentModel


def test_project_visibility_allows_global_and_matching_project_only() -> None:
    service = VectorRetrievalService(db=None)  # type: ignore[arg-type]
    statement = select(KbDocumentModel.doc_id).where(*service._visibility_filters("project-a"))
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "kb_documents.project_id IS NULL OR kb_documents.project_id =" in compiled
    assert "knowledge_bases.ai_searchable IS true" in compiled
    assert "knowledge_bases.is_enabled IS true" in compiled


def test_vector_recall_uses_cosine_distance_operator() -> None:
    service = VectorRetrievalService(db=None)  # type: ignore[arg-type]
    distance = KbChunkModel.embedding.cosine_distance([0.1] * 1024)
    statement = (
        select(KbDocumentModel.doc_id)
        .join(KbChunkModel, KbChunkModel.document_id == KbDocumentModel.doc_id)
        .where(*service._visibility_filters(None), KbChunkModel.embedding.is_not(None))
        .order_by(distance)
    )
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "<=>" in compiled
    assert "kb_chunks.embedding IS NOT NULL" in compiled


def test_keyword_rerank_returns_traceable_citations() -> None:
    service = VectorRetrievalService(db=None)  # type: ignore[arg-type]
    candidates = [
        KnowledgeCitation(
            doc_id="generic",
            title="Guide",
            category="general",
            excerpt="unrelated notes",
            section_path="",
            url="/knowledge/generic",
            score=0.92,
        ),
        KnowledgeCitation(
            doc_id="project-guide",
            title="RNA-seq guide",
            category="analysis",
            excerpt="RNA-seq alignment and quality control",
            section_path="Alignment",
            url="/knowledge/project-guide",
            score=0.86,
        ),
    ]

    ranked = service._keyword_rerank(candidates, "RNA-seq alignment", limit=1)

    assert ranked[0].doc_id == "project-guide"
    assert ranked[0].url == "/knowledge/project-guide"


def test_keyword_rerank_prefers_title_match_over_generic_page() -> None:
    service = VectorRetrievalService(db=None)  # type: ignore[arg-type]
    candidates = [
        KnowledgeCitation(
            doc_id="generic-feature-page",
            title="Wiki · 功能特性",
            category="平台 Wiki",
            excerpt="本章节介绍平台的功能与页面入口。",
            section_path="功能特性",
            url="/knowledge/generic-feature-page",
            score=1.0,
        ),
        KnowledgeCitation(
            doc_id="platform-treasure-mouse",
            title="寻宝鼠（科研数据发现）页面指南",
            category="平台使用指南",
            excerpt="本页面介绍寻宝鼠的主要功能、使用流程和执行边界。",
            section_path="快速结论",
            url="/knowledge/platform-treasure-mouse",
            score=1.0,
        ),
    ]

    ranked = service._keyword_rerank(candidates, "寻宝鼠 页面 功能", limit=1)

    assert ranked[0].doc_id == "platform-treasure-mouse"
