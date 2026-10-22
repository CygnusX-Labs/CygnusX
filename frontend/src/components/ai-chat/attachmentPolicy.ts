/** 聊天输入框文件选择器接受的文件类型；需与后端 chat-upload 白名单保持一致。 */
export const CHAT_UPLOAD_ACCEPT = [
  '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.ico',
  '.pdf', '.txt', '.md', '.doc', '.docx', '.rtf',
  '.xls', '.xlsx', '.xlsm', '.ods',
  '.ppt', '.pptx', '.pptm', '.odp', '.odt',
  '.csv', '.tsv', '.json', '.yaml', '.yml', '.xml', '.html', '.htm',
  '.py', '.r', '.ipynb',
  '.fastq', '.fq', '.fasta', '.fa', '.fna', '.faa', '.ffn',
  '.bam', '.cram', '.sam', '.vcf', '.gff', '.gff3', '.gtf', '.bed',
  '.h5ad', '.rds', '.qs', '.gz', '.zip', '.tar', '.bz2', '.xz',
  '.nwk', '.newick', '.nhx', '.nh', '.tree', '.tre', '.trees', '.dnd', '.nex', '.nexus',
  '.iqtree', '.treefile', '.contree', '.bionj', '.mldist', '.ufboot', '.log',
  '.aln', '.phy', '.phylip', '.sto',
  // 文献 / 通路基因集 / 代码文档
  '.bib', '.ris', '.enw', '.nbib', '.gmt', '.gmx', '.rnk',
  '.rmd', '.qmd', '.tex', '.rst', '.sh', '.sql', '.toml', '.ini', '.cfg',
  // 结构 / 系统发育文本 / 邮件
  '.nxs', '.raxml', '.star', '.pdb', '.cif', '.mmcif', '.sdf', '.mol2', '.xyz', '.eml',
  // 图像 / 组学元数据 / 旧版二进制工作簿
  '.tif', '.tiff', '.biom', '.h5', '.hdf5', '.mat', '.xlsb',
  // 以下格式只走文件管理 → @ → 沙盒
  '.parquet', '.feather', '.npy', '.npz', '.pkl',
  '.fcs', '.mzml', '.mzxml', '.mgf', '.raw', '.bw', '.bigwig',
  '.bcf', '.maf', '.idat', '.cel', '.qza', '.qzv',
].join(',')

const DATA_MANAGEMENT_ONLY_SUFFIXES = new Set([
  '.bam',
  '.cram',
  '.h5ad',
  '.rds',
  '.qs',
  '.zip',
  '.parquet',
  '.feather',
  '.npy',
  '.npz',
  '.pkl',
  '.fcs',
  '.mzml',
  '.mzxml',
  '.mgf',
  '.raw',
  '.bw',
  '.bigwig',
  '.bcf',
  '.maf',
  '.idat',
  '.cel',
  '.qza',
  '.qzv',
])

export const DATA_MANAGEMENT_UPLOAD_HINT =
  '请前往“文件管理”上传，再在输入框中使用 @ 引用该文件，避免聊天模型直接解析大体积或二进制数据。'

export function requiresDataManagementUpload(filename: string): boolean {
  const normalized = filename.trim().toLowerCase()
  return [...DATA_MANAGEMENT_ONLY_SUFFIXES].some((suffix) => normalized.endsWith(suffix))
}
