import { createContext } from 'react'

import type { AuthPayload } from '@/lib/api'

export type LoginInput = {
  tenant_slug: string
  email: string
  password: string
}

export type AuthContextValue = {
  session: AuthPayload | null
  loading: boolean
  login: (input: LoginInput) => Promise<AuthPayload>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
