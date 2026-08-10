import type { AgentTeamsCaseStatus } from '@/api/agentTeams'

export const agentTeamsStatusLabel: Record<AgentTeamsCaseStatus, string> = {
  received: '已接收',
  planning_running: '规划中',
  preflight_running: '预检中',
  preflight_blocked: '预检阻断',
  waiting_for_correction: '等待修正',
  approval_pending: '待审批',
  approved: '已批准',
  executing: '执行中',
  execution_failed: '执行失败',
  quality_running: '质量检查中',
  quality_blocked: '质量阻断',
  remediation_pending: '等待修复',
  delivery_ready: '可交付',
  closed: '已关闭',
  cancelled: '已取消',
}

export const agentTeamsNextActor: Partial<Record<AgentTeamsCaseStatus, string>> = {
  received: '数据管理员',
  preflight_running: '数据管理员',
  preflight_blocked: '请求人',
  waiting_for_correction: '请求人',
  approval_pending: '审批人',
  approved: '流程执行者',
  executing: '流程执行者',
  execution_failed: '流程执行者',
  quality_running: '质量控制',
  quality_blocked: '流程执行者',
  remediation_pending: '流程执行者',
  delivery_ready: '请求人',
}
