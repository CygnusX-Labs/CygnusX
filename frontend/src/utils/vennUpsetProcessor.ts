/**
 * VennUpset 核心计算（纯函数，无 Vue 依赖）。
 *
 * 列表文本解析（trim / 去空行 / 去重 / 大小写规范化）
 * → 计算所有非空交集区域（独占区域），供韦恩图与 UpSet 图使用。
 */

export interface NamedSet {
  name: string
  /** 去重后的元素（保留首次出现的原始写法） */
  items: string[]
}

export interface Region {
  /** 成员集合下标（升序），如 [0,2] 表示第 1、3 个集合的交集 */
  indices: number[]
  /** indices 以逗号连接的唯一键，如 "0,2" */
  key: string
  /** 恰好属于这些集合（且不属于其他任何集合）的元素 */
  elements: string[]
}

export interface ParsedList {
  /** 去重后的元素 */
  items: string[]
  /** 解析到的原始条目数（含重复与空行之前的有效 token 数） */
  rawCount: number
  /** 被去重掉的条目数 */
  dupCount: number
}

/** 支持换行 / 逗号 / 分号 / Tab / 空格混合分隔。 */
const SPLIT_RE = /[\n,;\t ]+/

/**
 * 解析列表文本：按分隔符切分、trim、去空、去重。
 * caseSensitive=false 时按小写归一化判重，保留首次出现的原始写法。
 */
export function parseListText(text: string, caseSensitive: boolean): ParsedList {
  const seen = new Set<string>()
  const items: string[] = []
  let rawCount = 0
  for (const token of text.split(SPLIT_RE)) {
    const t = token.trim()
    if (!t) continue
    rawCount++
    const k = caseSensitive ? t : t.toLowerCase()
    if (seen.has(k)) continue
    seen.add(k)
    items.push(t)
  }
  return { items, rawCount, dupCount: rawCount - items.length }
}

/**
 * 计算所有非空交集区域（独占区域）。
 * 对每个元素统计其出现在哪些集合中，按成员掩码分组。
 * 返回按「交集阶数升序、元素数降序」排序的区域列表。
 */
export function computeRegions(sets: NamedSet[], caseSensitive: boolean): Region[] {
  const norm = (s: string) => (caseSensitive ? s : s.toLowerCase())
  const member = new Map<string, { display: string; mask: boolean[] }>()
  sets.forEach((set, i) => {
    for (const item of set.items) {
      const k = norm(item)
      let e = member.get(k)
      if (!e) {
        e = { display: item, mask: sets.map(() => false) }
        member.set(k, e)
      }
      e.mask[i] = true
    }
  })
  const regionMap = new Map<string, Region>()
  for (const { display, mask } of member.values()) {
    const indices: number[] = []
    mask.forEach((m, i) => {
      if (m) indices.push(i)
    })
    if (!indices.length) continue
    const key = indices.join(',')
    let r = regionMap.get(key)
    if (!r) {
      r = { indices, key, elements: [] }
      regionMap.set(key, r)
    }
    r.elements.push(display)
  }
  const regions = [...regionMap.values()]
  for (const r of regions) r.elements.sort((a, b) => a.localeCompare(b))
  regions.sort(
    (a, b) => a.indices.length - b.indices.length || b.elements.length - a.elements.length,
  )
  return regions
}

/** 区域的可读描述，如 "A ∩ B"。 */
export function describeRegion(indices: number[], names: string[]): string {
  return indices.map((i) => names[i] ?? `集合${i + 1}`).join(' ∩ ')
}

/** 示例数据：三组有交集的常见基因列表。 */
export function genSampleLists(): { name: string; text: string }[] {
  return [
    {
      name: 'RNA-seq 差异基因',
      text: [
        'TP53', 'BRCA1', 'EGFR', 'MYC', 'KRAS', 'PTEN', 'AKT1', 'CDKN1A',
        'MDM2', 'RB1', 'VEGFA', 'BCL2', 'BAX', 'CASP3', 'FOS', 'JUN',
        'STAT3', 'NFKB1', 'IL6', 'TNF', 'GAPDH', 'ACTB', 'MMP9', 'CXCL8',
      ].join('\n'),
    },
    {
      name: '蛋白质组上调',
      text: [
        'TP53', 'EGFR', 'MYC', 'AKT1', 'BCL2', 'CASP3', 'STAT3', 'MMP9',
        'HSP90AA1', 'HSPA5', 'VIM', 'ACTB', 'TUBB', 'ENO1', 'PKM', 'LDHA',
        'SOD1', 'CAT', 'GAPDH', 'CXCL8',
      ].join('\n'),
    },
    {
      name: 'GWAS 候选基因',
      text: [
        'BRCA1', 'BRCA2', 'TP53', 'KRAS', 'PTEN', 'APOE', 'TCF7L2', 'FTO',
        'IL6', 'TNF', 'NFKB1', 'MTHFR', 'VEGFA', 'CDKN2A', 'PALB2', 'ATM',
      ].join('\n'),
    },
  ]
}
