/** Safe user-facing failure categories for project research surfaces. */
export function projectRequestFailure(exc: unknown, subject: string): string {
  const response = (exc as { response?: { status?: number; data?: { code?: string; error?: { code?: string } } } })?.response
  const code = response?.data?.code ?? response?.data?.error?.code
  if (code === 'FEATURE_DISABLED') return `服务未启用：${subject}尚未开放。`
  if (response?.status === 401 || response?.status === 403) return `当前用户无权限：无法访问${subject}，请核对登录与项目授权。`
  return `请求失败：${subject}暂不可用，请重试。`
}
