import apiClient from './client'
import type { ClaimCellQuery } from './claimProvenance'

export interface ReportRequest { source_manifest_job_id: string; claims: ClaimCellQuery[]; format: 'html' | 'html_pdf' }
export interface ReportPreparation { prepare_digest: string; source: { manifest: { selection: import('./projectDelivery').ExportSelection }; source_manifest_digest: string; selection_digest: string; selection: { claims: { claim_id: string; value: number | null; verification_status: string; supported_statement: string | null }[] } } }
export interface ProjectReportJob {
  id: string; project_id: string; status: string; source_digest: string; version: number
  source_selection?: import('./projectDelivery').ExportSelection
  html_sha256: string | null; html_size: number | null; pdf_sha256: string | null; pdf_size: number | null
  pdf_status: string; error_code: string | null
}
const base = (project: string) => `/projects/${encodeURIComponent(project)}/scientific-summary`
export const projectReportApi = {
  async prepare(project: string, request: ReportRequest, signal: AbortSignal): Promise<ReportPreparation> {
    return (await apiClient.post(`${base(project)}/prepare`, request, { signal })).data
  },
  async create(project: string, request: ReportRequest, digest: string, key: string, signal: AbortSignal): Promise<{ id: string }> {
    return (await apiClient.post(base(project), { ...request, prepare_digest: digest, request_key: key }, { signal })).data
  },
  async status(project: string, id: string, signal: AbortSignal): Promise<ProjectReportJob> {
    return (await apiClient.get(`${base(project)}/${encodeURIComponent(id)}`, { signal })).data
  },
  async preview(project: string, id: string, signal: AbortSignal): Promise<string> {
    return (await apiClient.get(`${base(project)}/${encodeURIComponent(id)}/preview`, { signal, responseType: 'text' })).data
  },
  async download(project: string, id: string, format: 'html' | 'pdf', signal: AbortSignal): Promise<Blob> {
    return (await apiClient.get(`${base(project)}/${encodeURIComponent(id)}/download`, { signal, params: { format }, responseType: 'blob' })).data
  },
}
