import { describe, expect, it } from 'vitest'

import { navigationGroups } from './navigation'

describe('permission-aware navigation metadata', () => {
  it('keeps resume writing available and PPT explicitly marked as later work', () => {
    const documentWriting = navigationGroups
      .flatMap((group) => group.items)
      .find((item) => item.id === 'document-writing')
    expect(documentWriting?.permission).toBe('jobs:read')
    expect(documentWriting?.children?.map((item) => item.id)).toEqual([
      'resume-writer',
      'ppt-writer',
    ])
    expect(
      documentWriting?.children?.find((item) => item.id === 'ppt-writer')?.badge,
    ).toBe('SOON')
  })

  it('requires explicit permissions for every visible navigation target', () => {
    const targets = navigationGroups.flatMap((group) =>
      group.items.flatMap((item) => [item, ...(item.children ?? [])]),
    )
    expect(targets.every((item) => item.permission.length > 0)).toBe(true)
    expect(new Set(targets.map((item) => item.id)).size).toBe(targets.length)
  })
})
