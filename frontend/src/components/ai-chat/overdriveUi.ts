import type { ChatMessage, OverdriveProgress } from './types'

export function conversationMessagesWithoutProgress(messages: ChatMessage[]): ChatMessage[] {
  return messages.filter((item) => !item.overdriveProgress)
}

export function activeOverdriveProgress(messages: ChatMessage[]): OverdriveProgress | null {
  const progress = [...messages].reverse().find((item) => item.overdriveProgress)?.overdriveProgress
  return progress && progress.phase !== 'completed' ? progress : null
}
