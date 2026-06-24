"""AI 对话路由 - WebSocket 全双工通信"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.get("/conversations")
async def list_conversations():
    """获取对话列表"""
    return {"message": "list conversations"}


@router.websocket("/ws")
async def ai_websocket(websocket: WebSocket):
    """AI 对话 WebSocket 端点

    支持流式 AI 响应、Tool Use 调用、MCP 工具集成。
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # TODO: 实现完整的 AI 对话逻辑
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        pass
