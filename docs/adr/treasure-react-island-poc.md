# ADR：科研展示 React Island 隔离 PoC

> 后续变更：根据用户“先解决正式页面”的要求，欢迎区与 Composer 已接入正式工作台及主构建；本文以下保留最初 PoC 阶段记录。当前接线、只读开关与验证边界以 [重载修复报告](../implementation/treasure-native-entry-reload-fix.md) 为准，G-P1A 仍未通过。

状态：EXPERIMENTAL / 决策待定。没有把 PoC 接入正式平台路由，也没有通过 G-P1A。

## 实验决策

复用子仓根 `src/components/chat/{EmptyState,Composer}.tsx` 与鼠形象、本地字体、中英文词典。新增 `src/island/` 展示入口；不 import SPA routes、Supabase、localAuth、chatStore 或科研网络客户端。Vue PoC 宿主负责草稿、语言、主题、模型与回调，React 不另建项目或消息状态。

构建分成两个独立产物：子仓现有 React19/Vite7/Tailwind4 生成临时 ES module，主前端现有 Vue/Vite5 消费该 module。只用已有 node_modules；主前端没有新增 React 依赖、没有改锁文件。此方式是兼容性实验，尚非供应链与发布方案。

ShadowRoot 隔离 CSS。原 `:root` token 在 shadow 样式内映射至 theme wrapper，`.dark` 与 lang 仅作用于该 wrapper。字体规则作为 refcount 管理的单个 `@font-face` 样式进入 document.head，其他 CSS 留在 shadow。最后一个 Island 卸载时移除该字体样式。

受控 i18n provider 不读写 localStorage、不改 html/title；Composer 在 Island 中使用 no-op typing callback，不触发旧 petBus。共用组件保留默认行为，原 SPA 不传新增可选参数。

彩蛋 Portal 显式挂载 theme wrapper 内，Island 使用非 modal Radix Dialog，以避免旧 Dialog 对整个 document 的滚动、pointer-events 和 aria-hidden 操作。为保持原遮罩结构，在 shadow Portal 内显式绘制同样的遮罩；针对 shadow activeElement 做本地 Tab/Shift+Tab 边界循环，关闭时恢复头像焦点。8 项 DOM 回归包括这些行为；真实焦点循环、焦点恢复、遮罩视觉与窄屏行为仍未验证，不能据此声称原版弹窗已等价恢复。

## 当前证据

- 原 React 源码与独立 Island TS 编译通过；Vue 独立 PoC 类型与构建通过。
- 8 项 DOM 回归通过，含原四场景/八示例、回调、禁用/停止态、语言主题隔离、Portal 所属树、两次 Vue 进入/离开与 style/focus guard 清理。
- 模块图 1792 项，禁止的 SPA/auth/network 入口命中为零。模块图检查不是完整安全审计。
- 初版 library mode 内联完整字体，ES module 约 8.07 MB。已改为保留 ES 入口导出的普通构建、assetsInlineLimit=0 与相对资源路径；字体按原 unicode-range 分片外置，最终 module 约 564 KB，Vue PoC JS 约 660 KB。两侧资源重定位构建与 DOM 测试通过；实际字体加载仍待浏览器验证，生产依赖固定与共享 React 方案仍待评审。
- Chromium socket 被当前环境拒绝，本地 dev server listen 也返回 EPERM。无新截图，不存在视觉通过结论。

## Gate 与替代路径

G-P1A = BLOCKED / VISUAL REVIEW PENDING。环境拒绝不等于 React 技术方案失败；目前不提前选择 Vue 重写，也不继续耦合 P1-B。保留隔离 PoC，在可运行浏览器环境完成字体、布局、Portal、Focus、滚动与截图对照，再由用户确认；若确认存在不可接受的隔离问题，再按功能矩阵评审 Vue 严格等价实现。

回退只需移除新增实验文件，按 `evidence/treasure-native/p1a-baseline/` 恢复四个共用展示文件本次增量。子仓已有科研后端改动不得覆盖；父仓不能替子仓提交内部变更。本次未提交。
