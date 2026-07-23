import { useState, type FormEvent } from 'react'
import { KeyRound } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { apiRequest, ApiError } from '@/lib/api'

export function PasswordChangeSheet({
  open,
  onOpenChange,
  endpoint,
  token,
  onChanged,
  title = '修改密码',
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  endpoint: string
  token: string
  onChanged: () => void | Promise<void>
  title?: string
}) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const reset = () => {
    setCurrentPassword('')
    setNewPassword('')
    setConfirmation('')
    setError('')
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    if (newPassword !== confirmation) {
      setError('两次输入的新密码不一致。')
      return
    }
    setSaving(true)
    try {
      await apiRequest(endpoint, {
        method: 'POST',
        token,
        body: { current_password: currentPassword, new_password: newPassword },
      })
      reset()
      onOpenChange(false)
      await onChanged()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '密码修改失败。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={(nextOpen) => {
      if (!nextOpen) reset()
      onOpenChange(nextOpen)
    }}>
      <SheetContent className="border-l-4 shadow-[-8px_0_0_0_var(--border)] sm:max-w-md">
        <SheetHeader className="border-b-4 border-border bg-primary p-6">
          <div className="mb-3 grid size-12 place-items-center border-2 border-border bg-background shadow-[4px_4px_0_0_var(--border)]"><KeyRound /></div>
          <SheetTitle className="font-head text-2xl">{title}</SheetTitle>
          <SheetDescription>必须验证当前密码。修改成功后会退出当前会话，请使用新密码重新登录。</SheetDescription>
        </SheetHeader>
        <form className="space-y-5 overflow-y-auto p-6" onSubmit={submit}>
          {error && <Alert status="error"><AlertTitle>无法修改密码</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
          <div className="border-2 border-border bg-muted/40 p-4 text-xs leading-6">
            至少 8 位，不能与登录名相同，并且满足以下任一条件：同时包含大写和小写字母，或包含特殊字符。
          </div>
          <div className="space-y-2"><Label htmlFor="current-password">当前密码</Label><Input className="h-12" id="current-password" type="password" autoComplete="current-password" required value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></div>
          <div className="space-y-2"><Label htmlFor="replacement-password">新密码</Label><Input className="h-12" id="replacement-password" type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></div>
          <div className="space-y-2"><Label htmlFor="replacement-confirmation">确认新密码</Label><Input className="h-12" id="replacement-confirmation" type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></div>
          <Button className="h-12 w-full" disabled={saving}><KeyRound />{saving ? '修改中…' : '修改密码并重新登录'}</Button>
        </form>
      </SheetContent>
    </Sheet>
  )
}
