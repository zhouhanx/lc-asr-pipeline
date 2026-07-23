import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ApiError } from '@/lib/api'

import { AuthShell } from './AuthShell'
import { useAuth } from './useAuth'

type IdentityStep = {
  tenantSlug: string
  email: string
}

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login, session } = useAuth()
  const [step, setStep] = useState<'identity' | 'password'>('identity')
  const [identity, setIdentity] = useState<IdentityStep>({ tenantSlug: '', email: '' })
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (session) return <Navigate to="/" replace />

  const advance = (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setStep('password')
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const payload = await login({
        tenant_slug: identity.tenantSlug.trim().toLowerCase(),
        email: identity.email.trim(),
        password,
      })
      if (payload.password_change_required) {
        navigate('/change-password', {
          replace: true,
          state: { token: payload.access_token },
        })
        return
      }
      navigate('/', { replace: true })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : '无法登录，请检查网络连接。')
    } finally {
      setSubmitting(false)
    }
  }

  if (step === 'password') {
    return (
      <AuthShell
        title="验证密码"
        description="身份已定位到指定租户。密码只会提交到安全认证接口。"
        eyebrow="STEP 02 / CREDENTIAL"
        footer={
          <button
            className="font-mono text-xs underline decoration-2 underline-offset-4"
            onClick={() => {
              setPassword('')
              setError('')
              setStep('identity')
            }}
          >
            ← 返回租户与邮箱
          </button>
        }
      >
        <div className="mb-5 border-2 border-border bg-muted p-3 font-mono text-xs shadow-sm">
          <p>{identity.tenantSlug}</p>
          <p className="mt-1 break-all text-muted-foreground">{identity.email}</p>
        </div>
        {error && (
          <Alert status="error" className="mb-5">
            <AlertTitle>登录失败</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <form className="space-y-5" onSubmit={submit}>
          <div className="space-y-2">
            <Label htmlFor="password">密码</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              minLength={1}
              maxLength={128}
              required
              autoFocus
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <Button className="w-full" type="submit" disabled={submitting}>
            {submitting ? '认证中...' : '进入工作台 →'}
          </Button>
        </form>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="登录"
      description="输入租户标识和注册邮箱。系统不会在这一步暴露账户是否存在。"
      eyebrow="STEP 01 / IDENTITY"
      footer={
        <div className="flex flex-wrap items-center justify-between gap-3 font-mono text-xs">
          <span>账户由平台管理员统一开通</span>
          <Link className="font-bold underline decoration-2 underline-offset-4" to="/admin">
            管理员登录
          </Link>
        </div>
      }
    >
      {typeof location.state === 'object' && location.state && 'passwordChanged' in location.state && (
        <Alert status="success" className="mb-5">
          <AlertTitle>密码修改成功</AlertTitle>
          <AlertDescription>请使用新密码重新登录。</AlertDescription>
        </Alert>
      )}
      <form className="space-y-5" onSubmit={advance}>
        <div className="space-y-2">
          <Label htmlFor="tenant-slug">租户标识</Label>
          <Input
            id="tenant-slug"
            autoComplete="organization"
            placeholder="acme-voice"
            pattern="[a-z0-9][a-z0-9-]{1,61}[a-z0-9]"
            minLength={3}
            maxLength={63}
            required
            value={identity.tenantSlug}
            onChange={(event) =>
              setIdentity((current) => ({ ...current, tenantSlug: event.target.value }))
            }
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="email">电子邮箱</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={identity.email}
            onChange={(event) =>
              setIdentity((current) => ({ ...current, email: event.target.value }))
            }
          />
        </div>
        <Button className="w-full" type="submit">
          下一步 →
        </Button>
      </form>
    </AuthShell>
  )
}
