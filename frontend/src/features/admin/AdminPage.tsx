import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiRequest, ApiError } from '@/lib/api'

import { AuthShell } from '../auth/AuthShell'
import { AdminWorkspace } from './AdminWorkspace'
import type { AdminAuth } from './types'

export function AdminPage() {
  const [auth, setAuth] = useState<AdminAuth | null>(null)
  const [username, setUsername] = useState('root')
  const [password, setPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const login = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setMessage('')
    setSubmitting(true)
    try {
      const payload = await apiRequest<AdminAuth>('/admin/auth/login', {
        method: 'POST',
        body: { username, password },
      })
      setAuth(payload)
      setPassword('')
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '管理员登录失败。')
    } finally {
      setSubmitting(false)
    }
  }

  const changePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!auth) return
    setError('')
    if (newPassword !== confirmation) {
      setError('两次输入的密码不一致。')
      return
    }
    setSubmitting(true)
    try {
      await apiRequest('/admin/auth/change-initial-password', {
        method: 'POST',
        token: auth.access_token,
        body: { new_password: newPassword },
      })
      setAuth(null)
      setNewPassword('')
      setConfirmation('')
      setMessage('管理员密码已修改，请使用新密码重新登录。')
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '管理员密码修改失败。')
    } finally {
      setSubmitting(false)
    }
  }

  if (!auth) {
    return (
      <AuthShell
        title="管理员登录"
        description="平台超级管理员可统一创建组织和账户，并跨租户查看任务、转写内容及原始录音。"
        eyebrow="INTERNAL / PLATFORM ADMIN"
        footer={<Link className="font-mono text-xs font-bold underline decoration-2 underline-offset-4" to="/login">← 返回用户登录</Link>}
      >
        {message && <Alert status="success" className="mb-5"><AlertTitle>操作成功</AlertTitle><AlertDescription>{message}</AlertDescription></Alert>}
        {error && <Alert status="error" className="mb-5"><AlertTitle>登录失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
        <form className="space-y-5" onSubmit={login}>
          <div className="space-y-2"><Label htmlFor="admin-username">管理员用户名</Label><Input className="h-12" id="admin-username" autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} /></div>
          <div className="space-y-2"><Label htmlFor="admin-password">密码</Label><Input className="h-12" id="admin-password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></div>
          <Button className="h-12 w-full" disabled={submitting}><ShieldCheck />{submitting ? '认证中…' : '进入管理平台'}</Button>
        </form>
      </AuthShell>
    )
  }

  if (auth.password_change_required) {
    return (
      <AuthShell title="修改管理员密码" description="初始 root 密码只能用于首次登录。修改后必须重新登录才能进入管理平台。" eyebrow="REQUIRED / ADMIN PASSWORD">
        {error && <Alert status="error" className="mb-5"><AlertTitle>修改失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
        <form className="space-y-5" onSubmit={changePassword}>
          <div className="border-2 border-border bg-muted/40 p-4 text-xs leading-6">至少 8 位，不能与用户名相同；需同时包含大小写字母，或者包含特殊字符。</div>
          <div className="space-y-2"><Label htmlFor="admin-new-password">新密码</Label><Input className="h-12" id="admin-new-password" type="password" autoComplete="new-password" minLength={8} required value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></div>
          <div className="space-y-2"><Label htmlFor="admin-confirm-password">确认新密码</Label><Input className="h-12" id="admin-confirm-password" type="password" autoComplete="new-password" minLength={8} required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></div>
          <Button className="h-12 w-full" disabled={submitting}>{submitting ? '保存中…' : '修改密码并退出'}</Button>
        </form>
      </AuthShell>
    )
  }

  return <AdminWorkspace auth={auth} onLogout={() => setAuth(null)} />
}
