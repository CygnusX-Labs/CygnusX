/**
 * 参考基因组模块 mock 数据（前端静态，后续对接后端 API 时替换）。
 *
 * 首批仅生菜 v8 / v11 两个版本，9 条染色体，30 条基因用于搜索交互演示。
 */

export interface Genome {
  id: string
  speciesEmoji: string
  commonName: string
  latinName: string
  version: string
  versionFull: string
  tags: string[]
  chromosomes: number
  totalGenes: number
  genomeSize: string
  n50: string
  releaseDate: string
  isDefault: boolean
  /** 卡片底部渐变条 */
  gradient: string
}

export interface Chromosome {
  name: string
  length: number
  color: string
}

export interface Gene {
  geneId: string
  geneName: string
  chromosome: string
  start: number
  end: number
  strand: '+' | '-'
  length: number
  annotation: string
  exons: number
}

export interface GenomeFile {
  name: string
  size: string
  indexed: boolean
  path: string
}

export interface GeneTypeStat {
  name: string
  value: number
  color: string
}

/** 基因组列表（首批：生菜 v8 / v11）。 */
export const MOCK_GENOMES: Genome[] = [
  {
    id: 'lettuce-v11',
    speciesEmoji: '🥬',
    commonName: '生菜',
    latinName: 'Lactuca sativa',
    version: 'v11',
    versionFull: 'Lsat.1.v11',
    tags: ['最新版', '染色体级'],
    chromosomes: 9,
    totalGenes: 38678,
    genomeSize: '2.69 Gb',
    n50: '120 Mb',
    releaseDate: '2023-05',
    isDefault: true,
    gradient: 'linear-gradient(90deg, #3b82f6, #7c3aed)',
  },
  {
    id: 'lettuce-v8',
    speciesEmoji: '🥬',
    commonName: '生菜',
    latinName: 'Lactuca sativa',
    version: 'v8',
    versionFull: 'Lsat.1.v8',
    tags: ['稳定版', '染色体级'],
    chromosomes: 9,
    totalGenes: 35241,
    genomeSize: '2.65 Gb',
    n50: '95 Mb',
    releaseDate: '2020-11',
    isDefault: false,
    gradient: 'linear-gradient(90deg, #60a5fa, #6366f1)',
  },
]

/** 9 条染色体（长度与颜色，蓝紫色系由浅到深）。 */
export const MOCK_CHROMOSOMES: Chromosome[] = [
  { name: 'Chr1', length: 425000000, color: '#6366f1' },
  { name: 'Chr2', length: 380000000, color: '#7c3aed' },
  { name: 'Chr3', length: 350000000, color: '#8b5cf6' },
  { name: 'Chr4', length: 310000000, color: '#a855f7' },
  { name: 'Chr5', length: 290000000, color: '#9333ea' },
  { name: 'Chr6', length: 270000000, color: '#7c3aed' },
  { name: 'Chr7', length: 250000000, color: '#6d28d9' },
  { name: 'Chr8', length: 230000000, color: '#5b21b6' },
  { name: 'Chr9', length: 195000000, color: '#4c1d95' },
]

/** 基因类型分布（概览饼图）。 */
export const MOCK_GENE_TYPES: GeneTypeStat[] = [
  { name: 'mRNA', value: 32104, color: '#6366f1' },
  { name: 'lncRNA', value: 4218, color: '#a855f7' },
  { name: 'TE', value: 1856, color: '#ec4899' },
  { name: 'Other', value: 500, color: '#94a3b8' },
]

/** 参考文件清单。 */
export const MOCK_FILES: GenomeFile[] = [
  { name: 'genome.fa', size: '2.1 Gb', indexed: true, path: '/data/omichub/reference/lettuce-v11/genome.fa' },
  { name: 'genes.gff3', size: '156 Mb', indexed: true, path: '/data/omichub/reference/lettuce-v11/genes.gff3' },
  { name: 'genes.gtf', size: '142 Mb', indexed: true, path: '/data/omichub/reference/lettuce-v11/genes.gtf' },
  { name: 'STAR index', size: '8.4 Gb', indexed: true, path: '/data/omichub/reference/lettuce-v11/STAR/' },
  { name: 'HISAT2 index', size: '6.2 Gb', indexed: true, path: '/data/omichub/reference/lettuce-v11/HISAT2/' },
]

/** 手写的 12 条有语义基因。 */
const GENE_BASE: Gene[] = [
  { geneId: 'LsG0001.1', geneName: 'LsMYB1', chromosome: 'Chr1', start: 1234567, end: 1235890, strand: '+', length: 1324, annotation: 'MYB transcription factor family protein', exons: 3 },
  { geneId: 'LsG0002.1', geneName: 'LsWRKY1', chromosome: 'Chr2', start: 2345678, end: 2347890, strand: '-', length: 2212, annotation: 'WRKY transcription factor 45', exons: 5 },
  { geneId: 'LsG0003.1', geneName: 'LsbHLH1', chromosome: 'Chr1', start: 3456789, end: 3458123, strand: '+', length: 1334, annotation: 'bHLH transcription factor', exons: 4 },
  { geneId: 'LsG0004.1', geneName: 'LsACT1', chromosome: 'Chr3', start: 1456789, end: 1459234, strand: '+', length: 2445, annotation: 'Actin family protein', exons: 6 },
  { geneId: 'LsG0005.1', geneName: 'LsUBQ1', chromosome: 'Chr2', start: 2567890, end: 2568456, strand: '-', length: 566, annotation: 'Ubiquitin-like domain protein', exons: 2 },
  { geneId: 'LsG0006.1', geneName: 'LsCYP1', chromosome: 'Chr4', start: 1678901, end: 1680456, strand: '+', length: 1555, annotation: 'Cytochrome P450', exons: 3 },
  { geneId: 'LsG0007.1', geneName: 'LsCHS1', chromosome: 'Chr5', start: 1789012, end: 1791234, strand: '-', length: 1222, annotation: 'Chalcone synthase', exons: 2 },
  { geneId: 'LsG0008.1', geneName: 'LsPAL1', chromosome: 'Chr3', start: 2890123, end: 2892345, strand: '+', length: 2222, annotation: 'Phenylalanine ammonia-lyase', exons: 4 },
  { geneId: 'LsG0009.1', geneName: 'LsF3H1', chromosome: 'Chr6', start: 1901234, end: 1902567, strand: '-', length: 1333, annotation: 'Flavanone 3-hydroxylase', exons: 3 },
  { geneId: 'LsG0010.1', geneName: 'LsDFR1', chromosome: 'Chr4', start: 2012345, end: 2013890, strand: '+', length: 1545, annotation: 'Dihydroflavonol reductase', exons: 3 },
  { geneId: 'LsG0011.1', geneName: 'LsANS1', chromosome: 'Chr7', start: 2123456, end: 2124789, strand: '-', length: 1333, annotation: 'Anthocyanidin synthase', exons: 2 },
  { geneId: 'LsG0012.1', geneName: 'LsGT1', chromosome: 'Chr5', start: 2234567, end: 2236123, strand: '+', length: 1556, annotation: 'Glycosyltransferase', exons: 4 },
]

/** 生成完整 30 条基因（12 条手写 + 18 条确定性生成）。 */
function buildGenes(): Gene[] {
  const annotations = [
    'Hypothetical protein', 'Protein kinase family protein', 'Leucine-rich repeat protein',
    'F-box protein', 'Pentatricopeptide repeat protein', 'ABC transporter',
    'MADS-box transcription factor', 'AP2/ERF transcription factor', 'NAC transcription factor',
  ]
  const result = [...GENE_BASE]
  for (let i = 13; i <= 30; i++) {
    const chr = `Chr${((i - 1) % 9) + 1}`
    const start = 1000000 + i * 234567
    const end = start + 600 + i * 73
    result.push({
      geneId: `LsG${String(i).padStart(4, '0')}.1`,
      geneName: `LsGene${i}`,
      chromosome: chr,
      start,
      end,
      strand: i % 2 === 0 ? '-' : '+',
      length: end - start,
      annotation: annotations[(i - 13) % annotations.length],
      exons: (i % 5) + 1,
    })
  }
  return result
}

export const MOCK_GENES: Gene[] = buildGenes()

/** v8 ↔ v11 基因 ID 映射（mock，部分条目）。 */
export const MOCK_ID_MAP: Record<string, string> = {
  Lsat_v8_0001: 'LsG0001.1',
  Lsat_v8_0002: 'LsG0002.1',
  Lsat_v8_0003: 'LsG0003.1',
  Lsat_v8_0004: 'LsG0004.1',
  Lsat_v8_0005: 'LsG0005.1',
  Lsat_v8_0006: 'LsG0006.1',
  Lsat_v8_0007: 'LsG0007.1',
  Lsat_v8_0008: 'LsG0008.1',
  Lsat_v8_0009: 'LsG0009.1',
  Lsat_v8_0010: 'LsG0010.1',
}

/** 反向映射（v11 → v8），由正向映射推导。 */
export const MOCK_ID_MAP_REVERSE: Record<string, string> = Object.fromEntries(
  Object.entries(MOCK_ID_MAP).map(([v8, v11]) => [v11, v8]),
)

/** 按 id 取基因组。 */
export function getGenomeById(id: string): Genome | undefined {
  return MOCK_GENOMES.find((g) => g.id === id)
}
