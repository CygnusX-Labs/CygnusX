"""Studio Runtime 适配器。"""

from omichub.application.services.chat.runtimes.delegating_runtime import DelegatingAgentRuntime


class StudioChatRuntime(DelegatingAgentRuntime):
    """Studio 请求的显式 Runtime 身份，保留既有执行语义。"""
