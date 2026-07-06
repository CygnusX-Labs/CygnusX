/**
 * 序列魔术师核心算法（纯函数，无 Vue 依赖）。
 *
 * 解析 FASTA → 类型检测 → 反向互补 / DNA↔RNA / 六框翻译 / GC 分析 / 序列清理。
 * 对齐需求文档 §2.3，密码子表为标准遗传密码。
 */

export type SeqType = 'dna' | 'rna' | 'protein'

export interface SeqStats {
  gc: number
  at: number
  length: number
  mw: number // kDa，按 DNA ~330 Da/bp 估算
  n50: number // 连续最长 ATGC 片段
}

export interface SixFrameResult {
  frame: number // +1, +2, +3, -1, -2, -3
  label: string
  protein: string
}

/** 解析输入：去除 FASTA 标题行与所有空白，统一大写。 */
export function parseFasta(text: string): string {
  return text
    .split('\n')
    .filter((line) => !line.startsWith('>'))
    .join('')
    .replace(/\s/g, '')
    .toUpperCase()
}

/**
 * 序列类型自动检测：
 * - 含 U 且无 T → RNA
 * - 非 ATGCU 字母占比 > 10% → Protein
 * - 否则 → DNA
 */
export function detectSeqType(seq: string): SeqType {
  const s = seq.toUpperCase().replace(/[^A-Z]/g, '')
  if (!s) return 'dna'
  const hasU = s.includes('U')
  const hasT = s.includes('T')
  if (hasU && !hasT) return 'rna'
  const nonStd = s.replace(/[ATGCU]/g, '')
  if (nonStd.length / s.length > 0.1) return 'protein'
  return 'dna'
}

/** 互补碱基表（含 IUPAC 简并碱基）。 */
const COMPLEMENT: Record<string, string> = {
  A: 'T', T: 'A', G: 'C', C: 'G', U: 'A',
  R: 'Y', Y: 'R', S: 'S', W: 'W', K: 'M', M: 'K',
  B: 'V', V: 'B', D: 'H', H: 'D', N: 'N',
}

/** 反向互补（DNA: T↔A, C↔G; RNA: U↔A）。 */
export function reverseComplement(seq: string): string {
  return seq
    .toUpperCase()
    .split('')
    .reverse()
    .map((b) => COMPLEMENT[b] || b)
    .join('')
}

/** DNA → RNA：T 替换为 U。 */
export function dnaToRna(seq: string): string {
  return seq.toUpperCase().replace(/T/g, 'U')
}

/** RNA → DNA：U 替换为 T。 */
export function rnaToDna(seq: string): string {
  return seq.toUpperCase().replace(/U/g, 'T')
}

/** 标准遗传密码表（DNA 三联体 → 氨基酸单字母，* 为终止子）。 */
const CODON_TABLE: Record<string, string> = {
  TTT: 'F', TTC: 'F', TTA: 'L', TTG: 'L',
  CTT: 'L', CTC: 'L', CTA: 'L', CTG: 'L',
  ATT: 'I', ATC: 'I', ATA: 'I', ATG: 'M',
  GTT: 'V', GTC: 'V', GTA: 'V', GTG: 'V',
  TCT: 'S', TCC: 'S', TCA: 'S', TCG: 'S',
  CCT: 'P', CCC: 'P', CCA: 'P', CCG: 'P',
  ACT: 'T', ACC: 'T', ACA: 'T', ACG: 'T',
  GCT: 'A', GCC: 'A', GCA: 'A', GCG: 'A',
  TAT: 'Y', TAC: 'Y', TAA: '*', TAG: '*',
  CAT: 'H', CAC: 'H', CAA: 'Q', CAG: 'Q',
  AAT: 'N', AAC: 'N', AAA: 'K', AAG: 'K',
  GAT: 'D', GAC: 'D', GAA: 'E', GAG: 'E',
  TGT: 'C', TGC: 'C', TGA: '*', TGG: 'W',
  CGT: 'R', CGC: 'R', CGA: 'R', CGG: 'R',
  AGT: 'S', AGC: 'S', AGA: 'R', AGG: 'R',
  GGT: 'G', GGC: 'G', GGA: 'G', GGG: 'G',
}

/** 单链单起点翻译（frame=1 从第 0 位起）。 */
function translateFrame(seq: string, frame: number): string {
  let protein = ''
  for (let i = frame - 1; i < seq.length - 2; i += 3) {
    const codon = seq.slice(i, i + 3)
    protein += CODON_TABLE[codon] || 'X'
  }
  return protein
}

/**
 * 六框翻译：+1/+2/+3 从原链起点 0/1/2 翻译；
 * -1/-2/-3 从反向互补链起点 0/1/2 翻译。
 */
export function sixFrameTranslate(seq: string): SixFrameResult[] {
  const s = seq.toUpperCase().replace(/[^ACGTUN]/g, '')
  const rc = reverseComplement(s)
  const results: SixFrameResult[] = []
  for (let f = 1; f <= 3; f++) {
    results.push({ frame: f, label: `+${f}`, protein: translateFrame(s, f) })
  }
  for (let f = 1; f <= 3; f++) {
    results.push({ frame: -f, label: `-${f}`, protein: translateFrame(rc, f) })
  }
  return results
}

/**
 * GC 含量分析：GC% / AT% / 长度 / 分子量(kDa) / N50(连续最长有效片段)。
 */
export function analyzeGC(seq: string): SeqStats {
  const s = seq.toUpperCase().replace(/[^ATGCU]/g, '')
  if (!s.length) return { gc: 0, at: 0, length: 0, mw: 0, n50: 0 }
  const gc = (s.match(/[GC]/g) || []).length
  const at = (s.match(/[ATU]/g) || []).length
  const matches = s.match(/[ATGCU]+/g) || []
  const n50 = matches.reduce((max, m) => Math.max(max, m.length), 0)
  const mw = (s.length * 330) / 1000
  return {
    gc: +(gc / s.length * 100).toFixed(2),
    at: +(at / s.length * 100).toFixed(2),
    length: s.length,
    mw: +mw.toFixed(2),
    n50,
  }
}

/** 序列清理：去除数字、空格、换行等非字母字符，大写。 */
export function cleanSequence(seq: string): string {
  return seq.replace(/[^A-Za-z]/g, '').toUpperCase()
}

/**
 * 格式化为带行号的 FASTA 风格：每 lineLength 个字符换行，行首 8 位行号。
 */
export function formatWithLineNumbers(seq: string, lineLength = 60): string {
  const lines: string[] = []
  for (let i = 0; i < seq.length; i += lineLength) {
    const lineNum = String(i + 1).padStart(8, ' ')
    lines.push(`${lineNum}  ${seq.slice(i, i + lineLength)}`)
  }
  return lines.join('\n')
}

/**
 * 氨基酸颜色编码（IGV 风格分组）：
 * 疏水性蓝、亲水性红、极性绿、带电黄、其他灰、终止红、未知白。
 */
export const AA_COLORS: Record<string, string> = {
  // 疏水性
  A: '#80b3ff', I: '#80b3ff', L: '#80b3ff', M: '#80b3ff', F: '#80b3ff', W: '#80b3ff', V: '#80b3ff',
  // 亲水性（碱性）
  R: '#ff8a80', K: '#ff8a80', H: '#ff8a80',
  // 极性
  S: '#80ff9a', T: '#80ff9a', C: '#80ff9a', N: '#80ff9a', Q: '#80ff9a', Y: '#80ff9a',
  // 带电（酸性）
  D: '#ffd54f', E: '#ffd54f',
  // 其他
  G: '#c9c9c9', P: '#c9c9c9',
  // 终止 / 未知
  '*': '#ff3d3d', X: '#ffffff',
}

/** 内置示例：水稻 ACTB 基因片段（DNA）。 */
export function genSampleSeq(): string {
  return `>Oryza_sativa_ACTB_fragment
ATGGCAGACGCAGATGAGATCAAGGCCAAGGCGGCGGCGGCGGCGGCGGC
GGCGGCGGCGGCGGCGGCGGCGGCGATGGCAGACGCAGATGAGATCAAGGCC
AAGGCGGCGGCGGCGGCGGCGGCGGCGGCGGCGGCGGCGGCGATGGCAGACG
CAGATGAGATCAAGGCCAAGGCGGCGGCGGCGGCGGCGGCGGCGGCGGCGGC`
}
