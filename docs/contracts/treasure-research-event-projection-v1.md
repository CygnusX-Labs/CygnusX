# Treasure 事件与历史投影 v1

沿用现有 delta/tool/cards/grounding/polariseq/platform_tool/end/error/[DONE]，不引入平行 SSE 协议。消息契约补充见 treasure-research-message-v1.md。

唯一展示映射器为前端 researchPresentation.ts::researchMessageView，实时 ResearchMessage 与 BFF 持久 DTO 共用它。BFF 只保留/归并原始 metadata；旧 card_to_proposal 不承担科研卡投影，不从泛化 Proposal 重建卡片。cards 以来源/编号去重并合并 metadata，未知字段保留；工具 running/end 合为一次调用但保留后续同名调用。UTF-8、CRLF、多行 data、尾帧和缺失终态均有隔离测试；[DONE] 本身不证明成功。

平台操作通过 Gateway 的 invocation/ingestion/analysis-link/task/report ID 恢复，不将检索 ToolTrace 当作业务任务。人工 prepare 后直接展示服务结果；会话恢复或 platform_tool 流结束后经 related 读取持久关联。报告另经 research.project_delivery 只读查询，不凭 LLM 文本或 Task succeeded 推断双报告存在。

会话/project/action generation 变化、Dialog 关闭和权限刷新均拒绝迟到响应。Vue 给 React 传 workflow 的显式快照，避免 Vue reactive 对象在 React 中变化却未触发更新。切换项目清空当前视图和审批绑定；旧请求不会覆盖新项目列表或会话内容。
