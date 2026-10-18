# Research 消息展示契约 v1

Vue 持有 ResearchMessage；React 只接收投影后的 TreasureMessage 和回调。契约源码同步位于子仓 `src/island/contract.ts` 与主前端 `src/types/treasureIsland.d.ts`。

- `content`：delta 原样追加；原 ChatMessage 负责 Markdown、编号和继续寻宝建议。
- `metadata_json.events.cards`：完整原始 tool/accession/title/summary/meta；即时事件与终态快照合并，显示层才转换字符串和过滤来源 URL。
- `events.tools`：running/done/error 归并为一次调用；后续同名调用保留。终态非空 tools 是权威快照。
- `events.grounding`：confirmed 与 unconfirmed 原样存储，显示层验证形状；默认折叠符合原组件行为。
- `events.polariseq.accession`：原样存储；命令展示仅允许 PRJNA/PRJEB/PRJDB/PRJCA 数字编号。
- `status`：实时 streaming；收到 end 后 complete；error/cancel/无终态断开均保留已收到内容并提示未完成。后端历史保留终态 end/interrupted/error/cancel，展示层兼容两侧命名。

文献读取仅通过 `/api/v1/research-agent/sessions/{id}/literature`；先验证会话 owner、active 和模块，再调用内部代理。前端不携带旧站 token。排行榜与统计的原站服务不进入浏览器构建。
