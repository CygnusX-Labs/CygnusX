import apiClient from './client'

export interface DiscoveryProposal {
  schema_version: '1.0'
  proposal_id: string
  source: string
  accession: string | null
  title: string
  summary: string
  organism: string | null
  assay_type: string | null
  sample_count: number | null
  metadata_status: 'unverified' | 'agent_asserted' | 'platform_verified'
  source_links: string[]
  evidence_refs: string[]
  retrieved_at: string | null
  project_id: string | null
  conversation_id: string
  provenance: Record<string, unknown>
  next_actions: string[]
}

export interface ResearchSession {
  session_id: string
  title: string
  project_id: string | null
  model_id: string
  status: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface ResearchMessage {
  message_id: string
  role: 'user' | 'assistant'
  content: string
  status: string
  metadata_json: {
    proposals?: DiscoveryProposal[]
    events?: { cards?: unknown[]; tools?: unknown[]; grounding?: unknown }
  }
  created_at: string
}

export const researchAgentApi = {
  async listSessions(projectId?: string): Promise<ResearchSession[]> {
    const response = await apiClient.get<ResearchSession[]>('/research-agent/sessions', {
      params: projectId ? { project_id: projectId } : undefined,
    })
    return response.data
  },
  async createSession(projectId?: string): Promise<ResearchSession> {
    const response = await apiClient.post<ResearchSession>('/research-agent/sessions', {
      project_id: projectId || undefined,
    })
    return response.data
  },
  async getMessages(sessionId: string): Promise<ResearchMessage[]> {
    const response = await apiClient.get<ResearchMessage[]>(`/research-agent/sessions/${sessionId}/messages`)
    return response.data
  },
  async cancel(sessionId: string): Promise<void> {
    await apiClient.post(`/research-agent/sessions/${sessionId}/cancel`)
  },
}

export function researchStreamUrl(sessionId: string): string {
  return `/api/v1/research-agent/sessions/${encodeURIComponent(sessionId)}/messages:stream`
}
