import apiClient from './client'

export type Integrity = 'VERIFIED' | 'PARTIAL' | 'UNKNOWN' | 'MISSING' | 'FAILED' | 'NOT_APPLICABLE'
export interface ResearchArtifact { file_record_id: string | null; logical_name: string; category: string; size: number | null; sha256: string | null; declared_sha256: string | null; integrity: Integrity; file_url: string | null }
export interface ResearchReport { report_id: string; kind: 'scientific' | 'reproducibility' | 'delivery'; state: string; integrity: Integrity; result_observation_id: string | null; report_url: string }
export interface ResearchProvenance {
  schema_version: 'cygnusx.research_provenance.v1'; task_id: string; owner_id: string; project_id: string | null
  analysis_link_id: string | null; parameters_sha256: string | null; result_observation_id: string | null; manifest_sha256: string | null
  analysis_parameters: Record<string, unknown>; flow: Record<string, unknown>; source: Record<string, unknown>[]; samples: Record<string, unknown>[]; inputs: ResearchArtifact[]
  report_jobs: Record<string, unknown>[]; runtime: Record<string, unknown>; started_at: string | null; finished_at: string | null
  observation_scope: 'capture_time_bytes_not_execution_attestation'
  dataset_id: string | null; dataset_version_id: string | null; handoff_hash: string | null
  run_id: string | null; compute_state: string; input_integrity: Integrity; result_integrity: Integrity
  evidence_state: Integrity; delivery_state: 'READY' | 'PARTIAL' | 'BLOCKED' | 'UNKNOWN'
  artifacts: ResearchArtifact[]; reports: ResearchReport[]; gaps: string[]
}
export interface DatasetDelivery { dataset_id: string; dataset_version_id: string; handoff_hash: string | null; analyses: (ResearchProvenance | { task_id: null; state: string; gaps: string[] })[]; gaps: string[] }
export interface ProjectDelivery { project_id: string; datasets: DatasetDelivery[]; runtime_admission: 'BLOCKED'; truncated: boolean }
export const researchDeliveryApi = {
  async downloadArtifact(fileId: string): Promise<Blob> {
    return (await apiClient.get(`/files/${encodeURIComponent(fileId)}/download`, { responseType: 'blob' })).data
  },
  async project(projectId: string, signal?: AbortSignal): Promise<ProjectDelivery> {
    return (await apiClient.get(`/projects/${encodeURIComponent(projectId)}/research-delivery`, { signal })).data
  },
  async task(taskId: string): Promise<ResearchProvenance> {
    return (await apiClient.get(`/tasks/${encodeURIComponent(taskId)}/provenance`)).data
  },
}
