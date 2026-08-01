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
  team_id: string
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

export const agentTeamsApi = {
  async status(): Promise<{ available: boolean }> {
    return (await apiClient.get('/agent-teams/status')).data
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
