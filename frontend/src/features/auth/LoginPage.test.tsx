import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import type { AuthPayload } from '@/lib/api'

import { AuthContext, type AuthContextValue } from './auth-context'
import { LoginPage } from './LoginPage'

const payload: AuthPayload = {
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
    slug: 'acme-voice',
    name: 'Acme Voice',
  },
  permissions: ['workspace:read'],
  password_change_required: false,
}

describe('tenant login flow', () => {
  it('collects identity and password in two user-visible steps', async () => {
    const user = userEvent.setup()
    const login = vi.fn<AuthContextValue['login']>().mockResolvedValue(payload)
    render(
      <AuthContext.Provider
        value={{
          session: null,
          loading: false,
          login,
          logout: vi.fn(),
        }}
      >
        <MemoryRouter initialEntries={['/login']}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<h1>工作台入口</h1>} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )

    await user.type(screen.getByLabelText('租户标识'), 'acme-voice')
    await user.type(screen.getByLabelText('电子邮箱'), 'person@example.com')
    await user.click(screen.getByRole('button', { name: '下一步 →' }))
    expect(screen.getByRole('heading', { name: '验证密码' })).toBeInTheDocument()

    await user.type(screen.getByLabelText('密码'), 'Correct-Horse-42!')
    await user.click(screen.getByRole('button', { name: '进入工作台 →' }))

    expect(login).toHaveBeenCalledWith({
      tenant_slug: 'acme-voice',
      email: 'person@example.com',
      password: 'Correct-Horse-42!',
    })
    expect(await screen.findByRole('heading', { name: '工作台入口' })).toBeInTheDocument()
  })
})
