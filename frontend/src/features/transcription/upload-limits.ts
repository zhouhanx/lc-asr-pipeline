export const MAX_BATCH_BYTES = 5 * 1024 ** 3

export function uploadBatchSizeError(sizeBytes: number): string {
  return sizeBytes > MAX_BATCH_BYTES ? '单次上传总量不能超过 5 GiB。' : ''
}
