# Follow-up 胶囊建议实施与验证

## 调查与边界

AI 助手入口 `AgentSandbox.vue`、工作台入口 `StudioView.vue` 均通过 `KimiMessageList.vue` → `KimiMessageItem.vue` → `SuggestionChips.vue` 展示建议。结构化 suggestions 优先，历史 Markdown 经 `parseNextStepSuggestions` 兜底。`send` 调原会话 handleSend，`prefill` 写输入框并聚焦；后者保留需要补充文件的业务语义。既有每消息最多 4 条策略不变。旧 Enter 是装饰文字，没有独立全局快捷键。

## 实际修改文件

- `frontend/src/components/ai-chat/SuggestionChips.vue`：横向 flex-wrap、Sparkles 标题、ArrowUpRight、38px 最小触摸高度、800px 上限、自然换行、原生按钮、focus-visible、主题令牌、禁用与同帧防重。
- `frontend/src/components/ai-chat/KimiMessageItem.vue`：正文左边界对齐、禁用状态透传。
- `frontend/src/components/ai-chat/KimiMessageList.vue`：会话禁用状态透传，沿用末条完成消息显示与流式隐藏规则。
- `frontend/src/views/StudioView.vue`：异步读取产物列表之前同步锁定建议，finally 释放，继续使用原发送方法。
- `frontend/src/utils/nextStepSuggestions.ts`：取消兜底标签的硬编码 12 字截断；完整 prompt 不变。
- `frontend/src/utils/nextStepSuggestions.spec.ts`：完整标题回归。
- `frontend/src/components/ai-chat/__tests__/suggestion-chips.test.ts`：0/1/2/4/6 条、特殊字符、完整 prompt、prefill、重复点击、disabled。
- `frontend/src/components/ai-chat/__tests__/kimi-message-item.test.ts`：结构化历史、Markdown 历史、流式前后、禁用与发送事件。
- `ARCHITECTURE_DESIGN/CygnusX_frontend.md`：同步共用组件现状及浏览器验收缺口。

## 验收限制

实际浏览器验收尚未通过，不能宣称 UI 已完整验收。

1. Vite 本地服务监听 `127.0.0.1:5199` 被运行环境拒绝：`listen EPERM: operation not permitted`。
2. 已离线构建真实 Vue 组件预览（`/tmp/followup-evidence/preview/.followup-preview.html`），尝试用已有 Playwright 驱动已安装 Chromium。
3. Chromium 启动被沙箱拒绝：`FATAL:content/browser/sandbox_host_linux.cc:41 Check failed: . shutdown: Operation not permitted (1)`，未产生可用截图。

因此，320/375/768/1280/1920px 的真实浏览器布局、深色实际观感、Tab/Enter/Space 原生激活及前后对比截图仍待可运行浏览器的环境验收。jsdom 无法证明这些要求。未发起真实 AI 请求。没有更改 Agent Runtime、协议或工作流。

测试原始日志保存在本目录；离线预览与旧组件快照保存在 `/tmp/followup-evidence`。仓库已有其它工作区变更不属于本次任务。

## 最终命令与结果

- `cd frontend && npm test`：90 个测试文件、611 条测试全部通过。
- `cd frontend && npm run type-check`：退出码 0。
- `cd frontend && npm run build`：退出码 0（包含 `vue-tsc -b` 和生产 Vite 构建）。
- `git diff --check`：通过。

本次没有提交 commit，因此未执行仓库要求的提交前全后端门禁；没有把前端局部验证称为全仓 CI 通过。目标保持未完成状态，等待真实浏览器与截图验收。

## 续轮复核

再次执行已有 Playwright 离线页面检查，Chromium 仍在启动阶段因 `shutdown: Operation not permitted (1)` 退出（退出码 1），详见 `browser-recheck.log`。当前工具列表没有其它浏览器/远程浏览器入口。未生成截图，浏览器验收继续未完成；没有绕过运行环境权限限制。已复核共用组件、Studio 发送门禁及前轮测试日志，`git diff --check` 仍通过。
