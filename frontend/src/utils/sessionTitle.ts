export const SESSION_TITLE_REFRESH_LIMIT = 12

/** Generate on the first completed turn, then refresh every third user turn through turn 12. */
export function shouldGenerateSessionTitle(userMessageCount: number, titleLocked = false): boolean {
  if (titleLocked || userMessageCount < 1 || userMessageCount > SESSION_TITLE_REFRESH_LIMIT) return false
  return userMessageCount === 1 || userMessageCount % 3 === 0
}
