import apiClient from './client'

export interface MasNodeProgress {
  key: string
  agent_id: string
  intent: string
  status: string
  attempt_count: number
}

export interface MasRunProgress {
  run_id: string
  status: string
  version: number
  nodes: MasNodeProgress[]
}

export interface MasPlanNode {
  key: string
  agent_id: string
  intent: string
  depends_on?: string[]
  input_contract?: Record<string, unknown>
  output_contract?: Record<string, unknown>
  parameters?: Record<string, unknown>
  resources?: Record<string, unknown>
  max_attempts?: number
  allow_skipped_dependencies?: boolean
}

export interface MasPlan {
  schema_version?: string
  title: string
  nodes: MasPlanNode[]
}

export interface MasRun {
  id: string
  plan_id: string
  status: string
  version: number
  context_summary: Record<string, unknown>
  created_at: string
  finished_at: string | null
}

export interface MasRunCreateRequest {
  plan: MasPlan
  context_summary?: Record<string, unknown>
  session_id?: string
  workspace_id?: string
}

export const masApi = {
  createRun: (request: MasRunCreateRequest) =>
    apiClient.post<MasRun>('/mas/runs', request).then((response) => response.data),
  approveRun: (runId: string) =>
    apiClient.post<MasRun>(`/mas/runs/${runId}/approve`).then((response) => response.data),
  getProgress: (runId: string) =>
    apiClient.get<MasRunProgress>(`/mas/runs/${runId}/progress`).then((response) => response.data),
  streamProgress: async (
    runId: string,
    onProgress: (progress: MasRunProgress) => void,
    signal: AbortSignal,
  ): Promise<void> => {
    const token = localStorage.getItem('access_token')
    const response = await fetch(`/api/v1/mas/runs/${runId}/events`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal,
    })
    if (!response.ok || !response.body) throw new Error('MAS SSE connection failed')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) return
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() || ''
      for (const frame of frames) {
        const data = frame.split('\n').find((line) => line.startsWith('data: '))?.slice(6)
        if (data && data !== '{}') onProgress(JSON.parse(data) as MasRunProgress)
      }
    }
  },
}
