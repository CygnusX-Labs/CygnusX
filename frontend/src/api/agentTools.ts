import apiClient from './client'

export interface ToolProposal {
  proposal_id: string
  conversation_id: string
  operation: string
  project_id: string | null
  parameters_hash: string
  normalized_parameters: Record<string, unknown>
  preview: Record<string, unknown>
  confirmation_id: string
  expires_at: string
  state: string
  write_enabled: boolean
  gate: string
}

export interface ToolResult {
  schema_version: string
  invocation_id: string
  result: ToolProposal | Record<string, unknown> | unknown[]
}

export interface ToolLink {
  invocation_id: string
  capability_id: string
  project_id: string | null
  state: string
  parameters_hash: string
  preview: Record<string, unknown>
  task_id: string | null
  dataset_import?: import('./datasets').ImportProposal
  dataset_analysis?: Record<string, unknown>
  proposal?: ToolProposal
  task?: { task_id: string; status: string; progress: number | null; task_url: string }
}

const base = (session: string) => `/agent-tools/sessions/${encodeURIComponent(session)}`
export const agentToolsApi = {
  async capabilities(session: string): Promise<{ tools: { capability_id: string }[]; write_enabled: false; gate: string }> {
    return (await apiClient.get(`${base(session)}/capabilities`)).data
  },
  async invoke(session: string, capability_id: string, args: Record<string, unknown> = {}): Promise<ToolResult> {
    return (await apiClient.post(`${base(session)}/invoke`, { capability_id, arguments: args })).data
  },
  async related(session: string): Promise<ToolLink[]> {
    return (await apiClient.get(`${base(session)}/related`)).data
  },
  async decide(session: string, proposal: string, approve: boolean): Promise<{ state: string; write_enabled: boolean }> {
    return (await apiClient.post(`${base(session)}/proposals/${encodeURIComponent(proposal)}/${approve ? 'approve' : 'reject'}`)).data
  },
}

export function asToolProposal(value: unknown): ToolProposal | null {
  if (!value || typeof value !== 'object') return null
  const result = value as Partial<ToolProposal>
  return typeof result.proposal_id === 'string' && typeof result.conversation_id === 'string'
    && typeof result.parameters_hash === 'string' && !!result.normalized_parameters
    && typeof result.confirmation_id === 'string' ? result as ToolProposal : null
}
