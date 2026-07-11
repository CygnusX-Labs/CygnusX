/**
 * 系统发育树前端处理与渲染封装
 * - 轻量 Newick 解析与统计（不依赖可视化库）
 * - phylotree.js 动态加载渲染器封装，避免进入页面时拖慢首屏
 */

import type { TreeStatistics, VizConfig } from '@/types/phylo'

// phylotree.js 动态导入，不参与页面首屏 chunk
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let phylotreeModule: any = null

export async function loadPhylotreeModule(): Promise<unknown> {
  if (phylotreeModule) return phylotreeModule
  phylotreeModule = await import('phylotree')
  return phylotreeModule
}

// ---------------------------------------------------------------------------
// 轻量 Newick 解析器（用于统计）
// ---------------------------------------------------------------------------

export interface NewickNode {
  name: string
  branch_length: number
  confidence?: number
  children: NewickNode[]
}

export function parseNewick(newickStr: string): NewickNode {
  const tokens = tokenizeNewick(newickStr.trim())
  if (tokens.length < 2 || tokens[tokens.length - 1] !== ';') {
    throw new Error('Invalid Newick string')
  }
  const { node } = parseSubtree(tokens, 0)
  return node
}

function tokenizeNewick(s: string): string[] {
  const tokens: string[] = []
  let i = 0
  while (i < s.length) {
    const c = s[i]
    if (c === ' ' || c === '\t' || c === '\n' || c === '\r') {
      i++
      continue
    }
    if ('(),;:'.includes(c)) {
      tokens.push(c)
      i++
      continue
    }
    let token = ''
    while (i < s.length && !'(),;:\s'.includes(s[i])) {
      token += s[i]
      i++
    }
    if (token) tokens.push(token)
  }
  return tokens
}

function parseSubtree(tokens: string[], idx: number): { node: NewickNode; nextIdx: number } {
  let name = ''
  let branchLength = 0
  let confidence: number | undefined
  const children: NewickNode[] = []

  if (tokens[idx] === '(') {
    idx++ // skip '('
    while (true) {
      const child = parseSubtree(tokens, idx)
      children.push(child.node)
      idx = child.nextIdx
      if (tokens[idx] === ',') {
        idx++
        continue
      }
      if (tokens[idx] === ')') {
        idx++
        break
      }
      throw new Error(`Unexpected token in Newick: ${tokens[idx]}`)
    }
    // optional internal label / bootstrap
    if (idx < tokens.length && !'(),;:'.includes(tokens[idx])) {
      const raw = tokens[idx]
      const num = Number(raw)
      if (!Number.isNaN(num)) {
        confidence = num
      } else {
        name = raw
      }
      idx++
    }
  } else {
    name = tokens[idx]
    idx++
  }

  if (tokens[idx] === ':') {
    idx++
    branchLength = Number(tokens[idx])
    idx++
  }

  return { node: { name, branch_length: branchLength, confidence, children }, nextIdx: idx }
}

// ---------------------------------------------------------------------------
// 统计计算
// ---------------------------------------------------------------------------

export function computeTreeStatistics(root: NewickNode): TreeStatistics {
  let totalBranches = 0
  let totalBranchLength = 0
  let sequenceCount = 0
  const bootstrapValues: number[] = []

  function walk(node: NewickNode): number {
    totalBranches++
    totalBranchLength += node.branch_length || 0
    if (node.children.length === 0) {
      sequenceCount++
      return node.branch_length || 0
    }
    if (node.confidence !== undefined) {
      bootstrapValues.push(node.confidence)
    }
    let maxChildHeight = 0
    for (const child of node.children) {
      const h = walk(child)
      if (h > maxChildHeight) maxChildHeight = h
    }
    return maxChildHeight + (node.branch_length || 0)
  }

  const treeHeight = walk(root)
  const meanBranchLength = totalBranchLength / Math.max(totalBranches, 1)

  return {
    sequence_count: sequenceCount,
    total_branches: Math.max(totalBranches - 1, 0),
    total_tree_length: Math.round(totalBranchLength * 10000) / 10000,
    mean_branch_length: Math.round(meanBranchLength * 10000) / 10000,
    tree_height: Math.round(treeHeight * 10000) / 10000,
    min_bootstrap: bootstrapValues.length ? Math.min(...bootstrapValues) : 0,
    max_bootstrap: bootstrapValues.length ? Math.max(...bootstrapValues) : 0,
    avg_bootstrap: bootstrapValues.length
      ? Math.round((bootstrapValues.reduce((a, b) => a + b, 0) / bootstrapValues.length) * 100) / 100
      : 0,
    has_bootstrap_support: bootstrapValues.length > 0,
  }
}

// ---------------------------------------------------------------------------
// 渲染选项
// ---------------------------------------------------------------------------

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function createRenderOptions(vizConfig: VizConfig, _isDark: boolean): Record<string, any> {
  return {
    zoom: true,
    brush: false,
    collapsible: true,
    selectable: true,
    'align-tips': vizConfig.alignTips,
    'show-labels': vizConfig.showLabels,
    'show-scale': vizConfig.showScaleBar,
    'font-size': vizConfig.fontSize,
    width: 800,
    height: 600,
    layout: vizConfig.layout === 'rectangular' ? 'left-to-right' : 'left-to-right',
    'is-radial': vizConfig.layout === 'radial' || vizConfig.layout === 'circular',
  }
}

// ---------------------------------------------------------------------------
// phylotree.js 渲染封装
// ---------------------------------------------------------------------------

export class PhyloTreeRenderer {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private tree: any = null
  private container: HTMLElement | null = null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private options: Record<string, any> = {}
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private phylotreeCtor: any = null

  async init(container: HTMLElement, options: Record<string, unknown> = {}) {
    this.container = container
    this.options = options
    const mod = await loadPhylotreeModule()
    this.phylotreeCtor = (mod as Record<string, unknown>).phylotree
    this.clear()
  }

  async render(newickStr: string, options: Record<string, unknown> = {}) {
    if (!this.container || !this.phylotreeCtor) return
    this.clear()
    this.options = { ...this.options, ...options }
    this.tree = new this.phylotreeCtor(newickStr.trim())
    this.tree.render({ container: this.container, ...this.options })
  }

  async updateOptions(options: Record<string, unknown>) {
    if (!this.tree || !this.container) return
    this.options = { ...this.options, ...options }
    this.tree.render({ container: this.container, ...this.options })
  }

  highlightNode(nodeId: string) {
    if (!this.tree) return
    const target = this.tree.getNodeByName(nodeId)
    if (target) {
      target.selected = true
      this.tree.display?.refresh()
    }
  }

  exportSVG(): string {
    const svg = this.container?.querySelector('svg')
    return svg ? new XMLSerializer().serializeToString(svg) : ''
  }

  exportNewick(): string {
    return this.tree ? this.tree.getNewick() : ''
  }

  clear() {
    if (this.container) this.container.innerHTML = ''
  }

  destroy() {
    this.clear()
    this.tree = null
    this.container = null
    this.phylotreeCtor = null
  }
}

// ---------------------------------------------------------------------------
// 导出辅助
// ---------------------------------------------------------------------------

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function svgToPng(svgString: string): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const svg = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(svg)
    const img = new Image()
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      URL.revokeObjectURL(url)
      reject(new Error('Canvas 2D context not available'))
      return
    }
    img.onload = () => {
      canvas.width = img.naturalWidth || 1200
      canvas.height = img.naturalHeight || 800
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.drawImage(img, 0, 0)
      URL.revokeObjectURL(url)
      canvas.toBlob((blob) => {
        if (blob) resolve(blob)
        else reject(new Error('PNG conversion failed'))
      }, 'image/png')
    }
    img.onerror = (e) => {
      URL.revokeObjectURL(url)
      reject(e)
    }
    img.src = url
  })
}
