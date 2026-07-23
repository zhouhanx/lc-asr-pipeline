import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  AudioLines,
  Building2,
  Download,
  FileText,
  Globe2,
  HardDrive,
  KeyRound,
  Lock,
  LogOut,
  Power,
  RotateCcw,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
} from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { TooltipProvider } from '@/components/ui/tooltip'
import { PasswordChangeSheet } from '@/features/auth/PasswordChangeSheet'
import { DialogueTranscript } from '@/features/transcription/DialogueTranscript'
import { TaskModelName } from '@/features/transcription/TaskModelName'
import { TaskIdentifier } from '@/features/transcription/TaskIdentifier'
import { apiDownload, apiRequest, ApiError, type ModelProvider } from '@/lib/api'

import { AdminSidebar } from './AdminSidebar'
import type {
  AdminAuth,
  AdminJob,
  AdminJobDetail,
  AdminRecording,
  AdminTenant,
  AdminUser,
  AdminView,
  CredentialNotice,
} from './types'

const viewTitles: Record<AdminView, string> = {
  overview: '管理总览',
  organizations: '组织和账户',
  tasks: '全部租户转写任务',
  recordings: '全部录音文件',
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MiB`
  return `${(value / 1024 ** 3).toFixed(2)} GiB`
}

export function AdminWorkspace({ auth, onLogout }: { auth: AdminAuth; onLogout: () => void }) {
  const [activeView, setActiveView] = useState<AdminView>('overview')
  const [tenants, setTenants] = useState<AdminTenant[]>([])
  const [jobs, setJobs] = useState<AdminJob[]>([])
  const [recordings, setRecordings] = useState<AdminRecording[]>([])
  const [selectedJob, setSelectedJob] = useState<AdminJobDetail | null>(null)
  const [credential, setCredential] = useState<CredentialNotice | null>(null)
  const [pendingDelete, setPendingDelete] = useState<AdminTenant | null>(null)
  const [pendingReset, setPendingReset] = useState<AdminUser | null>(null)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [recordingSetup, setRecordingSetup] = useState<AdminRecording | null>(null)
  const [recordingModels, setRecordingModels] = useState<ModelProvider[]>([])
  const [recordingForm, setRecordingForm] = useState({
    providerId: '',
    textProviderId: '',
    language: 'Chinese',
    speakerMode: 'single',
    diarize: true,
  })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const [tenantForm, setTenantForm] = useState({ name: '', slug: '', displayName: '', email: '' })
  const [userForm, setUserForm] = useState({ tenantId: '', displayName: '', email: '', role: 'member' })

  const load = useCallback(async () => {
    try {
      const [tenantPayload, jobPayload, recordingPayload] = await Promise.all([
        apiRequest<AdminTenant[]>('/admin/tenants', { token: auth.access_token }),
        apiRequest<AdminJob[]>('/admin/jobs', { token: auth.access_token }),
        apiRequest<AdminRecording[]>('/admin/recordings', { token: auth.access_token }),
      ])
      setTenants(tenantPayload)
      setJobs(jobPayload)
      setRecordings(recordingPayload)
      setUserForm((current) => ({ ...current, tenantId: current.tenantId || tenantPayload[0]?.id || '' }))
      setError('')
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '管理员数据加载失败。')
    }
  }, [auth.access_token])

  useEffect(() => { void load() }, [load])

  const createTenant = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const result = await apiRequest<{ tenant: AdminTenant; user: AdminUser; initial_password: string }>('/admin/tenants', {
        method: 'POST',
        token: auth.access_token,
        body: {
          tenant_name: tenantForm.name,
          tenant_slug: tenantForm.slug.trim().toLowerCase(),
          owner_display_name: tenantForm.displayName,
          owner_email: tenantForm.email,
        },
      })
      setCredential({ organization: result.tenant.name, login: result.user.email, password: result.initial_password })
      setTenantForm({ name: '', slug: '', displayName: '', email: '' })
      await load()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '组织创建失败。')
    } finally {
      setSaving(false)
    }
  }

  const createUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!userForm.tenantId) return
    setSaving(true)
    setError('')
    try {
      const result = await apiRequest<{ user: AdminUser; initial_password: string }>(`/admin/tenants/${userForm.tenantId}/users`, {
        method: 'POST',
        token: auth.access_token,
        body: { display_name: userForm.displayName, email: userForm.email, role: userForm.role },
      })
      setCredential({ organization: result.user.tenant_name, login: result.user.email, password: result.initial_password })
      setUserForm((current) => ({ ...current, displayName: '', email: '' }))
      await load()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '用户创建失败。')
    } finally {
      setSaving(false)
    }
  }

  const toggleUser = async (user: AdminUser) => {
    try {
      await apiRequest(`/admin/users/${user.id}`, {
        method: 'PATCH',
        token: auth.access_token,
        body: { status: user.status === 'active' ? 'disabled' : 'active' },
      })
      await load()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '账户状态修改失败。')
    }
  }

  const resetUserPassword = async () => {
    if (!pendingReset) return
    try {
      const result = await apiRequest<{ user: AdminUser; initial_password: string }>(`/admin/users/${pendingReset.id}/reset-password`, {
        method: 'POST',
        token: auth.access_token,
      })
      setCredential({
        organization: result.user.tenant_name,
        login: result.user.email,
        password: result.initial_password,
      })
      setNotice(`已重置“${result.user.display_name}”的密码，旧会话已失效。`)
      setPendingReset(null)
      await load()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '密码重置失败。')
      setPendingReset(null)
    }
  }

  const toggleTenant = async (tenant: AdminTenant) => {
    try {
      await apiRequest(`/admin/tenants/${tenant.id}`, {
        method: 'PATCH',
        token: auth.access_token,
        body: { status: tenant.status === 'active' ? 'suspended' : 'active' },
      })
      setNotice(tenant.status === 'active' ? `已禁用组织“${tenant.name}”。` : `已启用组织“${tenant.name}”。`)
      await load()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '组织状态修改失败。')
    }
  }

  const deleteTenant = async () => {
    if (!pendingDelete) return
    try {
      const result = await apiRequest<{ deleted_jobs: number; retained_recordings: number }>(`/admin/tenants/${pendingDelete.id}`, {
        method: 'DELETE',
        token: auth.access_token,
      })
      setNotice(`组织已删除：清理 ${result.deleted_jobs} 个转写任务，保留 ${result.retained_recordings} 个原始录音文件。`)
      setPendingDelete(null)
      await load()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '组织删除失败。')
      setPendingDelete(null)
    }
  }

  const openJob = async (jobId: string) => {
    try {
      setSelectedJob(await apiRequest<AdminJobDetail>(`/admin/jobs/${jobId}`, { token: auth.access_token }))
      setError('')
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '任务详情加载失败。')
    }
  }

  const toggleJobVisibility = async (job: AdminJobDetail) => {
    try {
      const updated = await apiRequest<AdminJob>(`/admin/jobs/${job.id}/visibility`, {
        method: 'PATCH',
        token: auth.access_token,
        body: { visibility: job.visibility === 'public' ? 'private' : 'public' },
      })
      setSelectedJob({ ...job, visibility: updated.visibility })
      setJobs((current) => current.map((item) => item.id === job.id ? { ...item, visibility: updated.visibility } : item))
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '任务可见范围修改失败。')
    }
  }

  const downloadJob = async (job: AdminJobDetail, format: 'txt' | 'json' | 'srt' | 'vtt' | 'html') => {
    try {
      const blob = await apiDownload(`/admin/jobs/${job.id}/export/${format}`, auth.access_token)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `transcript-${job.id}.${format}`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '任务导出失败。')
    }
  }

  const retryJob = async (job: AdminJobDetail) => {
    try {
      await apiRequest(`/admin/jobs/${job.id}/retry`, {
        method: 'POST',
        token: auth.access_token,
      })
      setNotice(job.has_asr_checkpoint ? '已重新提交文本整理，语音解析结果将直接复用。' : '已重新提交语音解析。')
      setSelectedJob(null)
      await load()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '任务重试失败。')
    }
  }

  const openRecordingTask = async (recording: AdminRecording) => {
    setRecordingSetup(recording)
    setRecordingModels([])
    setError('')
    try {
      const payload = await apiRequest<{ recording: AdminRecording; models: ModelProvider[] }>(`/admin/recordings/${recording.id}/models`, {
        token: auth.access_token,
      })
      const speech = payload.models.filter((model) => model.model_kind === 'speech')
      const text = payload.models.filter((model) => model.model_kind === 'text')
      setRecordingModels(payload.models)
      setRecordingForm({
        providerId: speech.find((model) => model.is_default)?.id || speech[0]?.id || '',
        textProviderId: text.find((model) => model.is_default)?.id || text[0]?.id || '',
        language: 'Chinese',
        speakerMode: 'single',
        diarize: true,
      })
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '录音模型加载失败。')
      setRecordingSetup(null)
    }
  }

  const createRecordingTask = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!recordingSetup) return
    setSaving(true)
    setError('')
    try {
      await apiRequest<AdminJob>(`/admin/recordings/${recordingSetup.id}/jobs`, {
        method: 'POST',
        token: auth.access_token,
        body: {
          provider_id: recordingForm.providerId,
          text_provider_id: recordingForm.textProviderId,
          language: recordingForm.language || null,
          speaker_mode: recordingForm.speakerMode,
          diarize: recordingForm.diarize,
        },
      })
      setNotice(`已为“${recordingSetup.original_name}”创建转写任务。`)
      setRecordingSetup(null)
      await load()
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '转写任务创建失败。')
    } finally {
      setSaving(false)
    }
  }

  const navigate = (view: AdminView) => {
    setActiveView(view)
    setSelectedJob(null)
  }

  return (
    <TooltipProvider delayDuration={100}>
      <SidebarProvider>
        <AdminSidebar auth={auth} activeView={activeView} onSelect={navigate} />
        <SidebarInset>
          <header className="sticky top-0 z-20 flex h-12 items-center justify-between border-b-2 border-border bg-card px-3">
            <div className="flex min-w-0 items-center gap-3">
              <SidebarTrigger />
              <div className="h-5 w-0.5 bg-border" />
              <p className="truncate font-head text-sm">{viewTitles[activeView]}</p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => setPasswordOpen(true)}><KeyRound />修改密码</Button>
              <Button variant="ghost" size="sm" onClick={onLogout}><LogOut />退出管理员</Button>
            </div>
          </header>
          <main className="pixel-grid flex-1 overflow-y-auto p-4 sm:p-6">
            <div className="mx-auto w-full max-w-7xl space-y-6">
              {error && <Alert status="error"><AlertTitle>管理操作失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
              {notice && <Alert status="success"><AlertTitle>操作完成</AlertTitle><AlertDescription>{notice}</AlertDescription></Alert>}
              {credential && (
                <Alert status="success">
                  <AlertTitle>一次性初始账户</AlertTitle>
                  <AlertDescription>
                    组织：{credential.organization} · 登录名：{credential.login} · 初始密码：
                    <strong className="select-all">{credential.password}</strong><br />
                    请通过安全渠道交付；离开本页后不再显示。
                  </AlertDescription>
                </Alert>
              )}

              {activeView === 'overview' && (
                <Overview
                  tenants={tenants}
                  jobs={jobs}
                  recordings={recordings}
                  onNavigate={navigate}
                />
              )}
              {activeView === 'organizations' && (
                <Organizations
                  tenants={tenants}
                  saving={saving}
                  tenantForm={tenantForm}
                  userForm={userForm}
                  setTenantForm={setTenantForm}
                  setUserForm={setUserForm}
                  onCreateTenant={createTenant}
                  onCreateUser={createUser}
                  onToggleTenant={toggleTenant}
                  onToggleUser={toggleUser}
                  onResetUser={setPendingReset}
                  onDeleteTenant={setPendingDelete}
                />
              )}
              {activeView === 'tasks' && (
                <Tasks
                  jobs={jobs}
                  selectedJob={selectedJob}
                  onOpen={openJob}
                  onClose={() => setSelectedJob(null)}
                  onToggleVisibility={toggleJobVisibility}
                  onDownload={downloadJob}
                  onRetry={retryJob}
                />
              )}
              {activeView === 'recordings' && <Recordings recordings={recordings} onTranscribe={openRecordingTask} />}
            </div>
          </main>
        </SidebarInset>
      </SidebarProvider>

      <AlertDialog open={Boolean(pendingDelete)} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogTitle>确认删除组织？</AlertDialogTitle>
          <AlertDialogDescription>
            将禁用该组织全部账户，并永久删除其转写任务、转写文本和说话人分段。
            已上传的原始录音文件及文件记录会被保留，仍可由超级管理员在“全部录音文件”中查看。
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => void deleteTenant()}>删除组织与转写任务</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={Boolean(pendingReset)} onOpenChange={(open) => !open && setPendingReset(null)}>
        <AlertDialogContent>
          <AlertDialogTitle>重置用户密码？</AlertDialogTitle>
          <AlertDialogDescription>
            将立即使该用户的旧密码和全部刷新会话失效，并生成一个只显示一次的随机初始密码。
            用户使用随机密码登录后，必须设置新密码并重新登录。
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => void resetUserPassword()}>生成随机密码</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <PasswordChangeSheet
        open={passwordOpen}
        onOpenChange={setPasswordOpen}
        endpoint="/admin/auth/change-password"
        token={auth.access_token}
        onChanged={onLogout}
        title="修改超级管理员密码"
      />

      <RecordingTaskSheet
        recording={recordingSetup}
        models={recordingModels}
        form={recordingForm}
        setForm={setRecordingForm}
        saving={saving}
        onClose={() => setRecordingSetup(null)}
        onSubmit={createRecordingTask}
      />
    </TooltipProvider>
  )
}

function PageIntro({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <div><p className="font-mono text-xs tracking-[0.2em] text-muted-foreground">{eyebrow}</p><h1 className="mt-2 font-head text-3xl">{title}</h1><p className="mt-2 max-w-3xl text-muted-foreground">{description}</p></div>
}

function Overview({
  tenants,
  jobs,
  recordings,
  onNavigate,
}: {
  tenants: AdminTenant[]
  jobs: AdminJob[]
  recordings: AdminRecording[]
  onNavigate: (view: AdminView) => void
}) {
  const cards = [
    { label: '活跃组织', value: tenants.filter((item) => item.status === 'active').length, icon: Building2, view: 'organizations' as const },
    { label: '平台账户', value: tenants.reduce((count, item) => count + item.users.length, 0), icon: Users, view: 'organizations' as const },
    { label: '转写任务', value: jobs.length, icon: FileText, view: 'tasks' as const },
    { label: '保留录音', value: recordings.length, icon: HardDrive, view: 'recordings' as const },
  ]
  return (
    <>
      <PageIntro eyebrow="PLATFORM / OVERVIEW" title="超级管理员总览" description="跨组织查看账户、转写任务与原始录音文件。各组织私有数据彼此隔离，平台管理员拥有审计视图。" />
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => {
          const Icon = card.icon
          return (
            <Card key={card.label} className="border-4 shadow-[6px_6px_0_0_var(--border)]">
              <CardHeader><div className="flex items-center justify-between"><CardDescription>{card.label}</CardDescription><Icon className="size-6" /></div><CardTitle className="font-head text-4xl">{card.value}</CardTitle></CardHeader>
              <CardContent><Button className="w-full" variant="outline" onClick={() => onNavigate(card.view)}>进入管理</Button></CardContent>
            </Card>
          )
        })}
      </div>
      <Card className="border-4 bg-primary shadow-[7px_7px_0_0_var(--border)]">
        <CardHeader><CardTitle className="flex items-center gap-3 font-head text-2xl"><ShieldCheck />数据边界</CardTitle></CardHeader>
        <CardContent className="grid gap-4 text-sm md:grid-cols-3">
          <p className="border-2 border-border bg-background p-4"><strong>私有任务</strong><br />仅任务所属组织和超级管理员可见。</p>
          <p className="border-2 border-border bg-background p-4"><strong>公开任务</strong><br />所有已登录且状态正常的用户可见。</p>
          <p className="border-2 border-border bg-background p-4"><strong>删除组织</strong><br />清理转写数据，但保留原始录音。</p>
        </CardContent>
      </Card>
    </>
  )
}

type OrganizationProps = {
  tenants: AdminTenant[]
  saving: boolean
  tenantForm: { name: string; slug: string; displayName: string; email: string }
  userForm: { tenantId: string; displayName: string; email: string; role: string }
  setTenantForm: (value: OrganizationProps['tenantForm']) => void
  setUserForm: (value: OrganizationProps['userForm']) => void
  onCreateTenant: (event: FormEvent<HTMLFormElement>) => void
  onCreateUser: (event: FormEvent<HTMLFormElement>) => void
  onToggleTenant: (tenant: AdminTenant) => void
  onToggleUser: (user: AdminUser) => void
  onResetUser: (user: AdminUser) => void
  onDeleteTenant: (tenant: AdminTenant) => void
}

function Organizations(props: OrganizationProps) {
  const { tenants, saving, tenantForm, userForm, setTenantForm, setUserForm } = props
  return (
    <>
      <PageIntro eyebrow="PLATFORM / ORGANIZATIONS" title="组织和账户" description="由超级管理员统一开通组织及账户。随机初始密码只显示一次，用户首次登录后必须改密并重新登录。" />
      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="border-4 shadow-[6px_6px_0_0_var(--border)]">
          <CardHeader className="border-b-2 border-border bg-primary"><CardTitle className="flex items-center gap-2 font-head text-2xl"><Building2 />注册组织</CardTitle><CardDescription>同时创建组织负责人账户。</CardDescription></CardHeader>
          <CardContent className="pt-6">
            <form className="space-y-5" onSubmit={props.onCreateTenant}>
              <div className="grid gap-5 sm:grid-cols-2">
                <div className="space-y-2"><Label htmlFor="tenant-name">组织名称</Label><Input className="h-12" id="tenant-name" required value={tenantForm.name} onChange={(event) => setTenantForm({ ...tenantForm, name: event.target.value })} /></div>
                <div className="space-y-2"><Label htmlFor="tenant-code">租户标识</Label><Input className="h-12" id="tenant-code" required pattern="[a-z0-9][a-z0-9-]{1,61}[a-z0-9]" value={tenantForm.slug} onChange={(event) => setTenantForm({ ...tenantForm, slug: event.target.value })} /></div>
                <div className="space-y-2"><Label htmlFor="owner-name">负责人姓名</Label><Input className="h-12" id="owner-name" required value={tenantForm.displayName} onChange={(event) => setTenantForm({ ...tenantForm, displayName: event.target.value })} /></div>
                <div className="space-y-2"><Label htmlFor="owner-email">登录邮箱</Label><Input className="h-12" id="owner-email" type="email" required value={tenantForm.email} onChange={(event) => setTenantForm({ ...tenantForm, email: event.target.value })} /></div>
              </div>
              <Button className="h-12 w-full" disabled={saving}><UserPlus />创建组织和负责人</Button>
            </form>
          </CardContent>
        </Card>
        <Card className="border-4 shadow-[6px_6px_0_0_var(--border)]">
          <CardHeader className="border-b-2 border-border bg-accent"><CardTitle className="flex items-center gap-2 font-head text-2xl"><Users />添加账户</CardTitle><CardDescription>向已有组织增加成员、管理员或负责人。</CardDescription></CardHeader>
          <CardContent className="pt-6">
            <form className="space-y-5" onSubmit={props.onCreateUser}>
              <div className="space-y-2"><Label>所属组织</Label><Select value={userForm.tenantId} onValueChange={(value) => setUserForm({ ...userForm, tenantId: value })}><SelectTrigger className="h-12"><SelectValue placeholder="选择组织" /></SelectTrigger><SelectContent><SelectGroup>{tenants.map((tenant) => <SelectItem key={tenant.id} value={tenant.id}>{tenant.name} · {tenant.slug}</SelectItem>)}</SelectGroup></SelectContent></Select></div>
              <div className="grid gap-5 sm:grid-cols-2">
                <div className="space-y-2"><Label htmlFor="new-user-name">用户姓名</Label><Input className="h-12" id="new-user-name" required value={userForm.displayName} onChange={(event) => setUserForm({ ...userForm, displayName: event.target.value })} /></div>
                <div className="space-y-2"><Label htmlFor="new-user-email">登录邮箱</Label><Input className="h-12" id="new-user-email" type="email" required value={userForm.email} onChange={(event) => setUserForm({ ...userForm, email: event.target.value })} /></div>
              </div>
              <div className="space-y-2"><Label>租户角色</Label><Select value={userForm.role} onValueChange={(value) => setUserForm({ ...userForm, role: value })}><SelectTrigger className="h-12"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="member">普通成员</SelectItem><SelectItem value="admin">租户管理员</SelectItem><SelectItem value="owner">组织负责人</SelectItem></SelectGroup></SelectContent></Select></div>
              <Button className="h-12 w-full" disabled={saving || !userForm.tenantId}><UserPlus />创建用户账户</Button>
            </form>
          </CardContent>
        </Card>
      </div>
      <section className="space-y-5">
        <div className="flex items-end justify-between"><h2 className="font-head text-3xl">已开通组织</h2><Badge variant="outline">{tenants.length} 个组织</Badge></div>
        {tenants.map((tenant) => (
          <Card key={tenant.id} className="border-4 shadow-[5px_5px_0_0_var(--border)]">
            <CardHeader className="border-b-2 border-border">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div><div className="flex flex-wrap items-center gap-2"><CardTitle className="font-head text-2xl">{tenant.name}</CardTitle><Badge className={tenant.status === 'active' ? 'bg-green-200 text-foreground' : 'bg-yellow-200 text-foreground'} variant="outline">{tenant.status === 'active' ? '正常' : '已禁用'}</Badge></div><CardDescription className="mt-2">{tenant.slug} · {tenant.users.length} 个账户</CardDescription></div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" onClick={() => props.onToggleTenant(tenant)}><Power />{tenant.status === 'active' ? '禁用组织' : '启用组织'}</Button>
                  <Button variant="destructive" onClick={() => props.onDeleteTenant(tenant)}><Trash2 />删除组织</Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="grid gap-4 pt-5 lg:grid-cols-2">
              {tenant.users.map((user) => (
                <div key={user.id} className="flex flex-wrap items-center justify-between gap-4 border-2 border-border bg-muted/30 p-4">
                  <div><p className="font-bold">{user.display_name}</p><p className="break-all font-mono text-xs">{user.email}</p><p className="mt-2 text-xs text-muted-foreground">{user.must_change_password ? '等待首次改密' : '密码已初始化'} · {user.membership_status}</p></div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" onClick={() => props.onResetUser(user)}><KeyRound />重置密码</Button>
                    <Button size="sm" variant={user.status === 'active' ? 'destructive' : 'outline'} onClick={() => props.onToggleUser(user)}>{user.status === 'active' ? '禁用账户' : '启用账户'}</Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        ))}
      </section>
    </>
  )
}

function Tasks({
  jobs,
  selectedJob,
  onOpen,
  onClose,
  onToggleVisibility,
  onDownload,
  onRetry,
}: {
  jobs: AdminJob[]
  selectedJob: AdminJobDetail | null
  onOpen: (jobId: string) => void
  onClose: () => void
  onToggleVisibility: (job: AdminJobDetail) => void
  onDownload: (job: AdminJobDetail, format: 'txt' | 'json' | 'srt' | 'vtt' | 'html') => void
  onRetry: (job: AdminJobDetail) => void
}) {
  if (selectedJob) {
    return (
      <>
        <Button variant="outline" onClick={onClose}>← 返回全部任务</Button>
        <Card className="border-4 shadow-[7px_7px_0_0_var(--border)]">
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div><div className="flex flex-wrap gap-2"><Badge>{selectedJob.tenant_name}</Badge><Badge variant="outline">{selectedJob.status}</Badge></div><CardTitle className="mt-3 break-all font-head text-3xl">{selectedJob.source_path.split('/').at(-1)}</CardTitle><CardDescription className="mt-2">{selectedJob.created_by_name} · {selectedJob.created_by_email}</CardDescription></div>
              <Button variant={selectedJob.visibility === 'public' ? 'default' : 'outline'} onClick={() => onToggleVisibility(selectedJob)}>{selectedJob.visibility === 'public' ? <Globe2 /> : <Lock />}{selectedJob.visibility === 'public' ? '公开任务' : '私有任务'}</Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <TaskIdentifier taskId={selectedJob.task_id} />
            <div className="grid gap-4 border-2 border-border bg-muted/30 p-4 text-sm sm:grid-cols-2">
              <div><p className="text-muted-foreground">语音模型</p><TaskModelName name={selectedJob.provider_name} deleted={selectedJob.provider_deleted} /></div>
              <div><p className="text-muted-foreground">文本模型</p><TaskModelName name={selectedJob.text_provider_name ?? '未配置'} deleted={selectedJob.text_provider_deleted} /></div>
            </div>
            {selectedJob.has_asr_checkpoint && selectedJob.status !== 'completed' && <Alert status="success"><AlertTitle>语音解析结果已保存</AlertTitle><AlertDescription>文本模型失败时可以直接重试文本整理，不会重新调用语音模型。</AlertDescription></Alert>}
            {selectedJob.status === 'failed' && <Alert variant="destructive"><AlertTitle>执行失败 · {selectedJob.task_id}</AlertTitle><AlertDescription>{selectedJob.error_message || '任务执行失败，请使用任务 ID 检索 Worker 日志。'}</AlertDescription></Alert>}
            {selectedJob.status === 'failed' && <Button variant="outline" onClick={() => onRetry(selectedJob)}><RotateCcw />{selectedJob.has_asr_checkpoint ? '重试文本整理' : '重试语音解析'}</Button>}
            {selectedJob.status === 'completed' && <div className="flex flex-wrap gap-3">{(['txt', 'json', 'srt', 'vtt', 'html'] as const).map((format) => <Button key={format} variant="outline" onClick={() => onDownload(selectedJob, format)}><Download />{format.toUpperCase()}</Button>)}</div>}
            {selectedJob.transcript_text ? <DialogueTranscript transcript={selectedJob.transcript_text} /> : <div className="border-2 border-dashed border-border p-8 text-center text-muted-foreground">暂无转写内容</div>}
          </CardContent>
        </Card>
      </>
    )
  }

  return (
    <>
      <PageIntro eyebrow="PLATFORM / TRANSCRIPTS" title="全部租户转写任务" description="超级管理员可跨组织审计任务、以左右对话布局查看转写结果、调整公开范围，并按用户侧相同格式导出。" />
      <div className="grid gap-4">
        {jobs.map((job) => (
          <Card key={job.id} className="border-4 shadow-[4px_4px_0_0_var(--border)]">
            <CardContent className="grid gap-4 p-5 md:grid-cols-[1fr_auto] md:items-center">
              <div><div className="flex flex-wrap gap-2"><Badge>{job.tenant_name}</Badge><Badge variant="outline">{job.status}</Badge><Badge className={job.visibility === 'public' ? 'bg-green-200 text-foreground' : ''} variant="outline">{job.visibility === 'public' ? <Globe2 /> : <Lock />}{job.visibility === 'public' ? '公开' : '私有'}</Badge></div><p className="mt-3 break-all font-bold">{job.source_path.split('/').at(-1)}</p><p className="mt-1 font-mono text-xs">{job.created_by_name} · {job.created_by_email}</p><TaskIdentifier className="mt-3" taskId={job.task_id} /><p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{job.transcript_text || '暂无转写内容'}</p></div>
              <Button variant="outline" onClick={() => onOpen(job.id)}><FileText />查看转写</Button>
            </CardContent>
          </Card>
        ))}
        {jobs.length === 0 && <Card className="border-4"><CardContent className="grid min-h-64 place-items-center text-muted-foreground">暂无转写任务</CardContent></Card>}
      </div>
    </>
  )
}

function Recordings({
  recordings,
  onTranscribe,
}: {
  recordings: AdminRecording[]
  onTranscribe: (recording: AdminRecording) => void
}) {
  return (
    <>
      <PageIntro eyebrow="PLATFORM / RECORDINGS" title="全部录音文件" description="集中查看所有组织上传的原始录音。组织被删除后，其录音仍保留并在此标记为“已删除组织”。" />
      <div className="grid gap-4 lg:grid-cols-2">
        {recordings.map((recording) => (
          <Card key={recording.id} className="border-4 shadow-[4px_4px_0_0_var(--border)]">
            <CardHeader><div className="flex flex-wrap gap-2"><Badge>{recording.tenant_name}</Badge><Badge className={recording.tenant_status === 'deleted' ? 'bg-red-200 text-foreground' : ''} variant="outline">{recording.tenant_status === 'deleted' ? '已删除组织' : recording.tenant_status === 'suspended' ? '已禁用组织' : '正常组织'}</Badge></div><CardTitle className="mt-3 break-all text-xl">{recording.original_name}</CardTitle><CardDescription className="break-all">{recording.relative_path}</CardDescription></CardHeader>
            <CardContent className="space-y-5 border-t-2 border-border pt-5">
              <div className="grid grid-cols-2 gap-4 text-sm"><div><p className="text-muted-foreground">文件大小</p><strong>{formatBytes(recording.size_bytes)}</strong></div><div><p className="text-muted-foreground">关联任务</p><strong>{recording.job_count}</strong></div><div><p className="text-muted-foreground">上传时间</p><strong>{new Date(recording.created_at).toLocaleString()}</strong></div><div><p className="text-muted-foreground">媒体类型</p><strong>{recording.media_type || '未知'}</strong></div></div>
              <Button className="w-full" onClick={() => onTranscribe(recording)}><AudioLines />配置并开始转写</Button>
            </CardContent>
          </Card>
        ))}
        {recordings.length === 0 && <Card className="border-4 lg:col-span-2"><CardContent className="grid min-h-64 place-items-center"><div className="text-center"><AudioLines className="mx-auto size-10" /><p className="mt-4 font-head text-xl">暂无录音文件</p></div></CardContent></Card>}
      </div>
    </>
  )
}

type RecordingTaskForm = {
  providerId: string
  textProviderId: string
  language: string
  speakerMode: string
  diarize: boolean
}

function RecordingTaskSheet({
  recording,
  models,
  form,
  setForm,
  saving,
  onClose,
  onSubmit,
}: {
  recording: AdminRecording | null
  models: ModelProvider[]
  form: RecordingTaskForm
  setForm: (form: RecordingTaskForm) => void
  saving: boolean
  onClose: () => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
  const speechModels = models.filter((model) => model.model_kind === 'speech')
  const textModels = models.filter((model) => model.model_kind === 'text')
  const ready = Boolean(form.providerId && form.textProviderId)

  return (
    <Sheet open={Boolean(recording)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="overflow-y-auto border-l-4 shadow-[-8px_0_0_0_var(--border)] sm:max-w-xl">
        <SheetHeader className="border-b-4 border-border bg-primary p-6">
          <div className="mb-3 grid size-12 place-items-center border-2 border-border bg-background shadow-[4px_4px_0_0_var(--border)]"><AudioLines /></div>
          <SheetTitle className="break-all font-head text-2xl">配置转写任务</SheetTitle>
          <SheetDescription>{recording?.tenant_name} · {recording?.original_name}</SheetDescription>
        </SheetHeader>
        <form className="space-y-5 p-6" onSubmit={onSubmit}>
          {models.length === 0 ? (
            <Alert status="warning"><AlertTitle>暂无可用模型</AlertTitle><AlertDescription>该组织需要先配置可用的语音模型和文本模型。</AlertDescription></Alert>
          ) : (
            <>
              <div className="space-y-2"><Label>语音模型</Label><Select value={form.providerId} onValueChange={(value) => setForm({ ...form, providerId: value })}><SelectTrigger className="h-12"><SelectValue placeholder="选择语音模型" /></SelectTrigger><SelectContent><SelectGroup>{speechModels.map((model) => <SelectItem key={model.id} value={model.id}>{model.name} · {model.model_name}</SelectItem>)}</SelectGroup></SelectContent></Select></div>
              <div className="space-y-2"><Label>文本模型</Label><Select value={form.textProviderId} onValueChange={(value) => setForm({ ...form, textProviderId: value })}><SelectTrigger className="h-12"><SelectValue placeholder="选择文本模型" /></SelectTrigger><SelectContent><SelectGroup>{textModels.map((model) => <SelectItem key={model.id} value={model.id}>{model.name} · {model.model_name}</SelectItem>)}</SelectGroup></SelectContent></Select></div>
              <div className="space-y-2"><Label htmlFor="admin-task-language">语言</Label><Input className="h-12" id="admin-task-language" value={form.language} onChange={(event) => setForm({ ...form, language: event.target.value })} placeholder="Chinese" /></div>
              <div className="space-y-2"><Label>说话人数</Label><Select value={form.speakerMode} onValueChange={(value) => setForm({ ...form, speakerMode: value })}><SelectTrigger className="h-12"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="single">单人</SelectItem><SelectItem value="double">双人</SelectItem><SelectItem value="multiple">多人</SelectItem></SelectGroup></SelectContent></Select></div>
              <Button type="button" className="h-12 w-full" variant={form.diarize ? 'default' : 'outline'} onClick={() => setForm({ ...form, diarize: !form.diarize })}>{form.diarize ? '说话人识别：开启' : '说话人识别：关闭'}</Button>
            </>
          )}
          <Button className="h-12 w-full" disabled={saving || !ready}><AudioLines />{saving ? '创建中…' : '创建转写任务'}</Button>
        </form>
      </SheetContent>
    </Sheet>
  )
}
