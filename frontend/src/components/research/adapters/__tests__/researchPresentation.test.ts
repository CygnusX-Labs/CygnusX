import { describe, expect, it } from 'vitest'
import type { ResearchMessage } from '@/api/researchAgent'
import { applyResearchEvent, consumeResearchStream, mergeCards, mergeToolFrames, researchMessageView, safeSourceUrl } from '../researchPresentation'
function message(): ResearchMessage {
  return { message_id: 'a', role: 'assistant', content: '', status: 'streaming', metadata_json: {} } as ResearchMessage
}
describe('original research presentation protocol', () => {
  it('retains card metadata across instant events, terminal snapshots and history restoration', () => {
    const row = message()
    const card = { accession: 'GSE123', title: 'Study', meta: { organism: 'Human', url_geo: 'https://www.ncbi.nlm.nih.gov/geo/' } }
    applyResearchEvent(row, { event: 'cards', cards: [card] })
    applyResearchEvent(row, { event: 'end', cards: [{ ...card, meta: { samples: 12 } }] })
    const restored = JSON.parse(JSON.stringify(row)) as ResearchMessage
    expect(researchMessageView(restored)).toEqual(researchMessageView(row))
    expect(researchMessageView(row).cards?.[0].meta).toMatchObject({ organism: 'Human', samples: '12' })
    expect(mergeCards([card], [card])).toHaveLength(1)
  })
  it('folds running/completed frames while retaining subsequent calls', () => {
    expect(mergeToolFrames([], [{ name: 'geo', status: 'running' }, { name: 'geo', status: 'done', ms: 2 }, { name: 'geo', status: 'running' }, { name: 'geo', status: 'error' }])).toEqual([
      { name: 'geo', status: 'done', ms: 2 }, { name: 'geo', status: 'error' },
    ])
  })
  it('rejects unsafe source links and invalid command accessions without changing stored payloads', () => {
    for (const url of ['javascript:alert(1)', 'data:text/html,a', '//example.org', 'https://u:p@example.org', 'https://www.ncbi.nlm.nih.gov.evil.test/data', 'https://127.0.0.1/data']) expect(safeSourceUrl(url)).toBe('')
    const row = message()
    applyResearchEvent(row, { event: 'cards', cards: [{ accession: 'GSE1', meta: { url_geo: 'javascript:alert(1)' } }] })
    applyResearchEvent(row, { event: 'polariseq', accession: 'PRJNA1; rm -rf /' })
    expect(researchMessageView(row).cards?.[0].meta.url_geo).toBe('')
    expect(researchMessageView(row).boost?.accession).toBeNull()
    expect(JSON.stringify(row.metadata_json)).toContain('javascript:alert(1)')
  })
  it('decodes split UTF-8, CRLF, multi-line data and an unterminated final frame', async () => {
    const data = new TextEncoder().encode(': heartbeat\r\ndata: {"delta":\r\ndata: "寻宝鼠"}\r\n\r\ndata: {"event":"end"}')
    const row = message()
    const body = new ReadableStream<Uint8Array>({ start(controller) { for (const byte of data) controller.enqueue(Uint8Array.of(byte)); controller.close() } })
    expect(await consumeResearchStream(body, event => applyResearchEvent(row, event))).toEqual({ ended: true, lastEventId: 0 })
    expect(row.content).toBe('寻宝鼠')
    expect(row.status).toBe('complete')
  })
  it('does not treat EOF or an unqualified DONE marker as a successful reply', async () => {
    const row = message()
    const body = new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(new TextEncoder().encode('data: {"delta":"partial"}\n\ndata: [DONE]\n\n')); controller.close() } })
    expect(await consumeResearchStream(body, event => applyResearchEvent(row, event))).toEqual({ ended: false, lastEventId: 0 })
    expect(row.content).toBe('partial')
  })
  it('skips frames already covered by the resume cursor', async () => {
    const seen: unknown[] = []
    const data = new TextEncoder().encode('id: 4\ndata: {"delta":"old"}\n\nid: 5\ndata: {"delta":"new"}\n\n')
    const body = new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(data); controller.close() } })
    expect(await consumeResearchStream(body, event => seen.push(event), 4)).toEqual({ ended: false, lastEventId: 5 })
    expect(seen).toEqual([{ delta: 'new' }])
  })
})
