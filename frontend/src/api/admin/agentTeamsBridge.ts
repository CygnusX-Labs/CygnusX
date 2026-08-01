import apiClient from '@/api/client'

export interface AgentTeamsBridgeConfig {
  enabled: boolean
  bridge_url: string
  timeout_seconds: number
  manager_token: string
  data_steward_token: string
  approval_token: string
  workflow_operator_token: string
  source: 'environment' | 'database'
  configured: boolean
  connected: boolean
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
}
