import apiClient from './client'
import type { ResearchReport } from './researchDelivery'

export type PlanStatus = 'DRAFT' | 'VALIDATED' | 'READY_FOR_REVIEW' | 'REVIEW_REQUIRED' | 'APPROVED' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'PARTIAL' | 'FAILED' | 'CANCELLED' | 'RECONCILIATION_REQUIRED'
export type StepStatus = 'WAITING_INPUT' | 'READY' | 'WAITING_APPROVAL' | 'SUBMITTING' | 'QUEUED' | 'RUNNING' | 'COMPLETE' | 'PARTIAL' | 'FAILED' | 'CANCELLED' | 'RECONCILIATION_REQUIRED'
export type StepKind = 'DISCOVERY' | 'DATASET_INSPECT' | 'WORKFLOW_MATCH' | 'ANALYSIS_PREPARE' | 'DATASET_IMPORT_PREPARE' | 'DATASET_IMPORT' | 'ANALYSIS_EXECUTE' | 'DELIVERY_PREPARE' | 'REPORT_PUBLISH'
export interface ResearchStepDraft {
  step_id: string; kind: StepKind; goal: string; depends_on: string[]; arguments: Record<string, unknown>
  bindings: { argument: 'proposal_id' | 'task_id' | 'dataset_id' | 'version_id'; from_step: string; output: 'analysis_proposal' | 'import_proposal' | 'task_id' | 'dataset_version' }[]
  failure_policy: 'STOP_AND_RECONCILE'
}
export interface ResearchPlanDraft {
  schema_version: 'cygnusx.research_plan.v1'; research_question: string; assumptions: string[]; steps: ResearchStepDraft[]
  budget: { max_tool_calls: number; max_elapsed_seconds: number; max_model_tokens: number; max_retries: 0; estimated_compute_seconds: number | null; estimated_storage_bytes: number | null }
}
export interface ResearchPlan {
  schema_version: 'cygnusx.research_plan.v1'; plan_id: string; version: number; project_id: string; digest: string
  status: PlanStatus; mode: 'PLAN_ONLY'; draft: ResearchPlanDraft; gaps: string[]; created_at: string; reviewed_at: string | null; superseded_by: string | null
  steps: { step_id: string; kind: StepKind; capability_id: string | null; effect: 'READ_ONLY' | 'PREPARE' | 'MUTATING' | 'REPORT_PUBLISH'; approval_required: boolean; expected_output: string; status: StepStatus; invocation_id: string | null; task_id: string | null; error_code: string | null; result_manifest_sha256?: string | null; reports?: ResearchReport[] }[]
}
export interface PlanEvent { kind: string; at: string; step_id?: string; invocation_id?: string; action?: string }
const base = (project: string) => `/projects/${encodeURIComponent(project)}/research-plans`
export const researchPlansApi = {
  async list(project: string, signal?: AbortSignal): Promise<ResearchPlan[]> { return (await apiClient.get(base(project), { signal })).data },
  async get(project: string, plan: string, signal?: AbortSignal): Promise<ResearchPlan> { return (await apiClient.get(`${base(project)}/${encodeURIComponent(plan)}`, { signal })).data },
  async review(project: string, plan: string, digest: string): Promise<ResearchPlan> { return (await apiClient.post(`${base(project)}/${encodeURIComponent(plan)}/review`, { expected_digest: digest })).data },
  async advance(project: string, plan: string, session: string): Promise<ResearchPlan> { return (await apiClient.post(`${base(project)}/${encodeURIComponent(plan)}/advance`, { session_id: session })).data },
  async control(project: string, plan: string, action: 'pause' | 'resume' | 'cancel'): Promise<ResearchPlan> { return (await apiClient.post(`${base(project)}/${encodeURIComponent(plan)}/control`, { action })).data },
  async reconcile(project: string, plan: string): Promise<ResearchPlan> { return (await apiClient.post(`${base(project)}/${encodeURIComponent(plan)}/reconcile`)).data },
  async events(project: string, plan: string): Promise<PlanEvent[]> { return (await apiClient.get(`${base(project)}/${encodeURIComponent(plan)}/events`)).data },
}
