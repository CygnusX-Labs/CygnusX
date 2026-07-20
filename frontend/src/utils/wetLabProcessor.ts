/**
 * 湿实验计算器核心算法（纯函数，无 Vue 依赖）。
 *
 * 覆盖 4 个子计算器：
 * 1. 母液稀释 C1V1 = C2V2
 * 2. qPCR 相对表达 2^-ΔΔCt
 * 3. 摩尔浓度 / 质量 / 体积换算
 * 4. 核酸浓度 ng/µL ↔ nM 换算
 */

// ---------------------------------------------------------------------------
// 通用格式化
// ---------------------------------------------------------------------------

/**
 * 数值格式化：普通范围保留 significantDigits 位有效数字；
 * 过大 / 过小（>=1e6 或 <1e-3）用科学计数法。非法值返回 '—'。
 */
export function formatNum(n: number | null | undefined, significantDigits = 4): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  if (n === 0) return '0'
  const abs = Math.abs(n)
  if (abs >= 1e6 || abs < 1e-3) {
    return n.toExponential(3)
  }
  return String(+n.toPrecision(significantDigits))
}

/** 解析用户输入为有限正数；非法返回 null。 */
export function parsePositive(raw: string | number | null | undefined, allowZero = false): number | null {
  if (raw === null || raw === undefined || raw === '') return null
  const v = typeof raw === 'number' ? raw : Number(String(raw).trim())
  if (!Number.isFinite(v)) return null
  if (allowZero ? v < 0 : v <= 0) return null
  return v
}

// ---------------------------------------------------------------------------
// 子计算器 1：母液稀释 C1V1 = C2V2
// ---------------------------------------------------------------------------

/** 浓度单位（统一折算为 µM；ng/µL 按 1 µg/mL ≈ 与 nM 无关，仅做同单位换算） */
export const DIL_CONC_UNITS = ['µM', 'nM', 'ng/µL'] as const
export type DilConcUnit = (typeof DIL_CONC_UNITS)[number]

/** 体积单位（统一折算为 µL） */
export const DIL_VOL_UNITS = ['µL', 'mL'] as const
export type DilVolUnit = (typeof DIL_VOL_UNITS)[number]

function concToMicroM(v: number, unit: DilConcUnit): number {
  if (unit === 'nM') return v / 1000
  return v // µM 与 ng/µL 视作“同单位”基准，仅同单位间计算
}

function volToMicroL(v: number, unit: DilVolUnit): number {
  return unit === 'mL' ? v * 1000 : v
}

export interface DilutionInput {
  c1: number | null
  c2: number | null
  v2: number | null
  concUnit: DilConcUnit
  volUnit: DilVolUnit
}

export interface DilutionResult {
  valid: boolean
  error: string | null
  /** 需取母液体积（µL） */
  v1uL: number
  /** 需加溶剂体积（µL） */
  solventuL: number
  /** 母液占终体积比例 % */
  ratio: number
}

/** C1V1 = C2V2 求解：V1 = C2·V2 / C1，加水量 = V2 - V1。 */
export function solveDilution(input: DilutionInput): DilutionResult {
  const empty: DilutionResult = { valid: false, error: null, v1uL: 0, solventuL: 0, ratio: 0 }
  const { c1, c2, v2, concUnit, volUnit } = input
  if (c1 === null || c2 === null || v2 === null) return empty
  if (c1 <= 0 || c2 <= 0 || v2 <= 0) return { ...empty, error: '所有数值必须为正数' }
  if (concToMicroM(c2, concUnit) > concToMicroM(c1, concUnit)) {
    return { ...empty, error: '目标浓度 C2 不能大于母液浓度 C1' }
  }
  const v2uL = volToMicroL(v2, volUnit)
  const v1uL = (concToMicroM(c2, concUnit) * v2uL) / concToMicroM(c1, concUnit)
  return {
    valid: true,
    error: null,
    v1uL,
    solventuL: v2uL - v1uL,
    ratio: (v1uL / v2uL) * 100,
  }
}

// ---------------------------------------------------------------------------
// 子计算器 2：qPCR 相对表达 2^-ΔΔCt
// ---------------------------------------------------------------------------

/** 原始 Ct 行：样本名 | 分组 | 目的基因 Ct | 内参基因 Ct（Tab 分隔，支持 Excel 粘贴） */
export interface CtRawRow {
  sample: string
  group: string
  targetCt: number
  refCt: number
}

export interface CtParseResult {
  rows: CtRawRow[]
  /** 被跳过的行号（1-based，含表头/格式错误行） */
  skipped: number[]
  groups: string[]
}

/**
 * 解析 Ct 表格文本（Tab 分隔，兼容逗号/多空格；自动跳过表头行）。
 */
export function parseCtTable(text: string): CtParseResult {
  const rows: CtRawRow[] = []
  const skipped: number[] = []
  const lines = text.split('\n')
  lines.forEach((line, idx) => {
    const trimmed = line.trim()
    if (!trimmed) return
    const cols = trimmed.includes('\t') ? trimmed.split('\t') : trimmed.split(/[,;]|\s{2,}/)
    if (cols.length < 4) {
      skipped.push(idx + 1)
      return
    }
    const target = Number(cols[2].trim())
    const ref = Number(cols[3].trim())
    if (!Number.isFinite(target) || !Number.isFinite(ref)) {
      skipped.push(idx + 1) // 表头或非数值行
      return
    }
    rows.push({
      sample: cols[0].trim() || `样本${rows.length + 1}`,
      group: cols[1].trim() || '未分组',
      targetCt: target,
      refCt: ref,
    })
  })
  return { rows, skipped, groups: [...new Set(rows.map((r) => r.group))] }
}

export interface QpcrDetailRow extends CtRawRow {
  key: string
  dCt: number
  ddCt: number
  /** 2^-ΔΔCt 相对表达量 */
  relExp: number
}

export interface QpcrGroupStat {
  group: string
  n: number
  mean: number
  sd: number
  sem: number
}

export interface QpcrResult {
  details: QpcrDetailRow[]
  groupStats: QpcrGroupStat[]
  controlGroup: string
  controlMeanDCt: number
}

/**
 * 2^-ΔΔCt 计算：
 * ΔCt = 目的基因 Ct - 内参 Ct（同一行）
 * 对照组 ΔCt 均值 → ΔΔCt = ΔCt - 对照均值 → 相对表达 = 2^-ΔΔCt
 */
export function computeQpcr(rows: CtRawRow[], controlGroup: string): QpcrResult | { error: string } {
  const controlRows = rows.filter((r) => r.group === controlGroup)
  if (!rows.length) return { error: '没有有效数据行' }
  if (!controlRows.length) return { error: `对照组「${controlGroup}」不存在` }
  const controlMeanDCt =
    controlRows.reduce((s, r) => s + (r.targetCt - r.refCt), 0) / controlRows.length

  const details: QpcrDetailRow[] = rows.map((r, i) => {
    const dCt = r.targetCt - r.refCt
    const ddCt = dCt - controlMeanDCt
    return {
      ...r,
      key: `${r.sample}-${i}`,
      dCt,
      ddCt,
      relExp: Math.pow(2, -ddCt),
    }
  })

  const byGroup = new Map<string, number[]>()
  details.forEach((d) => {
    const arr = byGroup.get(d.group) ?? []
    arr.push(d.relExp)
    byGroup.set(d.group, arr)
  })
  const groupStats: QpcrGroupStat[] = [...byGroup.entries()].map(([group, vals]) => {
    const n = vals.length
    const mean = vals.reduce((s, v) => s + v, 0) / n
    const sd =
      n > 1 ? Math.sqrt(vals.reduce((s, v) => s + (v - mean) ** 2, 0) / (n - 1)) : 0
    return { group, n, mean, sd, sem: n > 1 ? sd / Math.sqrt(n) : 0 }
  })
  // 对照组排最前
  groupStats.sort((a, b) => (a.group === controlGroup ? -1 : b.group === controlGroup ? 1 : 0))
  return { details, groupStats, controlGroup, controlMeanDCt }
}

/** qPCR 示例数据（3 样本 × 2 组，内参 ACTB，含技术重复）。 */
export function genSampleCtData(): string {
  return [
    '样本名\t分组\t目的基因Ct\t内参Ct',
    'Ctrl-1\t对照组\t22.35\t17.12',
    'Ctrl-2\t对照组\t22.48\t17.25',
    'Ctrl-3\t对照组\t22.19\t17.08',
    'Treat-1\t处理组\t19.82\t17.31',
    'Treat-2\t处理组\t20.05\t17.44',
    'Treat-3\t处理组\t19.67\t17.19',
  ].join('\n')
}

// ---------------------------------------------------------------------------
// 子计算器 3：摩尔浓度 / 质量 / 体积换算
// ---------------------------------------------------------------------------

export type MolarTarget = 'mass' | 'volume' | 'conc' | 'mw'

/** 质量单位折算到 g */
export const MASS_FACTORS: Record<string, number> = { g: 1, mg: 1e-3, 'µg': 1e-6 }
/** 体积单位折算到 L */
export const VOL_FACTORS: Record<string, number> = { L: 1, mL: 1e-3, 'µL': 1e-6 }
/** 浓度单位折算到 mol/L */
export const CONC_FACTORS: Record<string, number> = { M: 1, mM: 1e-3, 'µM': 1e-6, nM: 1e-9 }

export interface MolarInput {
  target: MolarTarget
  /** 分子量 g/mol */
  mw: number | null
  mwUnit?: string
  /** 质量（单位见 massUnit） */
  mass: number | null
  massUnit: string
  /** 体积 */
  volume: number | null
  volUnit: string
  /** 浓度 */
  conc: number | null
  concUnit: string
}

export interface MolarResult {
  valid: boolean
  error: string | null
  /** 求解结果（SI 基准：g / L / mol/L / g/mol） */
  value: number
  label: string
  unit: string
}

/**
 * 四项换算：n = m/MW，c = n/V。
 * 用户单选求解目标，其余三项为输入。
 */
export function solveMolar(input: MolarInput): MolarResult {
  const { target, massUnit, volUnit, concUnit } = input
  const massG = input.mass === null ? null : input.mass * (MASS_FACTORS[massUnit] ?? 1)
  const volL = input.volume === null ? null : input.volume * (VOL_FACTORS[volUnit] ?? 1)
  const concM = input.conc === null ? null : input.conc * (CONC_FACTORS[concUnit] ?? 1)
  const mw = input.mw

  const need = (v: number | null, name: string): string | null =>
    v === null ? `请输入${name}` : v <= 0 ? `${name}必须为正数` : null

  let err: string | null = null
  let value = NaN
  let label = ''
  let unit = ''

  if (target === 'mass') {
    err = need(mw, '分子量') ?? need(volL, '体积') ?? need(concM, '浓度')
    if (!err) {
      value = concM! * volL! * mw! // g
      label = '所需质量'
      unit = 'g'
    }
  } else if (target === 'volume') {
    err = need(mw, '分子量') ?? need(massG, '质量') ?? need(concM, '浓度')
    if (!err) {
      value = massG! / mw! / concM! // L
      label = '所需体积'
      unit = 'L'
    }
  } else if (target === 'conc') {
    err = need(mw, '分子量') ?? need(massG, '质量') ?? need(volL, '体积')
    if (!err) {
      value = massG! / mw! / volL! // mol/L
      label = '浓度'
      unit = 'mol/L'
    }
  } else {
    err = need(massG, '质量') ?? need(volL, '体积') ?? need(concM, '浓度')
    if (!err) {
      value = massG! / (concM! * volL!) // g/mol
      label = '分子量'
      unit = 'g/mol'
    }
  }
  return { valid: err === null, error: err, value, label, unit }
}

/** 把 SI 结果换算成友好单位（质量 g/mg/µg，体积 L/mL/µL，浓度 M/mM/µM/nM）。 */
export function friendlySI(value: number, kind: 'mass' | 'volume' | 'conc' | 'mw'): string {
  if (!Number.isFinite(value)) return '—'
  if (kind === 'mw') return `${formatNum(value)} g/mol`
  if (kind === 'mass') {
    if (value >= 1) return `${formatNum(value)} g`
    if (value >= 1e-3) return `${formatNum(value * 1e3)} mg`
    return `${formatNum(value * 1e6)} µg`
  }
  if (kind === 'volume') {
    if (value >= 1) return `${formatNum(value)} L`
    if (value >= 1e-3) return `${formatNum(value * 1e3)} mL`
    return `${formatNum(value * 1e6)} µL`
  }
  if (value >= 1) return `${formatNum(value)} M`
  if (value >= 1e-3) return `${formatNum(value * 1e3)} mM`
  if (value >= 1e-6) return `${formatNum(value * 1e6)} µM`
  return `${formatNum(value * 1e9)} nM`
}

// ---------------------------------------------------------------------------
// 子计算器 4：核酸浓度 ng/µL ↔ nM
// ---------------------------------------------------------------------------

export type NucleicType = 'dsDNA' | 'ssDNA' | 'ssRNA'

/** 每 bp/nt 平均分子量（g/mol） */
export const NUC_MW_PER_NT: Record<NucleicType, number> = {
  dsDNA: 660,
  ssDNA: 330,
  ssRNA: 340,
}

export interface NucleicResult {
  valid: boolean
  error: string | null
  ngPerUl: number
  nM: number
  /** 分子量 g/mol */
  mw: number
}

/** ng/µL → nM。 */
export function ngUlToNm(ngPerUl: number, length: number, type: NucleicType): NucleicResult {
  if (ngPerUl <= 0 || length <= 0) {
    return { valid: false, error: '浓度与长度必须为正数', ngPerUl: 0, nM: 0, mw: 0 }
  }
  const mw = length * NUC_MW_PER_NT[type]
  // ng/µL = g/m³ = 1e-3 g/L；nM = (g/L) / MW * 1e9
  const nM = ((ngPerUl * 1e-3) / mw) * 1e9
  return { valid: true, error: null, ngPerUl, nM, mw }
}

/** nM → ng/µL。 */
export function nmToNgUl(nM: number, length: number, type: NucleicType): NucleicResult {
  if (nM <= 0 || length <= 0) {
    return { valid: false, error: '浓度与长度必须为正数', ngPerUl: 0, nM: 0, mw: 0 }
  }
  const mw = length * NUC_MW_PER_NT[type]
  const ngPerUl = ((nM * 1e-9) * mw) / 1e-3
  return { valid: true, error: null, ngPerUl, nM, mw }
}

// ---------------------------------------------------------------------------
// CSV 导出辅助
// ---------------------------------------------------------------------------

/** 明细行数组 → CSV 文本（带 BOM，Excel 友好）。 */
export function toCsv(headers: string[], rows: (string | number)[][]): string {
  const esc = (v: string | number) => {
    const s = String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return '﻿' + [headers, ...rows].map((r) => r.map(esc).join(',')).join('\n')
}
