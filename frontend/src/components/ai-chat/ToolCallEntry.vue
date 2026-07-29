<script setup lang="ts">
/**
 * ToolCallEntry — 单个工具调用卡片的统一分发渲染。
 * 从 KimiMessageItem 抽离，供"底部工具列表"与"正文/工具交错时间线"两种布局复用：
 *  - Studio HITL 审批卡片（有 approval 数据时出现）
 *  - Studio 代码工具（仅工作台页面）：代码卡片，支持编辑/重跑/产物
 *  - MAS 计划预览 / 交接卡片 / 产物登记卡片
 *  - 其余 MCP 工具走 McpToolCallCard
 */
import { inject } from 'vue'
import ApprovalCard from './ApprovalCard.vue'
import MasPlanPreviewCard from './MasPlanPreviewCard.vue'
import HandoffCard from './HandoffCard.vue'
import McpToolCallCard from './McpToolCallCard.vue'
import StudioCodeCard from '@/components/studio/StudioCodeCard.vue'
import { StudioContextKey, isStudioCodeTool } from '@/components/studio/context'
import { useAgentHubStore } from '@/stores/agentHub'
import type { MasPlan } from '@/api/mas'
import type { PipelineType } from '@/types/pipeline'
import type { ToolCall } from './types'

const props = defineProps<{ tool: ToolCall }>()

const emit = defineEmits<{
  confirmTool: [toolName: string, args: Record<string, unknown>]
  openToolPage: [route: string, args: Record<string, unknown>]
}>()

// Studio 工作台上下文：仅在 /studio 页面被 provide；普通 /ai 聊天无此上下文
const studioCtx = inject(StudioContextKey, null)
const agentHubStore = useAgentHubStore()

function isStudioCodeToolCall(tool: ToolCall): boolean {
  return !!studioCtx && isStudioCodeTool(tool.name)
}

function isArtifactRegisterTool(tool: ToolCall): boolean {
  return tool.name === 'artifact_register' && tool.status === 'success' && !!tool.uiPayload?.report_id
}

function isHandoffTool(tool: ToolCall): boolean {
  return tool.name === 'transfer_to_agent' && tool.status === 'success'
}

function hasMasPlan(tool: ToolCall): boolean {
  const plan = tool.uiPayload?.mas_plan
  return !!plan && typeof plan === 'object' && Array.isArray((plan as MasPlan).nodes)
}

function masPlanFromTool(tool: ToolCall): MasPlan {
  return tool.uiPayload?.mas_plan as MasPlan
}

function contextSummaryFromTool(tool: ToolCall): Record<string, unknown> | undefined {
  const summary = tool.uiPayload?.context_summary
  return summary && typeof summary === 'object' ? (summary as Record<string, unknown>) : undefined
}

function stringPayloadValue(tool: ToolCall, key: string): string | undefined {
  const value = tool.uiPayload?.[key]
  return value === undefined || value === null ? undefined : String(value)
}

function isPipelineTask(tool: ToolCall): boolean {
  return ['rna_seq', 'atac_seq'].includes(String(tool.uiPayload?.pipeline_type || ''))
}

function pipelineType(tool: ToolCall): PipelineType {
  return String(tool.uiPayload?.pipeline_type) as PipelineType
}

function handlePipelineVisualization(taskId: string, type: PipelineType): void {
  void agentHubStore.sendMessage(
    `请读取 ${type} 任务 ${taskId} 的结果，并为关键质量指标和差异分析结果生成可视化。`,
  )
}

function handleAdjustPipeline(type: PipelineType): void {
  void agentHubStore.sendMessage(`请帮我检查并调整这次 ${type} 分析的参数，然后重新预检。`)
}
</script>

<template>
  <!-- Studio HITL 审批卡片（有 approval 数据时出现，决议后保留终态徽标） -->
  <ApprovalCard v-if="tool.approval" :tool="tool" />
  <!-- Studio 代码工具（仅工作台页面）：代码卡片，支持编辑/重跑/产物 -->
  <StudioCodeCard v-if="isStudioCodeToolCall(tool)" :tool="tool" />
  <MasPlanPreviewCard
    v-else-if="hasMasPlan(tool)"
    :plan="masPlanFromTool(tool)"
    :context-summary="contextSummaryFromTool(tool)"
    :session-id="stringPayloadValue(tool, 'session_id')"
    :workspace-id="stringPayloadValue(tool, 'workspace_id')"
  />
  <HandoffCard v-else-if="isHandoffTool(tool)" :tool="tool" />
  <div v-else-if="isArtifactRegisterTool(tool)" class="artifact-register-card">
    <div class="artifact-register-icon">✓</div>
    <div>
      <div class="artifact-register-title">
        已登记为《{{ tool.uiPayload?.title }}》v{{ tool.uiPayload?.version }}
      </div>
      <div v-if="tool.uiPayload?.parent_id" class="artifact-register-sub">
        已挂到原报告版本树
      </div>
    </div>
  </div>
  <McpToolCallCard
    v-else
    :tool="tool"
    @confirm-tool="(name, args) => emit('confirmTool', name, args)"
    @open-tool-page="(route, args) => emit('openToolPage', route, args)"
    @generate-visualization="handlePipelineVisualization"
    @adjust-parameters="handleAdjustPipeline"
  />
</template>

<style scoped>
.artifact-register-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(24, 160, 88, 0.25);
  border-radius: 10px;
  background: rgba(24, 160, 88, 0.08);
}
.artifact-register-icon {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  background: #18a058;
  font-weight: 700;
}
.artifact-register-title {
  font-size: 13px;
  font-weight: 600;
}
.artifact-register-sub {
  margin-top: 2px;
  font-size: 11px;
  color: var(--chat-text-muted, #888);
}
</style>
