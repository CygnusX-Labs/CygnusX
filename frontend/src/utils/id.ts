/**
 * Generate a request-local identifier in browsers that do not expose
 * crypto.randomUUID (for example, older WebViews or non-secure contexts).
 */
export function generateId(): string {
  const cryptoApi = globalThis.crypto
  if (typeof cryptoApi?.randomUUID === 'function') return cryptoApi.randomUUID()

  if (typeof cryptoApi?.getRandomValues === 'function') {
    const bytes = new Uint8Array(16)
    cryptoApi.getRandomValues(bytes)
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }

  const fallback = `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`
    .padEnd(32, '0')
    .slice(-32)
  return `${fallback.slice(0, 8)}-${fallback.slice(8, 12)}-${fallback.slice(12, 16)}-${fallback.slice(16, 20)}-${fallback.slice(20)}`
}
