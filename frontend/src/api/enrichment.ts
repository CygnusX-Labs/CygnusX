import apiClient from '@/api/client'
import type { EnrichmentResult, SpeciesOption } from '@/types/enrichment'

/**
 * 获取 YAML 中 enabled=true 的物种列表
 */
export async function fetchSpeciesOptions(): Promise<SpeciesOption[]> {
  const { data } = await apiClient.get<{ data: SpeciesOption[] }>('/enrichment/species')
  return data.data
}

/**
 * 提交富集分析任务
 */
export async function submitEnrichment(payload: FormData): Promise<EnrichmentResult> {
  const { data } = await apiClient.post<EnrichmentResult>('/enrichment/submit', payload, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return data
}
