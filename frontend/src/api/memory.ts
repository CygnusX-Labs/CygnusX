import apiClient from './client'
import type { MemoryBlock, MemoryForgetContext, MemoryForgetResponse, MemoryResidualHint } from '@/types/memory'

/** Use the selected block's partition and version; never infer it from the active chat. */
export async function updateMemoryBlock(block: MemoryBlock, content: string): Promise<MemoryBlock> {
  const { data } = await apiClient.patch<MemoryBlock>(`/users/me/memory-blocks/${block.block_name}`, {
    content,
    expected_version: block.version,
  }, { params: { agent_id: block.agent_id, project_id: block.project_id || undefined } })
  return data
}

export async function forgetMemory(
  id: number, context: MemoryForgetContext = {},
): Promise<MemoryForgetResponse> {
  const { data } = await apiClient.post<MemoryForgetResponse>(`/users/me/memories/${id}/forget`, null, { params: context })
  return data
}

/** Client-reported clicks only; this request never edits or archives any memory. */
export async function recordMemoryResidualAction(
  sourceId: string, hint: MemoryResidualHint,
): Promise<void> {
  await apiClient.post('/users/me/memory-residual-actions', {
    source_id: Number(sourceId), target_id: hint.id, kind: hint.kind,
    action: hint.kind === 'block' ? 'open_editor' : 'archive',
  })
}
