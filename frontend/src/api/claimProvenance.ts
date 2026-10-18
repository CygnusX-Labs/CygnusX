import apiClient from './client'

export interface ClaimCellQuery {
  task_id: string; file_record_id: string; feature_id: string
  column: 'log2FoldChange' | 'pvalue' | 'padj' | 'baseMean' | 'lfcSE' | 'stat'
  source_report_id?: string | null
}
export interface ClaimProvenance {
  schema_version: 'cygnusx.claim_provenance.v1'; claim_id: string; claim_text: string
  claim_text_verified: false; project_id: string; source_report_id: string | null
  report_version: number | null; report_snapshot_id: string | null; snapshot_digest: string | null
  task_id: string; result_observation_id: string | null; observation_digest: string | null
  observation_binding: 'VERIFIED_ASSOCIATION' | 'NOT_RECORDED'
  file_record_id: string; file_sha256: string; table_identifier: 'deg.tsv'
  row_identifier: string; row_number: number; column_identifier: string; value: number | null
  verification_status: 'VERIFIED_VALUE' | 'NOT_VERIFIED'; supported_statement: string | null
  supported_statement_status: 'SUPPORTED_CLAIM' | 'NOT_VERIFIED'; interpretation_status: 'AI_INTERPRETATION' | null
  dataset_version_id: string | null; analysis_link_id: string | null; definition_digest: string | null
  execution_binding_digest: string | null; definition_status: string; input_file_record_ids: string[]
  missing_evidence: string[]; reproducibility_status: 'NOT_RUN'; verification_scope: string
}
export const claimProvenanceApi = {
  async inspect(project: string, query: ClaimCellQuery, signal?: AbortSignal): Promise<ClaimProvenance> {
    return (await apiClient.post(`/projects/${encodeURIComponent(project)}/research-evidence/claim-provenance`, query, { signal })).data
  },
}
