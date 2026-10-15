/**
 * Normalize backend progress values to a bounded integer percentage.
 * Backends currently emit both 0–1 fractions and 0–100 percentages.
 */
export function normalizeProgress(value: unknown): number {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return 0

  const percentage = numericValue > 1 ? numericValue : numericValue * 100
  return Math.round(Math.min(100, Math.max(0, percentage)))
}
