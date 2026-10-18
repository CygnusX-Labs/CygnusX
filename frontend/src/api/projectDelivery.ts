import apiClient from './client'
import type { ProjectDelivery } from './researchDelivery'

export type PackageKind = 'evidence' | 'results' | 'reproduction_materials'
export interface ExportSelection { kind: PackageKind; task_ids: string[]; report_ids: string[]; source_manifest_job_id?: string; project_report_job_ids?: string[] }
export interface DeliveryManifest {
  project_id: string; selection: ExportSelection; evidence_status: 'partial' | 'complete'
  files: { path: string; size: number; sha256: string }[]
  references: { kind: string; id: string | null; status: string; disposition: string; reason: string | null }[]
  gaps: string[]; reproduction_status: 'NOT_RUN'
}
export interface ExportPreview { manifest: DeliveryManifest; manifest_digest: string }
export interface ExportJob {
  id: string; project_id: string; status: string; manifest_digest: string; evidence_partial: boolean
  attempt_count: number; retryable: boolean; error_code: string | null
  archive_sha256: string | null; archive_size: number | null; file_record_id: string | null
}
export interface DeliveryInventory extends ProjectDelivery {
  association_status: string; historical_tasks: { status: string; reason: string }; export_enabled: boolean
}
const base = (project: string) => `/projects/${encodeURIComponent(project)}`
export const projectDeliveryApi = {
  async summaryPreview(project: string, id: string, signal?: AbortSignal): Promise<string> {
    return (await apiClient.get(`${base(project)}/exports/${encodeURIComponent(id)}/summary-preview`, { signal, responseType: 'text' })).data
  },
  async inventory(project: string, signal?: AbortSignal): Promise<DeliveryInventory> {
    return (await apiClient.get(`${base(project)}/delivery-inventory`, { signal })).data
  },
  async prepare(project: string, selection: ExportSelection, signal?: AbortSignal): Promise<ExportPreview> {
    return (await apiClient.post(`${base(project)}/exports/prepare`, selection, { signal })).data
  },
  async create(project: string, preview: ExportPreview, requestKey: string, signal?: AbortSignal): Promise<ExportJob> {
    return (await apiClient.post(`${base(project)}/exports`, {
      selection: preview.manifest.selection, manifest_digest: preview.manifest_digest, request_key: requestKey,
    }, { signal })).data
  },
  async status(project: string, id: string, signal?: AbortSignal): Promise<ExportJob> {
    return (await apiClient.get(`${base(project)}/exports/${encodeURIComponent(id)}`, { signal })).data
  },
  async retry(project: string, id: string): Promise<ExportJob> {
    return (await apiClient.post(`${base(project)}/exports/${encodeURIComponent(id)}/retry`)).data
  },
  async download(project: string, id: string): Promise<Blob> {
    return (await apiClient.get(`${base(project)}/exports/${encodeURIComponent(id)}/download`, { responseType: 'blob' })).data
  },
}
