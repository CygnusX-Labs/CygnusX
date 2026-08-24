from pathlib import Path
from types import SimpleNamespace

import pytest

from cygnusx.application.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_read_attachment_text_extracts_local_pdf(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF fake")
    monkeypatch.setattr(
        ChatService,
        "_resolve_attachment_path",
        staticmethod(lambda _url: str(pdf_path)),
    )
    async def fake_extract_pdf_text(source: str) -> str:
        return f"parsed:{Path(source).name}"

    monkeypatch.setattr(
        ChatService,
        "_extract_pdf_text",
        staticmethod(fake_extract_pdf_text),
    )

    text = await ChatService._read_attachment_text(
        {
            "name": "paper.pdf",
            "mime_type": "application/pdf",
            "url": "/api/v1/files/chat-upload/user/paper.pdf",
        }
    )

    assert text == "parsed:paper.pdf"


@pytest.mark.asyncio
async def test_extract_pdf_text_delegates_to_pdf_processor(monkeypatch, tmp_path: Path) -> None:
    """验证 _extract_pdf_text 已迁移至 PDFProcessor。"""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF fake")

    async def fake_process(self, file_path: str):
        return SimpleNamespace(
            content=f"processed:{Path(file_path).name}",
            metadata=SimpleNamespace(total_pages=2),
        )

    monkeypatch.setattr(
        "cygnusx.application.services.pdf_processor.PDFProcessor.process",
        fake_process,
    )

    text = await ChatService._extract_pdf_text(str(pdf_path))

    assert text == "processed:paper.pdf"
