"""AI 对话饼干计费单元测试 — spend_ai_tokens 扣减 / 封顶 + 对话准入闸门。"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from omichub.application.services.cookie_service import CookieService
from omichub.domain.cookie.entities import CookieAccount


def _service_with_account(balance: str) -> tuple[CookieService, CookieAccount]:
    svc = CookieService(session=MagicMock())
    account = CookieAccount(id=1, user_id=uuid4(), balance=Decimal(balance))
    svc.get_or_create_account = AsyncMock(return_value=account)
    svc._record_transaction = AsyncMock()
    return svc, account


@pytest.mark.asyncio
async def test_spend_ai_tokens_deducts_by_rate():
    svc, account = _service_with_account("100.00")

    cost = await svc.spend_ai_tokens(account.user_id, tokens=1500, source_id="msg-1")

    assert cost == Decimal("15.00")  # 1500 / 1000 * 10 🥫
    svc._record_transaction.assert_awaited_once()
    kwargs = svc._record_transaction.call_args
    assert kwargs.args[2] == Decimal("-15.00")
    assert kwargs.kwargs["source_type"] == "ai_chat"


@pytest.mark.asyncio
async def test_spend_ai_tokens_caps_at_available_balance():
    svc, account = _service_with_account("5.00")

    cost = await svc.spend_ai_tokens(account.user_id, tokens=1500, source_id="msg-1")

    assert cost == Decimal("5.00")
    assert svc._record_transaction.call_args.args[2] == Decimal("-5.00")


@pytest.mark.asyncio
async def test_spend_ai_tokens_skips_when_broke_or_invalid():
    svc, account = _service_with_account("0.00")
    assert await svc.spend_ai_tokens(account.user_id, tokens=1500, source_id="m") == Decimal("0")
    assert await svc.spend_ai_tokens(account.user_id, tokens=0, source_id="m") == Decimal("0")
    svc._record_transaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_gate_blocks_when_balance_empty():
    from omichub.application.services.chat_service import ChatService

    svc = ChatService(db=MagicMock())
    with patch(
        "omichub.application.services.cookie_service.CookieService.check_balance",
        AsyncMock(return_value=Decimal("0")),
    ):
        message = await svc._ensure_cookie_balance(str(uuid4()))

    assert message is not None
    assert "饼干余额不足" in message


@pytest.mark.asyncio
async def test_chat_gate_passes_with_balance():
    from omichub.application.services.chat_service import ChatService

    svc = ChatService(db=MagicMock())
    with patch(
        "omichub.application.services.cookie_service.CookieService.check_balance",
        AsyncMock(return_value=Decimal("3.5")),
    ):
        assert await svc._ensure_cookie_balance(str(uuid4())) is None
