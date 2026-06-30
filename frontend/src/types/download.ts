/** 数据下载相关类型 */

export interface DownloadRequest {
  accession: string
  download_method: 'aws' | 'aspera' | 'ftp'
  multithreads: number
  aws_threads: number
}
