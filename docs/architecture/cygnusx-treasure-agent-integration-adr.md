# ADR: CygnusX 原生科研寻宝鼠集成

日期：2026-10-15
状态：Phase 1 implemented / release blocked

## 决策

采用 **Vue Native Chat View + Node Discovery API**。主平台继续使用 Vue 3/Naive UI；寻宝鼠的 Node/TypeScript Agent Runtime 和真实 GEO/SRA/ENA/文献检索工具保持不变，通过 FastAPI BFF 受信调用。

浏览器链路为：平台 JWT -> `CurrentUserId` -> FastAPI `research-agent` 路由 -> 已校验的 owner/project/session -> Node `/cygnusx/discovery`。Node 只接受内部共享令牌，平台身份相关请求头仅作观测上下文，不作为授权依据。浏览器不接触 Node 凭证，也不再访问旧 `/auth`、`/history` 或旧 chat 路径。

## 为什么不是 React Island

现有 React 应用包含独立 Supabase/本地账号、TanStack Router、会话侧栏、模型目录和全套页面，不是可直接挂载的聊天组件；主 frontend 没有 React 依赖。抽取 Island 会同时引入打包、CSS 隔离、卸载和双认证迁移风险，且不能替代后端身份统一。Vue 原生页面只复刻交互表面，Agent Runtime 不重写。

## 会话与数据边界

新会话复用平台 `ChatSessionModel`/`ChatMessageModel`，以 `sandbox_meta.research_agent` 标记，所有读取按平台用户与项目再次核验。未选择项目时显式保留 `project_id=null`，不会套用普通 Chat 的默认项目规则。旧寻宝鼠账号和历史卷保留但不自动映射、合并或删除。

## 回滚

回滚代码时保留平台 API 和旧数据；不得直接重新暴露旧 Nginx location。只有在隔离环境恢复旧 UI 时，才能同步恢复受平台认证保护的受控代理，并继续禁止独立账号绕权。`treasure_native_ui_enabled` 默认 false，写能力后端恒为 false。
