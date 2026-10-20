"""Focused tests for v2 memory helpers without database dependencies."""

import asyncio
from pathlib import Path

import pytest

from cygnusx.application.services import studio_context_service, studio_tools
from cygnusx.infrastructure.celery_app.tasks.memory import _extract_json_array


def test_fact_extraction_parser_accepts_only_json_arrays() -> None:
    response = {"choices": [{"message": {"content": '[{"content":"用户偏好 DESeq2","scope":"preference"}]'}}]}

    assert _extract_json_array(response) == [{"content": "用户偏好 DESeq2", "scope": "preference"}]
    assert _extract_json_array({"choices": [{"message": {"content": "[]"}}]}) == []
    for content in ("not json", "{}", "[null]", '[{"content":"missing scope"}]'):
        with pytest.raises(ValueError):
            _extract_json_array({"choices": [{"message": {"content": content}}]})


def test_workspace_remember_writes_note_and_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        studio_tools.studio_sandbox_manager,
        "workspace_dir",
        lambda _session_id: tmp_path,
    )
    monkeypatch.setattr(
        studio_context_service.studio_sandbox_manager,
        "workspace_dir",
        lambda _session_id: tmp_path,
    )

    result = asyncio.run(
        studio_tools._workspace_remember(
            {"title": "RNA normalization", "summary": "Use DESeq2", "content": "Keep the VST workflow."},
            "session",
        )
    )

    assert result["success"] is True
    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "RNA normalization" in index
    note = next((tmp_path / ".memory").glob("*.md"))
    assert "Keep the VST workflow." in note.read_text(encoding="utf-8")
    assert studio_context_service.load_workspace_memory_index("session") == index


def test_workspace_remember_preserves_markup_and_avoids_same_day_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        studio_tools.studio_sandbox_manager,
        "workspace_dir",
        lambda _session_id: tmp_path,
    )

    first = asyncio.run(
        studio_tools._workspace_remember(
            {"title": "HTML", "summary": "Keep markup", "content": "<script>if (a < b) return;"},
            "session",
        )
    )
    second = asyncio.run(
        studio_tools._workspace_remember(
            {"title": "HTML", "summary": "Keep the second note", "content": "<b>second</b>"},
            "session",
        )
    )

    assert first["success"] is True
    assert second["success"] is True
    notes = sorted((tmp_path / ".memory").glob("*.md"))
    assert len(notes) == 2
    note_contents = [note.read_text(encoding="utf-8") for note in notes]
    assert any("<script>if (a < b) return;" in content for content in note_contents)
    assert any("<b>second</b>" in content for content in note_contents)
    assert len([line for line in (tmp_path / "MEMORY.md").read_text(encoding="utf-8").splitlines() if line.startswith("- [")]) == 2


@pytest.mark.unit
@pytest.mark.parametrize("episode,focus", [("完成质控；待确认批次效应", "完成 RNA 分析"), (None, None)])
def test_settlement_parser_validates_combined_outputs(episode, focus) -> None:
    import json

    from cygnusx.infrastructure.celery_app.tasks.memory import _extract_settlement

    payload = {"facts": [], "episode": episode, "current_focus": focus}
    assert _extract_settlement({"choices": [{"message": {"content": json.dumps(payload)}}]}) == (
        [], episode, focus
    )


@pytest.mark.unit
@pytest.mark.parametrize("payload", [
    '{"facts":[]}',
    '{"facts":[],"episode":42,"current_focus":null}',
    '{"facts":[],"episode":"API_KEY=sk-secret-value","current_focus":null}',
])
def test_settlement_parser_rejects_invalid_or_sensitive_outputs(payload) -> None:
    from cygnusx.infrastructure.celery_app.tasks.memory import _extract_settlement

    with pytest.raises(ValueError):
        _extract_settlement({"choices": [{"message": {"content": payload}}]})


@pytest.mark.unit
@pytest.mark.parametrize("importance", [0, 11, True, 1.5, "7"])
def test_extracted_importance_must_be_bounded_integer(importance) -> None:
    import json

    payload = [{"content": "用户常用 GRCh38", "scope": "preference", "importance": importance}]
    with pytest.raises(ValueError, match="importance"):
        _extract_json_array({"choices": [{"message": {"content": json.dumps(payload)}}]})
