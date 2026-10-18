"""流程目录工具"""

from fastmcp import FastMCP

from client.api_client import CygnusXAPIClient, CygnusXAPIError


def register(mcp: FastMCP, api: CygnusXAPIClient) -> None:

    @mcp.tool()
    async def cygnusx_list_flows(category: str = "", limit: int = 20, offset: int = 0) -> dict:
        """列出平台当前已开放、可提交的分析流程目录（仅含简要字段，分页返回）。

        输出与门控后的"可提交流程集合"同源同判定：默认关闭的流程
        （如 counts_deg，受 counts_deg_flow_enabled 配置门控）不会出现。
        只读工具，无副作用。目录不随流程数膨胀：默认每页 20 条、最多 50 条，
        完整契约按需走 cygnusx_get_flow_detail。

        :param category: 流程类别过滤（可选）："rna_seq"/"atac_seq"/"scrna"等，留空返回全部
        :param limit: 每页条数（默认 20，最大 50）
        :param offset: 分页偏移（默认 0）
        :return: JSON 格式结果，含 success、summary、data（items/total/next_offset）、next_steps

        示例:
            await cygnusx_list_flows("scrna")
            # 返回已开放的单细胞 RNA 分析流程第一页
        """
        limit = max(1, min(limit, 50))
        offset = max(0, offset)
        try:
            data = await api.list_flows(category=category or None, limit=limit, offset=offset)
            flows = data.get("flows", data) if isinstance(data, dict) else data
            items = data.get("items", flows) if isinstance(data, dict) else flows
            total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
            lines = []
            for f in (items if isinstance(items, list) else []):
                lines.append(
                    f"- {f.get('id', f.get('flow_id', '?'))}: {f.get('name', '?')} "
                    f"(v{f.get('version', '?')}, {f.get('parameter_count', 0)} 参数)"
                )
            next_offset = offset + limit
            has_more = next_offset < total
            return {
                "success": True,
                "summary": (
                    f"可用流程（{offset + 1}-{min(next_offset, total)}/{total}）:\n"
                    + "\n".join(lines)
                ),
                "data": {
                    "items": items,
                    "total": total,
                    "next_offset": next_offset if has_more else None,
                    "has_more": has_more,
                },
                "next_steps": (
                    ["使用 cygnusx_get_flow_detail 查看具体流程的参数配置"]
                    + ([f"调用 cygnusx_list_flows(offset={next_offset}) 获取下一页"]
                       if has_more else [])
                ),
            }
        except CygnusXAPIError as e:
            return {"success": False, "summary": f"获取流程列表失败: {e.detail}"}

    @mcp.tool()
    async def cygnusx_get_flow_detail(flow_id: str) -> dict:
        """获取分析流程的完整输入契约：描述、参数列表、样本表定义、执行配置。

        这是固定工具目录中的 describe 工具：配合 cygnusx_list_flows（目录）
        使用，按需拉取单个流程的完整契约。对未开放流程（门控关闭）返回"不存在"。

        :param flow_id: 流程 ID（如："scrna_v2"）
        :return: JSON 格式流程详情，含 meta、parameters、sample_sheet

        示例:
            await cygnusx_get_flow_detail("scrna_v2")
            # 返回完整流程信息
        """
        try:
            data = await api.get_flow(flow_id)
            meta = data.get("meta", {})
            params = data.get("parameters", [])
            param_names = [p.get("name", p.get("key", "?")) for p in params[:30]]
            summary = (
                f"流程: {meta.get('name', flow_id)} (v{meta.get('version', '?')})\n"
                f"描述: {meta.get('description', '无')}\n"
                f"类别: {meta.get('category', '?')}\n"
                f"参数数量: {len(params)}\n"
                f"主要参数: {', '.join(param_names[:15])}\n"
            )
            if data.get("sample_sheet"):
                cols = [c.get("name", "?") for c in data["sample_sheet"].get("columns", [])]
                summary += f"样本表列: {', '.join(cols)}\n"
            return {
                "success": True,
                "summary": summary,
                "data": data,
                "next_steps": ["使用 cygnusx_submit_analysis 提交分析任务"],
            }
        except CygnusXAPIError as e:
            return {"success": False, "summary": f"获取流程详情失败: {e.detail}"}

    @mcp.tool()
    async def cygnusx_get_flow_parameters(flow_id: str) -> dict:
        """获取流程的参数 JSON Schema，用于了解每个参数的类型、默认值和约束。

        :param flow_id: 流程 ID（如："scrna_v2"）
        :return: JSON 格式参数 schema，含 properties 和 required 列表

        示例:
            await cygnusx_get_flow_parameters("scrna_v2")
            # 返回参数定义列表
        """
        try:
            data = await api.get_flow_schema(flow_id)
            props = data.get("properties", {})
            lines = []
            for name, spec in list(props.items())[:30]:
                ptype = spec.get("type", "any")
                default = spec.get("default", "")
                desc = spec.get("description", "")
                lines.append(f"- {name} ({ptype}): {desc} [默认: {default}]")
            return {
                "success": True,
                "summary": f"参数 schema ({len(props)} 个):\n" + "\n".join(lines),
                "data": data,
            }
        except CygnusXAPIError as e:
            return {"success": False, "summary": f"获取参数 schema 失败: {e.detail}"}
