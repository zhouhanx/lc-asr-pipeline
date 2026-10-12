type BrowserBrand = { brand: string; version: string }

export type BrowserNavigator = {
  userAgent: string
  brave?: unknown
  userAgentData?: {
    brands: BrowserBrand[]
    mobile?: boolean
  }
}

export type SupportedBrowser = 'chrome' | 'edge'

export function detectSupportedBrowser(
  browserNavigator: BrowserNavigator = navigator as BrowserNavigator,
): SupportedBrowser | null {
  const brands = browserNavigator.userAgentData?.brands ?? []
  if (browserNavigator.userAgentData?.mobile) return null
  if (brands.some(({ brand }) => brand === 'Microsoft Edge')) return 'edge'
  if (
    browserNavigator.brave !== undefined ||
    brands.some(({ brand }) =>
      /Brave|Opera|Vivaldi|Samsung|Yandex/i.test(brand),
    )
  ) {
    return null
  }
  if (brands.some(({ brand }) => brand === 'Google Chrome')) return 'chrome'

  const userAgent = browserNavigator.userAgent
  if (/\bEdg\/[\d.]+/.test(userAgent)) return 'edge'
  if (
    /\b(?:OPR|Opera|SamsungBrowser|Vivaldi|YaBrowser|Brave)\//.test(userAgent)
  ) {
    return null
  }
  if (/\bChrome\/[\d.]+/.test(userAgent) && !/\b(?:Mobile|Android)\b/.test(userAgent)) {
    return 'chrome'
  }
  return null
}
