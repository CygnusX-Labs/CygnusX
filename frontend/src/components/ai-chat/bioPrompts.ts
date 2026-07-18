import type { BioPromptTemplate } from './types'

export const BIO_PROMPTS: BioPromptTemplate[] = []

interface PromptPayload {
  templates?: Array<{
    id: string
    title: string
    description?: string
    category?: string
    prompt: string
  }>
}

export async function loadBioPrompts(): Promise<BioPromptTemplate[]> {
  const response = await fetch('/api/v1/prompts/user-templates/bio')
  if (!response.ok) return []
  const payload = await response.json() as PromptPayload
  return (payload.templates || []).map((item) => ({
    id: item.id,
    title: item.title,
    description: item.description || '',
    category: item.category || '生信分析',
    content: item.prompt,
  }))
}
