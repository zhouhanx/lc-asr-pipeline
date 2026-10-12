import { describe, expect, it } from 'vitest'

import { uploadBatchSizeError } from './upload-limits'

describe('upload boundary feedback', () => {
  it('accepts exactly 5 GiB and rejects one byte over', () => {
    const limit = 5 * 1024 ** 3
    expect(uploadBatchSizeError(limit - 1)).toBe('')
    expect(uploadBatchSizeError(limit)).toBe('')
    expect(uploadBatchSizeError(limit + 1)).toContain('5 GiB')
  })
})
