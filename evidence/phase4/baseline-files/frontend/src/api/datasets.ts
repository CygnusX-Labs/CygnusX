import apiClient from './client'

export interface DatasetItem { id: string; project_id: string; name: string; assay_type: string; status: string }
export interface DatasetVersion { id: string; number: number; status: string; revision_reason: string }
export interface DatasetDetail extends DatasetItem { versions: DatasetVersion[] }
export interface DatasetAsset { asset_id: string; file_record_id: string; asset_role: string; data_type: string; format: string; size: number; sha256: string | null; checksum_status: string; availability: string }
export interface DatasetSample { sample_id: string; sample_key: string; source_metadata: Record<string, unknown>; user_annotation: Record<string, unknown>; mapping_status: string; file_record_ids: string[] }
export interface DataHandoff { dataset_id: string; dataset_version_id: string; project_id: string; manifest_hash: string; assets: DatasetAsset[]; samples: DatasetSample[]; source: unknown[]; validation: { dataset_ready: boolean; blocking_reasons: string[]; compatible_flow_ids: string[]; worker_paths_verified: boolean } }
export interface ImportProposal { proposal_id: string; ingestion_id: string; project_id: string; dataset_version_id: string | null; state: string; preview: Record<string, unknown>; normalized_parameters: Record<string, unknown>; parameters_hash: string; expires_at: string | null; write_enabled: boolean; gate: string; tasks: { task_id: string; status: string; progress: null }[]; errors: unknown[] }
export interface GeoCandidate { primary_accession: string; status: string; error_code?: string; samples: Record<string, unknown>[]; files: { url: string; original_name: string; size: number | null; data_type: string }[]; runs: { run_accession: string; library_layout: string; files: unknown[] }[]; source_evidence: Record<string, unknown>[]; confidence_flags: string[] }
const base = (project: string) => `/projects/${encodeURIComponent(project)}`
const versionBase = (project: string, dataset: string, version: string) => `${base(project)}/datasets/${encodeURIComponent(dataset)}/versions/${encodeURIComponent(version)}`
export const datasetsApi = {
  async newVersion(project: string, dataset: string, revision_reason: string): Promise<{version_id:string}> { return (await apiClient.post(`${base(project)}/datasets/${encodeURIComponent(dataset)}/versions`, { revision_reason })).data },
  async reviewVersion(project: string, dataset: string, version: string, assay_type: string, reason: string): Promise<unknown> { return (await apiClient.post(`${versionBase(project, dataset, version)}/review`, { assay_type, reason })).data },
  async reviewRole(project: string, dataset: string, version: string, asset: string, role: string, reason: string): Promise<unknown> { return (await apiClient.post(`${versionBase(project, dataset, version)}/assets/${encodeURIComponent(asset)}/review`, { role, reason })).data },
  async imports(project: string): Promise<ImportProposal[]> { return (await apiClient.get(`${base(project)}/import-proposals`)).data },
  async list(project: string): Promise<DatasetItem[]> { return (await apiClient.get(`${base(project)}/datasets`)).data },
  async detail(project: string, dataset: string): Promise<DatasetDetail> { return (await apiClient.get(`${base(project)}/datasets/${encodeURIComponent(dataset)}`)).data },
  async handoff(project: string, dataset: string, version: string): Promise<DataHandoff> { return (await apiClient.get(`${versionBase(project, dataset, version)}/handoff`)).data },
  async discover(project: string, accession: string): Promise<GeoCandidate> { return (await apiClient.get(`${base(project)}/dataset-discovery/${encodeURIComponent(accession)}`)).data },
  async prepare(project: string, args: Record<string, unknown>): Promise<ImportProposal | { state: string; error_code: string }> { return (await apiClient.post(`${base(project)}/import-proposals`, args)).data },
  async proposal(project: string, id: string): Promise<ImportProposal> { return (await apiClient.get(`${base(project)}/import-proposals/${encodeURIComponent(id)}`)).data },
  async decide(project: string, id: string, approve: boolean): Promise<ImportProposal> { return (await apiClient.post(`${base(project)}/import-proposals/${encodeURIComponent(id)}/${approve ? 'approve' : 'reject'}`)).data },
  async verify(project: string, dataset: string, version: string): Promise<DataHandoff> { return (await apiClient.post(`${versionBase(project, dataset, version)}/verify`)).data },
  async freeze(project: string, dataset: string, version: string): Promise<DataHandoff> { return (await apiClient.post(`${versionBase(project, dataset, version)}/handoff/freeze`)).data },
  async reviewSample(project: string, dataset: string, version: string, sample: string, group: string): Promise<unknown> { return (await apiClient.post(`${versionBase(project, dataset, version)}/samples/${encodeURIComponent(sample)}/review`, { group })).data },
  async prepareAnalysis(project: string, dataset: string, version: string, flow: string, options: Record<string, unknown>): Promise<Record<string, unknown>> { return (await apiClient.post(`${versionBase(project, dataset, version)}/analysis-prepare`, { flow_id: flow, options })).data },
}
export function asImportProposal(value: unknown): ImportProposal | null {
  if (!value || typeof value !== 'object') return null
  const candidate = value as Partial<ImportProposal>
  return typeof candidate.ingestion_id === 'string' && typeof candidate.project_id === 'string' && typeof candidate.parameters_hash === 'string' && !!candidate.preview ? candidate as ImportProposal : null
}
