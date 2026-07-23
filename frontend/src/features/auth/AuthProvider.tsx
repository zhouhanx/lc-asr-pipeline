import { useEffect, useMemo, useState, type PropsWithChildren } from 'react'

import { apiRequest, refreshAuthSession, setAuthSessionListener, type AuthPayload } from '@/lib/api'

import { AuthContext, type LoginInput } from './auth-context'

export function AuthProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<AuthPayload | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    const removeSessionListener = setAuthSessionListener((payload) => {
      if (active) setSession(payload)
    })
    refreshAuthSession()
      .then((payload) => {
        if (active) setSession(payload)
      })
      .catch(() => {
        if (active) setSession(null)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
      removeSessionListener()
    }
  }, [])

  useEffect(() => {
    if (!session) return
    const expiresAt = new Date(session.expires_at).getTime()
    const refreshDelay = Math.max(0, expiresAt - Date.now() - 60_000)
    const timer = window.setTimeout(() => {
      refreshAuthSession()
        .then(setSession)
        .catch(() => setSession(null))
    }, refreshDelay)
    return () => window.clearTimeout(timer)
  }, [session])

  const value = useMemo(
    () => ({
      session,
      loading,
      login: async (input: LoginInput) => {
        const payload = await apiRequest<AuthPayload>('/auth/login', {
          method: 'POST',
          body: input,
        })
        if (!payload.password_change_required) setSession(payload)
        return payload
      },
      logout: async () => {
        try {
          await apiRequest('/auth/logout', { method: 'POST' })
        } finally {
          setSession(null)
        }
      },
    }),
    [loading, session],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
