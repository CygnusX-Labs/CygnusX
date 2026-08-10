import { defineStore } from 'pinia'
import { ref } from 'vue'
import { agentTeamsApi, type AgentTeamsCase } from '@/api/agentTeams'

export const useAgentTeamsStore = defineStore('agentTeams', () => {
  const cases = ref<Record<string, AgentTeamsCase>>({})

  async function refreshCase(caseId: string): Promise<AgentTeamsCase> {
    const value = await agentTeamsApi.getCase(caseId)
    cases.value = { ...cases.value, [caseId]: value }
    return value
  }

  async function submitCase(caseId: string, payload: { task_name: string }) {
    return agentTeamsApi.submitCase(caseId, payload)
  }

  async function rejectCase(caseId: string, payload: { reason: string }): Promise<AgentTeamsCase> {
    const value = await agentTeamsApi.rejectCase(caseId, payload)
    cases.value = { ...cases.value, [caseId]: value }
    return value
  }

  return { cases, refreshCase, submitCase, rejectCase }
})
