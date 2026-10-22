import { describe, expect, it } from 'vitest'
import { CHAT_UPLOAD_ACCEPT, requiresDataManagementUpload } from '../attachmentPolicy'

describe('CHAT_UPLOAD_ACCEPT', () => {
  const accepted = CHAT_UPLOAD_ACCEPT.split(',')

  it.each([
    '.xlsx', '.xlsm', '.xls', '.ods', '.pptx', '.docx', '.pdf', '.csv', '.fastq', '.vcf',
    '.bib', '.ris', '.gmt', '.rnk', '.rmd', '.qmd', '.tex', '.sh', '.sql', '.toml',
    '.pdb', '.cif', '.mmcif', '.sdf', '.xyz', '.eml',
    '.tif', '.tiff', '.biom', '.h5', '.hdf5', '.mat', '.xlsb',
    '.parquet', '.fcs', '.mzml', '.bw', '.qza',
  ])(
    'includes %s so the picker does not grey it out',
    (suffix) => {
      expect(accepted).toContain(suffix)
    },
  )
})

describe('requiresDataManagementUpload', () => {
  it.each([
    'sample.bam', 'alignment.CRAM', 'cells.h5ad', 'object.Rds', 'integration_harmony.qs',
    'bundle.zip', 'matrix.parquet', 'values.npy', 'flow.fcs', 'spectra.mzML', 'calls.bcf',
    'variants.maf', 'qiime.qza',
  ])(
    'routes %s through file management',
    (filename) => {
      expect(requiresDataManagementUpload(filename)).toBe(true)
    },
  )

  it.each([
    'plot.png', 'metadata.csv', 'markers.tsv', 'report.pdf', 'genes.fasta',
    'refs.bib', 'genes.gmt', 'protein.pdb', 'mail.eml', 'table.biom', 'data.h5',
    'figure.tif', 'legacy.xlsb', 'counts.csv.gz',
  ])(
    'keeps %s in the chat attachment flow',
    (filename) => {
      expect(requiresDataManagementUpload(filename)).toBe(false)
    },
  )
})
