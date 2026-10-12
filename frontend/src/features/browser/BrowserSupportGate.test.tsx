import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { BrowserSupportGate } from './BrowserSupportGate'
import { detectSupportedBrowser, type BrowserNavigator } from './browser-policy'

const chrome: BrowserNavigator = {
  userAgent: 'Mozilla/5.0 Chrome/140.0.0.0 Safari/537.36',
  userAgentData: {
    brands: [
      { brand: 'Chromium', version: '140' },
      { brand: 'Google Chrome', version: '140' },
    ],
    mobile: false,
  },
}

const edge: BrowserNavigator = {
  userAgent: 'Mozilla/5.0 Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0',
  userAgentData: {
    brands: [
      { brand: 'Chromium', version: '140' },
      { brand: 'Microsoft Edge', version: '140' },
    ],
    mobile: false,
  },
}

describe('browser support policy', () => {
  it('accepts only desktop Google Chrome and Microsoft Edge', () => {
    expect(detectSupportedBrowser(chrome)).toBe('chrome')
    expect(detectSupportedBrowser(edge)).toBe('edge')
    expect(
      detectSupportedBrowser({
        userAgent: 'Mozilla/5.0 Version/18.0 Safari/605.1.15',
      }),
    ).toBeNull()
    expect(
      detectSupportedBrowser({
        userAgent: 'Mozilla/5.0 Firefox/141.0',
      }),
    ).toBeNull()
    expect(
      detectSupportedBrowser({
        userAgent: 'Mozilla/5.0 Chrome/140.0.0.0 Safari/537.36',
        brave: {},
        userAgentData: {
          brands: [{ brand: 'Brave', version: '140' }],
          mobile: false,
        },
      }),
    ).toBeNull()
  })

  it('does not initialize children in an unsupported browser', () => {
    vi.stubGlobal('navigator', {
      userAgent: 'Mozilla/5.0 Firefox/141.0',
    })
    const child = vi.fn(() => <div>authenticated application</div>)
    const Child = child
    render(
      <BrowserSupportGate>
        <Child />
      </BrowserSupportGate>,
    )
    expect(child).not.toHaveBeenCalled()
    expect(
      screen.getByRole('heading', { name: '请使用 Chrome 或 Edge' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('authenticated application')).not.toBeInTheDocument()
  })
})
