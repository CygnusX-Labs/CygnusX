"""Owner history response projection, without changing canonical execution/approval data."""

from datetime import UTC, datetime

import pytest

from cygnusx.application.schemas.chat import ChatMessageDTO

pytestmark = pytest.mark.unit


def test_download_history_projection_removes_credentials_and_paths_without_mutation():
    metadata = {
        "tool_invocations": [
            {
                "tool_name": "platform_submit_download",
                "arguments": {"links": ["https://example.org/private?token=HISTORY_CANARY"]},
                "result": {"work_dir": "/data/users/private", "error": "password=HISTORY_CANARY"},
            }
        ]
    }
    message = ChatMessageDTO(
        message_id="fixture",
        role="assistant",
        content="",
        status="completed",
        created_at=datetime.now(UTC),
        metadata_json=metadata,
    )
    serialized = message.model_dump_json()
    assert "HISTORY_CANARY" not in serialized
    assert "/data/users/private" not in serialized
    assert "HISTORY_CANARY" in str(metadata)


def test_unrelated_tool_metadata_keeps_existing_contract():
    metadata = {
        "tool_invocations": [{"tool_name": "read_file", "arguments": {"path": "/workspace/a"}}]
    }
    message = ChatMessageDTO(
        message_id="fixture",
        role="assistant",
        content="",
        status="completed",
        created_at=datetime.now(UTC),
        metadata_json=metadata,
    )
    assert message.metadata_json == metadata


def test_sse_download_metadata_is_filtered_without_mutating_execution_chunk():
    from cygnusx.application.services.chat.chat_event_service import ChatEventService
    from cygnusx.infrastructure.ai_provider.openai_compatible import ChatChunk

    chunk = ChatChunk(
        type="tool_call",
        metadata={
            "tool_name": "platform_submit_download",
            "arguments": {"links": ["https://example.org/f?token=HISTORY_CANARY"]},
        },
    )
    sent = ChatEventService(enforcement="off").before_send(chunk)
    assert "HISTORY_CANARY" not in str(sent.metadata)
    assert "HISTORY_CANARY" in str(chunk.metadata)


def test_new_persisted_envelope_hash_covers_safe_projection_only():
    from cygnusx.application.services.chat.utils import (
        _finalize_invocation_envelope,
        _invocation_payload_hash,
    )

    original = {
        "tool_name": "platform_submit_download",
        "arguments": {"links": ["https://example.org/f?token=HISTORY_CANARY"]},
        "result": {"work_dir": "/data/private"},
    }
    safe = _finalize_invocation_envelope(original)
    assert "HISTORY_CANARY" not in str(safe)
    assert "/data/private" not in str(safe)
    assert safe["payload_hash"] == _invocation_payload_hash(safe)
    assert "payload_hash" not in original
    assert "HISTORY_CANARY" in str(original)


def test_download_output_without_name_is_filtered_by_stream_local_call_id():
    from cygnusx.application.services.chat.chat_event_service import ChatEventService
    from cygnusx.infrastructure.ai_provider.openai_compatible import ChatChunk

    stream = ChatEventService(enforcement="off")
    stream.before_send(
        ChatChunk(
            type="tool_call",
            metadata={"tool_name": "platform_submit_download", "tool_call_id": "call-one"},
        )
    )
    output = ChatChunk(
        type="tool_output",
        content="password=HISTORY_CANARY",
        metadata={"tool_call_id": "call-one", "data": "https://example.org/f?token=HISTORY_CANARY"},
    )
    assert "HISTORY_CANARY" not in str(stream.before_send(output))
    assert "HISTORY_CANARY" in str(output)
    # A different conversation using the same opaque ID does not inherit tool identity.
    assert ChatEventService(enforcement="off").before_send(output) == output
