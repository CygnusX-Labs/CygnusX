/**
 * Agent 模板 API — 前台读取 + 后台 CRUD
 */
import apiClient from './client'
import type { AgentTemplate } from '@/types/agent'

/** 后端 AgentTemplateDTO -> 前端 AgentTemplate */
function toAgent(d: any): AgentTemplate {
  return {
    id: d.agent_id,
    name: d.name,
    description: d.description ?? '',
    avatar: d.avatar ?? '🤖',
    color: d.color ?? '#4f8ef7',
    category: d.category ?? 'general',
    model_engine: d.model_engine ?? '',
    model_name: d.model_name ?? '',
    model_id: d.model_id ?? undefined,
    system_prompt: d.system_prompt ?? '',
    welcome_message: d.welcome_message ?? '',
    mcp_ids: (d.mcp_ids ?? []).map(String),
    skill_ids: (d.skill_ids ?? []).map(String),
    features: d.features || {},
    is_active: d.is_active ?? true,
    is_builtin: d.is_builtin ?? false,
    is_default: d.is_default ?? false,
  }
}

export const agentApi = {
  /** 启用中的 Agent 列表（前台集市） */
  async list(): Promise<AgentTemplate[]> {
    const res = await apiClient.get('/agents')
    return (res.data as any[]).map(toAgent)
  },

  /** Agent 详情 */
  async get(agentId: string): Promise<AgentTemplate> {
    const res = await apiClient.get(`/agents/${agentId}`)
    return toAgent(res.data)
  },
}

export const adminAgentApi = {
  async list(): Promise<AgentTemplate[]> {
    const res = await apiClient.get('/admin/agents')
    return (res.data as any[]).map(toAgent)
  },
  async create(payload: Partial<AgentTemplate> & { id?: string }): Promise<AgentTemplate> {
    const res = await apiClient.post('/admin/agents', toPayload(payload))
    return toAgent(res.data)
  },
  async update(agentId: string, payload: Partial<AgentTemplate>): Promise<AgentTemplate> {
    const res = await apiClient.put(`/admin/agents/${agentId}`, toPayload(payload))
    return toAgent(res.data)
  },
  async remove(agentId: string): Promise<void> {
    await apiClient.delete(`/admin/agents/${agentId}`)
  },
  async toggle(agentId: string): Promise<AgentTemplate> {
    const res = await apiClient.post(`/admin/agents/${agentId}/toggle`)
    return toAgent(res.data)
  },
  async setDefault(agentId: string): Promise<void> {
    await apiClient.post(`/admin/agents/${agentId}/set-default`)
  },
}

/** 前端 AgentTemplate -> 后端 CreateAgentRequest/UpdateAgentRequest */
function toPayload(a: Partial<AgentTemplate> & { id?: string }): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  if (a.id !== undefined) out.agent_id = a.id
  if (a.name !== undefined) out.name = a.name
  if (a.description !== undefined) out.description = a.description
  if (a.avatar !== undefined) out.avatar = a.avatar
  if (a.color !== undefined) out.color = a.color
  if (a.category !== undefined) out.category = a.category
  if (a.model_id !== undefined) {
    out.model_id = a.model_id || null
  } else if ('model_id' in a) {
    out.model_id = null
  }
  if (a.system_prompt !== undefined) out.system_prompt = a.system_prompt
  if (a.welcome_message !== undefined) out.welcome_message = a.welcome_message
  if (a.mcp_ids !== undefined) out.mcp_ids = a.mcp_ids || []
  if (a.skill_ids !== undefined) out.skill_ids = a.skill_ids || []
  if (a.features !== undefined) out.features = a.features
  if (a.is_active !== undefined) out.is_active = a.is_active
  if (a.is_default !== undefined) out.is_default = a.is_default
  return out
}
