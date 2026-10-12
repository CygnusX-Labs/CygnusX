# CygnusX Frontend v2.0 - W12 变更报告

- 状态：部分完成。Studio 待处理条的键盘定位和窄屏排版已改；三栏拖拽、审批全路径、Plan 与产物的浏览器验收待补。
- 基线与保护：沿用 W00 基线，保留起点五个脏子模块、原规范及 W01–W11 改动。
- 采用规范：实施规范 §5.12、§19 W12；活动 `CygnusX_frontend.md` Studio/审批约束。
- 实际修改：PendingApprovalBar 的工具摘要及澄清问题改为可聚焦按钮，点击或键盘激活均定位到原消息；窄屏操作区允许换行，待办列表高度受视口限制，保持输入区可见。审批 store API、一次性计划决议、`always_allow` 和问答数据源未改。
- 自动验证：`PendingApprovalBar.test.ts` 与 `studio-routing.test.ts` 合计 5/5 通过；`npm run type-check`、`npm run build` 通过。真实多审批、澄清、撤销与批准后的状态仍须联调。
- 视觉证据：未取得；浏览器限制见 W00。需在 390/768/1024px 检查待办条高度、焦点、三栏与输入区不遮挡。
- 风险与可逆性：摘要 DOM 元素由 span 变为 button，CSS 清除了原生按钮边框/底色；如有样式差异，可撤销本批 PendingApprovalBar 模板及 CSS。
- 下一推荐包：W13；浏览器恢复后补 Studio 全路径 E2E。
