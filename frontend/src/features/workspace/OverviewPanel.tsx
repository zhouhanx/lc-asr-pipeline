import { useCallback, useEffect, useState } from 'react'
import { Activity, CheckCircle2, Clock3, FileClock, Layers3, LoaderCircle, type LucideIcon } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { apiRequest, type AuthPayload, type WorkspaceSummary } from '@/lib/api'

type OverviewPanelProps = {
  session: AuthPayload
  onNavigate: (item: 'tasks' | 'models' | 'history') => void
}

type OverviewMetric = {
  label: string
  value: number | undefined
  note: string
  icon: LucideIcon
  color: string
  target: 'tasks' | 'models' | 'history' | null
  actionLabel: string | null
}

export function OverviewPanel({ session, onNavigate }: OverviewPanelProps) {
  const [summary, setSummary] = useState<WorkspaceSummary | null>(null)
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)

  const load = useCallback(() => {
    apiRequest<WorkspaceSummary>('/workspace/summary', { token: session.access_token })
      .then((value) => {
        setSummary(value)
        setError('')
        setUpdatedAt(new Date())
      })
      .catch((reason: Error) => setError(reason.message))
  }, [session.access_token])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 5000)
    return () => window.clearInterval(timer)
  }, [load])

  const metrics: OverviewMetric[] = [
    { label: '正在运行', value: summary?.running_tasks, note: `排队 ${summary?.queued_tasks ?? 0}`, icon: LoaderCircle, color: 'bg-primary', target: null, actionLabel: null },
    { label: '已经完成', value: summary?.completed_tasks, note: 'SUCCESS TASKS', icon: CheckCircle2, color: 'bg-green-300', target: 'tasks', actionLabel: '查看已完成的转写任务' },
    { label: '可用模型', value: summary?.available_models, note: 'LOCAL + API', icon: Layers3, color: 'bg-blue-300', target: 'models', actionLabel: '查看可用模型' },
    { label: '历史文件', value: summary?.historical_files, note: 'DEDUPLICATED', icon: FileClock, color: 'bg-pink-300', target: 'history', actionLabel: '查看历史文件' },
  ]

  return <div className="w-full space-y-5 px-[15px]">
    <section className="w-full border-4 border-border bg-secondary px-6 py-5 text-secondary-foreground shadow-[7px_7px_0_0_var(--border)] sm:px-7 sm:py-6">
      <div className="flex flex-wrap items-center justify-between gap-5"><div><p className="font-mono text-[10px] tracking-[0.28em] text-white/70">TENANT WORKSPACE</p><h1 className="mt-2 font-head text-3xl uppercase sm:text-4xl">你好，{session.user.display_name}</h1><p className="mt-3 max-w-4xl text-sm leading-6 text-white/75">这里是 {session.tenant.name} 的语音识别工作空间。提交、监测、历史文件和独立任务详情均限定在当前租户。</p></div><Badge className="bg-primary px-3 py-1.5 text-sm text-foreground" variant="outline">LIVE WORKSPACE</Badge></div>
    </section>
    {error && <Alert variant="destructive"><AlertTitle>统计加载失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
    <section className="grid w-full gap-5 sm:grid-cols-2 xl:grid-cols-4">{metrics.map((metric) => { const Icon = metric.icon; const target = metric.target; const card = <Card className={`h-full min-h-36 border-4 shadow-[5px_5px_0_0_var(--border)] [--card-spacing:--spacing(5)] ${target ? 'transition-transform group-hover:-translate-y-0.5 group-focus-visible:-translate-y-0.5' : ''}`}><CardContent className="flex h-full items-center justify-between gap-4"><div><p className="font-head text-base">{metric.label}</p><p className="mt-2 font-head text-4xl">{metric.value ?? '—'}</p><p className="mt-2 font-mono text-[10px] text-muted-foreground">{metric.note}</p></div><div className={`grid size-12 shrink-0 place-items-center border-3 border-border shadow-[3px_3px_0_0_var(--border)] ${metric.color}`}><Icon className={`size-6 ${metric.label === '正在运行' && (summary?.running_tasks ?? 0) > 0 ? 'animate-spin' : ''}`} /></div></CardContent></Card>; return target ? <button key={metric.label} type="button" aria-label={metric.actionLabel ?? undefined} className="group h-full cursor-pointer text-left focus-visible:outline-4 focus-visible:outline-offset-4 focus-visible:outline-primary" onClick={() => onNavigate(target)}>{card}</button> : <div key={metric.label} className="h-full">{card}</div> })}</section>
    <section className="grid w-full items-stretch gap-5 lg:grid-cols-2">
      <Card className="h-full border-4 shadow-[5px_5px_0_0_var(--border)] [--card-spacing:--spacing(5)]"><CardHeader className="gap-1"><CardTitle className="flex items-center gap-3 font-head text-xl"><Activity className="size-6" />工作空间状态</CardTitle><CardDescription>统计数据每 5 秒刷新一次。</CardDescription></CardHeader><CardContent><div className="flex min-h-28 items-center justify-between gap-5 border-4 border-dashed border-border bg-muted/40 px-5 py-4"><div><p className="font-head text-lg">LAST REPORT</p><p className="mt-1 font-mono text-xs text-muted-foreground">最近一次任务与统计报告</p></div><div className="flex shrink-0 items-center gap-3 border-2 border-border bg-background px-4 py-3 shadow-[3px_3px_0_0_var(--border)]"><Clock3 className="size-6" /><strong className="font-mono text-sm">{updatedAt?.toLocaleTimeString() ?? '正在连接…'}</strong></div></div></CardContent></Card>
      <Card className="h-full border-4 shadow-[5px_5px_0_0_var(--border)] [--card-spacing:--spacing(5)]"><CardHeader className="gap-1"><CardTitle className="font-head text-xl">系统状态</CardTitle><CardDescription>基础服务与模型配置。</CardDescription></CardHeader><CardContent className="grid gap-x-6 gap-y-3 font-mono text-xs sm:grid-cols-2">{[['FastAPI', 'ONLINE'], ['DB', 'ONLINE'], ['TASK POLLING', '5 SECONDS'], ['MODEL CONFIG', `${summary?.available_models ?? 0} READY`]].map(([service, state]) => <div key={service} className="flex min-h-12 items-center justify-between gap-3 border-b-2 border-border"><span>{service}</span><strong className="text-green-700">{state}</strong></div>)}</CardContent></Card>
    </section>
  </div>
}
