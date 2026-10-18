# ADR：寻宝鼠统一原生入口与能力预检

状态：P0 已实现，待 Gate 审查；未发布。范围仅访问边界，不决定 P1-A 的 React/Vue 展示方案。

## 决策与理由

`TreasureMouseView.vue` 只挂载平台 `TreasureResearchWorkbench.vue`。Vue 持有平台身份、项目与平台会话；不再默认 iframe，也不提供用户可切换的旧账号入口。Node 科研服务保留为内网适配器。两个 Nginx 配置对 `/treasure-mouse` 和 `/treasure-mouse/` 旧子应用路径返回 404；平台页面使用 Vue Router 的 hash 路由。未重载 Nginx。

已登录用户先读取 `/api/v1/research-agent/capabilities`，native flag 关闭时仍可获得安全的能力快照。模块未授权返回 disabled 快照，不访问受保护会话；实际业务请求在服务端重新校验 active、模块和 owner。注册表的 treasure-mouse `api_prefix` 维持原值，避免中间件提前 403 破坏 capability 契约；BFF 服务明确复用现有用户 `disabled_modules` 与管理员豁免语义。

capability 是配置与身份许可的前提，不是 Redis、模型、Node、Worker 的健康保证；`write_execution` 与 `write_tools_enabled` 均由 DTO 限制为 false。实际下游仍会 fail closed。

## 结果与边界

- 用户得到一个入口；native 关闭时可解释原因，不把请求失败展示为零历史。
- 模块撤权后手动刷新或窗口重新聚焦会清空当前内容并重新预检；每次 HTTP 业务访问继续独立校验。已开始的 SSE 不保证中途撤权终止。
- 全局 project=null 仅用于只读科研发现；不隐式创建默认项目。
- 停止按钮明确为“停止接收”。实例内 asyncio.Event 不构成跨请求或跨进程取消保证，P1-C 再处理。
- 旧 React 主视觉尚未恢复；此 ADR 不宣称临时 Vue 工作台满足 P1-A/B。

## 回退

原始脏文件已保存在 `evidence/treasure-native/baseline/`，附 HEAD 与内容 hash。按文件选择性恢复本次增量；禁止 git reset 覆盖其他 Phase5 工作。回退也不得重新暴露旧独立认证 API 或放开写门禁。
