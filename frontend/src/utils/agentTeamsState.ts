import type { AgentTeamsEvent } from '@/api/agentTeams'

/** Merge Bridge event pages without losing history or duplicating cursor replays. */
export function mergeAgentTeamsEvents(
  current: AgentTeamsEvent[],
  incoming: AgentTeamsEvent[],
): AgentTeamsEvent[] {
  const incomingById = new Map(incoming.map((event) => [event.event_id, event]))
  const merged = current.map((event) => incomingById.get(event.event_id) ?? event)
  const knownIds = new Set(current.map((event) => event.event_id))
  return [...merged, ...incoming.filter((event) => !knownIds.has(event.event_id))]
}

/** Background polling must not refresh a hidden browser tab. */
export function shouldPollAgentTeamsCase(visibilityState: DocumentVisibilityState): boolean {
  return visibilityState === 'visible'
}
