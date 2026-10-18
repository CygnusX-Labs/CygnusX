import type { ResearchMessage } from '@/api/researchAgent'
import type { TreasureCard, TreasureMessage } from '@/types/treasureIsland'

type RecordValue = Record<string, unknown>
function record(value: unknown): RecordValue {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {}
}
function text(value: unknown): string { return typeof value === 'string' ? value : '' }
export function safeSourceUrl(value: unknown): string {
  if (typeof value !== 'string') return ''
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : ''
  } catch { return '' }
}
export function mergeCards(previous: unknown[], incoming: unknown[]): unknown[] {
  const merged = new Map<string, RecordValue>()
  for (const raw of [...previous, ...incoming]) {
    const card = record(raw)
    if (!Object.keys(card).length) continue
    const meta = record(card.meta)
    const key = [meta.source, meta.literature_source, card.accession || meta.doi || meta.pmid || card.title || JSON.stringify(card)].join(':')
    const old = merged.get(key)
    merged.set(key, { ...old, ...card, meta: { ...record(old?.meta), ...meta } })
  }
  return [...merged.values()]
}
function viewCard(raw: unknown): TreasureCard {
  const card = record(raw)
  const meta: Record<string, string> = {}
  for (const [key, value] of Object.entries(record(card.meta))) {
    if (key.startsWith('url_') || /(?:^|_)url$/.test(key)) meta[key] = safeSourceUrl(value)
    else if (value != null) meta[key] = typeof value === 'string' ? value : JSON.stringify(value)
  }
  return { tool: text(card.tool), accession: text(card.accession), title: text(card.title), summary: text(card.summary), meta }
}
/** Collapse the running/done frames for one call, retaining repeated completed calls. */
export function mergeToolFrames(previous: unknown[], incoming: unknown[]): RecordValue[] {
  const result: RecordValue[] = []
  for (const raw of [...previous, ...incoming]) {
    const tool = record(raw)
    const name = text(tool.name)
    if (!name) continue
    const status = tool.status || (tool.ok === false ? 'error' : 'done')
    const index = result.findIndex(item => item.name === name && item.status === 'running')
    const item = { ...tool, status }
    if (index >= 0) result[index] = { ...result[index], ...item }
    else result.push(item)
  }
  return result
}
/** The same projection is used for both restored and live platform messages. */
export function researchMessageView(message: ResearchMessage): TreasureMessage {
  const events = message.metadata_json?.events ?? {}
  const tools = mergeToolFrames([], events.tools ?? [])
  const liveTools = tools.map(tool => ({ name: text(tool.name), label: text(tool.label) || text(tool.name),
    status: (tool.status === 'running' ? 'running' : tool.status === 'error' ? 'error' : 'done') as 'running' | 'done' | 'error',
    ms: typeof tool.ms === 'number' ? tool.ms : undefined }))
  const rawGrounding = record(events.grounding)
  const grounding = events.grounding ? {
    unconfirmed: Array.isArray(rawGrounding.unconfirmed) ? rawGrounding.unconfirmed.flatMap(raw => {
      const item = record(raw); return typeof item.id === 'string' ? [{ id: item.id, status: text(item.status) || 'unverified' }] : []
    }) : [],
    confirmed: Array.isArray(rawGrounding.confirmed) ? rawGrounding.confirmed.filter((id): id is string => typeof id === 'string') : [],
  } : null
  return { id: message.message_id, role: message.role, content: message.content,
    cards: mergeCards([], events.cards ?? []).map(viewCard), liveTools,
    toolLogs: liveTools.filter(tool => tool.status !== 'running').map(tool => ({ name: tool.name, label: tool.label, ok: tool.status !== 'error', ms: tool.ms ?? 0 })),
    grounding, boost: events.polariseq ? { accession: /^PRJ(?:NA|EB|DB|CA)\d+$/i.test(events.polariseq.accession ?? '') ? events.polariseq.accession : null } : null, streaming: message.status === 'streaming',
    error: events.error || (['error', 'cancel', 'cancelled', 'interrupted'].includes(message.status) ? '本次回复未完整结束，已保留收到的内容。' : null),
  }
}
/** Store lossless source payloads; display-only sanitization happens above. */
export function applyResearchEvent(message: ResearchMessage, event: RecordValue): void {
  const events = message.metadata_json.events ??= {}
  if (typeof event.delta === 'string') message.content += event.delta
  if (Array.isArray(event.cards)) events.cards = mergeCards(events.cards ?? [], event.cards)
  if (event.event === 'tool') events.tools = mergeToolFrames(events.tools ?? [], [event])
  if (event.event === 'end' && Array.isArray(event.tools) && event.tools.length) events.tools = mergeToolFrames([], event.tools)
  if (event.event === 'grounding') events.grounding = event
  if (event.event === 'polariseq') events.polariseq = { accession: typeof event.accession === 'string' ? event.accession : null }
  if (event.event === 'cancel') message.status = 'cancelled'
  if (event.event === 'end') message.status = 'complete'
}
/** Streaming UTF-8/SSE framing, including CRLF, multi-line data and final buffered frame. */
export async function consumeResearchStream(body: ReadableStream<Uint8Array>, onEvent: (event: RecordValue) => void): Promise<boolean> {
  const reader = body.getReader(); const decoder = new TextDecoder()
  let buffer = ''; let payload: string[] = []; let ended = false
  function line(value: string) {
    if (!value) {
      if (!payload.length) return
      const raw = payload.join('\n'); payload = []
      if (raw === '[DONE]') return
      const event = record(JSON.parse(raw))
      onEvent(event)
      if (['end', 'cancel', 'error'].includes(text(event.event)) || event.error) ended = true
    } else if (value.startsWith('data:')) payload.push(value.slice(5).replace(/^ /, ''))
  }
  try {
    while (true) {
      const chunk = await reader.read()
      buffer += decoder.decode(chunk.value, { stream: !chunk.done })
      const lines = buffer.split(/\r?\n/); buffer = lines.pop() ?? ''
      for (const value of lines) line(value)
      if (chunk.done) { if (buffer) line(buffer); line(''); break }
    }
  } finally { reader.releaseLock() }
  return ended
}
