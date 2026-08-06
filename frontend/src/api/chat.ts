import apiClient from './client'

export interface OverdriveApprovalRecord {
  approval_id: string
  tool_name: string
  arguments: Record<string, unknown>
  status: 'pending' | 'executing' | 'completed' | 'rejected' | 'failed'
  result?: Record<string, unknown>
  error?: string
  reason?: string
}

export const chatApi = {
  async controlOverdrive(
    sessionId: string,
    action: 'pause' | 'resume' | 'skip' | 'terminate' | 'directive',
    options: { taskId?: string; directive?: string } = {},
  ): Promise<Record<string, unknown>> {
    const response = await apiClient.post(`/chat/sessions/${sessionId}/overdrive/control`, {
      action,
      task_id: options.taskId,
      directive: options.directive,
    })
    return response.data
  },
  async approveOverdriveApproval(sessionId: string, approvalId: string): Promise<OverdriveApprovalRecord> {
    const response = await apiClient.post(
      `/chat/sessions/${sessionId}/overdrive-approvals/${approvalId}/approve`,
    )
    return response.data
  },
  async rejectOverdriveApproval(
    sessionId: string,
    approvalId: string,
    reason?: string,
  ): Promise<OverdriveApprovalRecord> {
    const response = await apiClient.post(
      `/chat/sessions/${sessionId}/overdrive-approvals/${approvalId}/reject`,
      { reason },
    )
    return response.data
  },
  async submitMessageFeedback(
    sessionId: string,
    messageId: string,
    rating: 'like' | 'dislike' | 'none',
    comment?: string,
  ): Promise<{ feedback: { rating: string } | null }> {
    const response = await apiClient.put(
      `/chat/sessions/${sessionId}/messages/${messageId}/feedback`,
      { rating, comment },
    )
    return response.data
  },
  async getSessionFeedbacks(sessionId: string): Promise<Record<string, 'like' | 'dislike'>> {
    const response = await apiClient.get(`/chat/sessions/${sessionId}/feedbacks`)
    return response.data
  },
}
