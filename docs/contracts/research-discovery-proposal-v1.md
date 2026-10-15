# Research Discovery Proposal v1

`DiscoveryProposal` 是只读科研发现线索，不是 `Dataset`、`FileRecord`、`Artifact` 或 `Task`。

## 事件

平台 BFF 保留 Node 原始 SSE 事件：`delta`、`tool`、`cards`、`polariseq`、`grounding`、`end`、`error`、`cancel`。未知或非法 JSON 行被忽略，不作为 HTML 渲染；流结束前不会伪造 completed。

## 结构

```json
{
  "schema_version": "1.0",
  "proposal_id": "session-id:accession",
  "source": "seqout_search_geo",
  "accession": "GSE123456",
  "title": "...",
  "summary": "...",
  "organism": null,
  "assay_type": null,
  "sample_count": null,
  "metadata_status": "unverified",
  "source_links": ["https://www.ncbi.nlm.nih.gov/bioproject/?term=GSE123456"],
  "evidence_refs": ["GSE123456"],
  "retrieved_at": "2026-10-15T00:00:00Z",
  "project_id": null,
  "conversation_id": "session-id",
  "provenance": {
    "agent": "research-treasure-mouse",
    "tool_name": "seqout_search_geo",
    "verification_level": "source_not_verified"
  },
  "next_actions": ["inspect_metadata", "refine_search"]
}
```

Accession 只在已知编号格式下生成安全来源链接。样本数、实验类型和物种来自旧卡片时仍为未验证；Phase 1 不创建下载/分析任务，不登记项目数据集。
