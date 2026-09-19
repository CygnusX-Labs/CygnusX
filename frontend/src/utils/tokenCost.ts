/**
 * Token 用量展示与计费：单价在设置页配置（localStorage 持久化），
 * 工作台顶栏按会话汇总消息 tokens 后换算费用。
 */

export interface TokenPricing {
  /** 输入单价：元 / M tokens */
  inputPerM: number
  /** 输出单价：元 / M tokens */
  outputPerM: number
}

const STORAGE_KEY = 'ai_token_pricing'

export const DEFAULT_TOKEN_PRICING: TokenPricing = { inputPerM: 1, outputPerM: 2 }

export function loadTokenPricing(): TokenPricing {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_TOKEN_PRICING }
    const parsed = JSON.parse(raw)
    return {
      inputPerM: Number.isFinite(parsed.inputPerM) ? Math.max(0, parsed.inputPerM) : DEFAULT_TOKEN_PRICING.inputPerM,
      outputPerM: Number.isFinite(parsed.outputPerM) ? Math.max(0, parsed.outputPerM) : DEFAULT_TOKEN_PRICING.outputPerM,
    }
  } catch {
    return { ...DEFAULT_TOKEN_PRICING }
  }
}

export function saveTokenPricing(pricing: TokenPricing): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(pricing))
}

/** 按 M 单位格式化 token 数：≥1M 显示 "x.xxM"，不足显示 K，便于顶栏紧凑展示 */
export function formatTokensInM(tokens: number): string {
  if (!Number.isFinite(tokens) || tokens <= 0) return '0'
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(2)}M`
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}K`
  return String(Math.round(tokens))
}

export interface SessionUsage {
  input: number
  output: number
  total: number
  cost: number
}

/** 模型级单价（AI 配置中心配置）覆盖全局单价；未配置字段回退到全局值 */
export function resolvePricing(
  globalPricing: TokenPricing,
  modelPrice?: { input?: number | null; output?: number | null } | null,
): TokenPricing {
  return {
    inputPerM: modelPrice?.input ?? globalPricing.inputPerM,
    outputPerM: modelPrice?.output ?? globalPricing.outputPerM,
  }
}

export interface HasTokens {
  tokens?: { input?: number; output?: number; total?: number }
}

/** 汇总会话全部消息的 token 消耗，并按定价换算费用 */
export function summarizeUsage(messages: HasTokens[], pricing: TokenPricing): SessionUsage {
  let input = 0
  let output = 0
  let total = 0
  for (const message of messages) {
    const tokens = message.tokens
    if (!tokens) continue
    input += tokens.input || 0
    output += tokens.output || 0
    total += tokens.total ?? (tokens.input || 0) + (tokens.output || 0)
  }
  const cost = (input / 1_000_000) * pricing.inputPerM + (output / 1_000_000) * pricing.outputPerM
  return { input, output, total, cost }
}
