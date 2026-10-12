import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ApiError,
  apiRequest,
  csrfTokenFromCookie,
  refreshAuthSession,
  type AuthPayload,
} from './api'

const authPayload: AuthPayload = {
  access_token: 'access-token',
  token_type: 'bearer',
  expires_at: '2030-01-01T00:00:00Z',
  user: {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'person@example.com',
    display_name: 'Person',
    email_verified: false,
  },
  tenant: {
    id: '00000000-0000-0000-0000-000000000002',
    slug: 'tenant',
    name: 'Tenant',
  },
  permissions: ['workspace:read'],
  password_change_required: false,
}

describe('CSRF-aware API requests', () => {
  beforeEach(() => {
    document.cookie = 'lc_asr_csrf=csrf-token; Path=/'
  })

  it('reads the CSRF cookie without exposing the refresh cookie', () => {
    expect(
      csrfTokenFromCookie('other=value; lc_asr_csrf=encoded%20token'),
    ).toBe('encoded token')
  })

  it('adds the CSRF header to refresh and logout requests', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(authPayload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await refreshAuthSession()
    await apiRequest('/auth/logout', { method: 'POST' })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    for (const [, init] of fetchMock.mock.calls) {
      const headers = new Headers(init?.headers)
      expect(headers.get('X-CSRF-Token')).toBe('csrf-token')
      expect(init?.credentials).toBe('include')
    }
  })

  it('includes the server operation ID in API errors for support lookup', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ detail: '简历草稿不存在' }), {
        status: 404,
        headers: {
          'Content-Type': 'application/json',
          'X-Operation-ID': 'OP-00000000-0000-4000-8000-000000000001',
        },
      }),
    ))

    const request = apiRequest('/resume-writer/documents/missing')
    await expect(request).rejects.toMatchObject({
      status: 404,
      operationId: 'OP-00000000-0000-4000-8000-000000000001',
      message: '简历草稿不存在（操作 ID：OP-00000000-0000-4000-8000-000000000001）',
    } satisfies Partial<ApiError>)
  })
})
