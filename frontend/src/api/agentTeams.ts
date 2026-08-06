import apiClient from '@/api/client'

export type AgentTeamsCaseStatus =
  | 'received' | 'preflight_running' | 'preflight_blocked' | 'waiting_for_correction'
  | 'approval_pending' | 'approved' | 'executing' | 'execution_failed' | 'quality_running'
  | 'quality_blocked' | 'remediation_pending' | 'delivery_ready' | 'closed' | 'cancelled'

export interface AgentTeamsCase {
  case_id: string
  project_ref: { kind: string; id: string; location?: string | null }
  intent: string
  requester_ref: string
  /** 后端按 requester_ref 回填的用户名；昵称存在时由前端优先显示。 */
  requester_username?: string | null
  requester_nickname?: string | null
  team_id: string
  origin_consultation_id?: string | null
  consultation_summary?: string | null
  status: AgentTeamsCaseStatus
  omic_task_ids: string[]
  work_items: AgentTeamsWorkItem[]
  quality_decision?: string | null
  manifest_uri?: string | null
  created_at: string
  updated_at: string
}

export interface AgentTeamsWorkItem {
  work_item_id: string
  parent_work_item_id?: string | null
  target: string
  objective: string
  skill_name: string
  status: 'pending' | 'in_progress' | 'completed' | 'blocked' | 'failed' | 'cancelled'
  summary?: string | null
  updated_at: string
}

export interface AgentTeamsEvent {
  event_id: string
  recorded_at: string
  case_id: string
  actor: string
  event_type: string
  payload: Record<string, unknown>
}

export interface AgentTeamsCaseCreateRequest {
  project_id: string
  intent: string
  flow_id: string
  sample_sheet: Array<Record<string, unknown>>
  comparisons?: Array<Record<string, unknown>>
}

export interface AgentTeamsCaseSubmitRequest {
  task_name: string
}

export interface AgentTeamsCaseListParams {
  status?: AgentTeamsCaseStatus
  project_id?: string
  cursor?: string
  limit?: number
}

export interface AgentTeamsCaseListResponse {
  items: AgentTeamsCase[]
  total: number
  next_cursor?: string | null
}

export interface AgentTeamsEventListResponse {
  events: AgentTeamsEvent[]
  next_cursor?: string | null
}

export interface AgentTeamsBridgeStatus {
  available: boolean
  enabled: boolean
  configured: boolean
  connected: boolean
  configuration_source: 'database' | 'environment'
  reason: 'disabled' | 'incomplete_configuration' | 'bridge_unreachable' | null
}

export interface AgentTeamsChatRoom {
  available: boolean
  element_url: string
  reason: 'not_configured' | null
  case_id?: string
  source?: 'case' | 'global'
}

export const agentTeamsApi = {
  async status(): Promise<AgentTeamsBridgeStatus> {
    return (await apiClient.get('/agent-teams/status')).data
  },
  async getChatRoom(caseId?: string): Promise<AgentTeamsChatRoom> {
    return (await apiClient.get<AgentTeamsChatRoom>('/agent-teams/chat-room', {
      params: caseId ? { case_id: caseId } : undefined,
    })).data
  },
  async listCases(params: AgentTeamsCaseListParams = {}): Promise<AgentTeamsCaseListResponse> {
    return (await apiClient.get<AgentTeamsCaseListResponse>('/agent-teams/cases', { params })).data
  },
  async createCase(payload: AgentTeamsCaseCreateRequest): Promise<AgentTeamsCase> {
    return (await apiClient.post<AgentTeamsCase>('/agent-teams/cases', payload)).data
  },
  async getCase(caseId: string): Promise<AgentTeamsCase> {
    return (await apiClient.get<AgentTeamsCase>(`/agent-teams/cases/${caseId}`)).data
  },
  async refreshCase(caseId: string): Promise<AgentTeamsCase> {
    return (await apiClient.post<AgentTeamsCase>(`/agent-teams/cases/${caseId}/refresh`)).data
  },
  async submitCase(caseId: string, payload: AgentTeamsCaseSubmitRequest): Promise<{ omic_task_id: string; status: string }> {
    return (await apiClient.post(`/agent-teams/cases/${caseId}/submit`, payload)).data
  },
  async getEvents(
    caseId: string,
    params: { cursor?: string; limit?: number } = {},
  ): Promise<AgentTeamsEventListResponse> {
    return (await apiClient.get<AgentTeamsEventListResponse>(
      `/agent-teams/cases/${caseId}/events`,
      { params },
    )).data
  },
}
