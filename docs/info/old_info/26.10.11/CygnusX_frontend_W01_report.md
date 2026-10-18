# CygnusX Frontend v2.0 - W01 变更报告

- 状态：部分完成。已修复已下线路由的可点入口，自动检查通过；项目详情真实浏览器验收待环境可用后补齐。
- 当前分支 / Git 基线和原有未提交改动：见 W00 报告；未触碰五个子模块及已有两份未跟踪规范。
- 采用的现行规范：`CygnusX_frontend.md` §5.6、§27；实施规范 §5.10、§19 W01。路由守卫与后端权限保持原样。
- 已核实问题：`frontend/src/router/index.ts` 中 `agent-teams-room` 路由目前被注释；`frontend/src/views/ProjectDetailView.vue` 的协作会话“打开”动作仍调用该命名路由，可能在点击后导航失败。
- 实际修改：`frontend/src/views/ProjectDetailView.vue` 在渲染操作时用 `router.hasRoute('agent-teams-room')` 判断入口是否存在。路由下线时禁用按钮、显示“暂不可用”和原因；恢复路由后仍按 `room_id`、`case_id` 的原有优先级跳转。会话记录和字段不变。
- 兼容与业务保护：没有新增路由、放开权限、删除协作会话或改动项目/会话 ID。不存在路由时 `openSession` 也有保护，避免其他调用路径误跳转。
- `type-check`：通过。相关 Vitest：`collaboration-route-notice.test.ts` 1/1 通过。全量 Vitest 基线仍有 W00 所列 7 项既有失败；W01 未改这些测试域。`build`：W01 修改后通过。`git diff --check`：通过。
- 视觉证据：未取得；原因见 W00。Light/Dark 和 1440/390 项目详情交互验收待补。
- 业务回归：S1–S10 中项目详情的失效路由已静态核查；真实点击、权限角色和历史深链未实测。
- 风险：路由未来恢复时必须回归 room/case query 跳转；当前禁用按钮的浏览器 tooltip 和键盘行为尚未实测。
- 可逆性：仅回滚 `ProjectDetailView.vue` 中本批次的 `openSession` 与 `renderOpenButton` 差异，不清理用户其他改动。
- 下一推荐包：W02，同时补齐 W00/W01 浏览器证据。
