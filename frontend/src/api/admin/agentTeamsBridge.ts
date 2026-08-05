import apiClient from '@/api/client'

export interface AgentTeamsBridgeConfig {
  enabled: boolean
  bridge_url: string
  timeout_seconds: number
  manager_token: string
  data_steward_token: string
  approval_token: string
  workflow_operator_token: string
  element_url: string
  source: 'environment' | 'database'
  configured: boolean
  connected: boolean
}

export interface AgentTeamsBridgeHealth {
  connection: { connected: boolean; enabled: boolean; configured: boolean; reason?: string | null }
  identities: Array<{ identity: string; valid: boolean }>
  workers: Array<{
    identity: string
    configured: boolean
    active: boolean
    last_seen_at?: string | null
    age_seconds?: number | null
  }>
  allowed_flows: string[]
  scrna_submit_available: boolean
}

export interface AgentTeamsBridgeTokenBundle {
  manager_token: string
  data_steward_token: string
  approval_token: string
  workflow_operator_token: string
}

export interface AgentTeamsBridgeResourceCase {
  case_id: string
  team_id: string
  intent: string
  status: string
  project_ref: { id: string }
  updated_at: string
}

export interface AgentTeamsBridgeResourceSnapshot {
  health: AgentTeamsBridgeHealth
  teams: Array<{ team_id: string; case_count: number }>
  cases: AgentTeamsBridgeResourceCase[]
  total_cases: number
}

export type AgentTeamsBridgeConfigUpdate = Pick<
  AgentTeamsBridgeConfig,
  | 'enabled'
  | 'bridge_url'
  | 'timeout_seconds'
  | 'manager_token'
  | 'data_steward_token'
  | 'approval_token'
  | 'workflow_operator_token'
>

export const agentTeamsBridgeAdminApi = {
  async get(): Promise<AgentTeamsBridgeConfig> {
    return (await apiClient.get<AgentTeamsBridgeConfig>('/admin/agentteams-bridge')).data
  },
  async update(payload: AgentTeamsBridgeConfigUpdate, totpCode: string): Promise<AgentTeamsBridgeConfig> {
    return (await apiClient.put<AgentTeamsBridgeConfig>('/admin/agentteams-bridge', payload, {
      headers: { 'X-TOTP-Code': totpCode },
    })).data
  },
  async health(): Promise<AgentTeamsBridgeHealth> {
    return (await apiClient.get<AgentTeamsBridgeHealth>('/admin/agentteams-bridge/health')).data
  },
  async generateTokens(totpCode: string): Promise<AgentTeamsBridgeTokenBundle> {
    return (await apiClient.post<AgentTeamsBridgeTokenBundle>('/admin/agentteams-bridge/tokens', undefined, {
      headers: { 'X-TOTP-Code': totpCode },
    })).data
  },
  async resources(): Promise<AgentTeamsBridgeResourceSnapshot> {
    return (await apiClient.get<AgentTeamsBridgeResourceSnapshot>('/admin/agentteams-bridge/resources')).data
  },
  async reconcileCase(caseId: string, totpCode: string): Promise<AgentTeamsBridgeResourceCase> {
    return (await apiClient.post<AgentTeamsBridgeResourceCase>(`/admin/agentteams-bridge/cases/${caseId}/reconcile`, undefined, {
      headers: { 'X-TOTP-Code': totpCode },
    })).data
  },
}
