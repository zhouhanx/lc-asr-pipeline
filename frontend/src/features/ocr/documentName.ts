const MAX_SUMMARY_LENGTH = 28

function shorten(value: string, maxLength = MAX_SUMMARY_LENGTH) {
  const normalized = value.replace(/\s+/g, ' ').trim()
  return normalized.length > maxLength
    ? `${normalized.slice(0, maxLength - 1).trimEnd()}…`
    : normalized
}

export function originalDocumentName(sourcePath: string) {
  return sourcePath.split('/').at(-1) ?? sourcePath
}

export function summarizeDocumentName(sourcePath: string) {
  const original = originalDocumentName(sourcePath)
  const stem = original.replace(/\.[^.]+$/, '').trim()
  const bracketed = stem.match(/^【([^】]+)】\s*(.*)$/)

  if (bracketed) {
    const [, subject, suffix] = bracketed
    const roleSection = subject.split('_')[0]
    const items = roleSection
      .split(/[、，,]/)
      .map((item) => item.trim())
      .filter(Boolean)
    const primary = items[0] ?? roleSection
    const subjectSummary = items.length > 1 ? `${primary}等${items.length}项` : primary
    return shorten([subjectSummary, suffix.trim()].filter(Boolean).join(' · '))
  }

  return shorten(stem)
}
