import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiRequest, ApiError } from '@/lib/api'

import { AuthShell } from './AuthShell'

type PasswordLocationState = {
  token?: string
}

export function InitialPasswordPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const state = location.state as PasswordLocationState | null
  const token = state?.token
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  if (!token) return <Navigate to="/login" replace />

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    if (password !== confirmation) {
      setError('两次输入的密码不一致。')
      return
    }
    setSaving(true)
    try {
      await apiRequest('/auth/change-initial-password', {
        method: 'POST',
        token,
        body: { new_password: password },
      })
      navigate('/login', { replace: true, state: { passwordChanged: true } })
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '密码修改失败。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <AuthShell
      title="设置新密码"
      description="至少 8 位，不能与登录名相同；需同时包含大小写字母，或者包含特殊字符。修改后必须重新登录。"
      eyebrow="REQUIRED / PASSWORD CHANGE"
    >
      {error && (
        <Alert status="error" className="mb-5">
          <AlertTitle>无法修改密码</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <form className="space-y-5" onSubmit={submit}>
        <div className="space-y-2">
          <Label htmlFor="new-password">新密码</Label>
          <Input
            id="new-password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            maxLength={128}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirm-password">确认新密码</Label>
          <Input
            id="confirm-password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            maxLength={128}
            required
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
          />
        </div>
        <Button className="w-full" disabled={saving}>
          {saving ? '保存中…' : '修改密码并退出'}
        </Button>
      </form>
    </AuthShell>
  )
}
