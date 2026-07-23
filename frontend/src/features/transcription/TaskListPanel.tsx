import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Clock3, Eye, LoaderCircle, RotateCcw, Trash2, XCircle } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { apiRequest, type AuthPayload, type TranscriptionJob } from '@/lib/api'

import { TaskModelName } from './TaskModelName'

type Props = { session: AuthPayload; onOpenTask: (jobId: string) => void }

const speakerModeLabel = { single: '单人', double: '双人', multiple: '多人' } as const

function statusLabel(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'processing') return '语音解析中'
  if (status === 'refining') return '文本整理中'
  if (status === 'queued') return '等待中'
  if (status === 'failed') return '失败'
  if (status === 'cancelled') return '已取消'
  return status
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'completed') return <CheckCircle2 className="size-5" />
  if (status === 'processing' || status === 'refining') return <LoaderCircle className="size-5 animate-spin" />
  if (status === 'failed' || status === 'cancelled') return <XCircle className="size-5" />
  return <Clock3 className="size-5" />
}

export function TaskListPanel({ session, onOpenTask }: Props) {
  const [jobs, setJobs] = useState<TranscriptionJob[]>([])
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [deleting, setDeleting] = useState('')
  const [pendingDelete, setPendingDelete] = useState<TranscriptionJob | null>(null)

  const load = useCallback(() => {
    apiRequest<TranscriptionJob[]>('/jobs', { token: session.access_token })
      .then((items) => {
        setJobs(items)
        setUpdatedAt(new Date())
      })
      .catch((reason: Error) => setError(reason.message))
  }, [session.access_token])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 5000)
    return () => window.clearInterval(timer)
  }, [load])

  const action = async (job: TranscriptionJob, name: 'cancel' | 'retry') => {
    try {
      await apiRequest(`/jobs/${job.id}/${name}`, { method: 'POST', token: session.access_token })
      load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '任务操作失败。')
    }
  }

  const deleteJob = async (job: TranscriptionJob) => {
    setDeleting(job.id)
    setPendingDelete(null)
    setError('')
    try {
      await apiRequest(`/jobs/${job.id}`, { method: 'DELETE', token: session.access_token })
      load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除任务失败。')
    } finally {
      setDeleting('')
    }
  }

  return (
    <div className="mx-auto w-full max-w-7xl space-y-7">
      <AlertDialog open={pendingDelete !== null} onOpenChange={(open) => { if (!open) setPendingDelete(null) }}>
        <AlertDialogContent>
          <AlertDialogTitle>删除这个转写任务？</AlertDialogTitle>
          <AlertDialogDescription>“{pendingDelete?.source_path.split('/').at(-1)}”的任务、转写文本与分段结果将被永久删除。只有在没有其他任务引用时，源文件才会一并删除。此操作无法撤销。</AlertDialogDescription>
          <AlertDialogFooter><AlertDialogCancel>取消</AlertDialogCancel><AlertDialogAction onClick={() => { if (pendingDelete) void deleteJob(pendingDelete) }}><Trash2 />确认删除</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="font-mono text-xs tracking-[0.25em] text-muted-foreground">WORKSPACE / TASKS</p><h1 className="mt-2 font-head text-4xl">转写任务</h1><p className="mt-2 text-base text-muted-foreground">每个录音对应一个独立任务；列表每 5 秒刷新一次。</p></div>
        <div className="border-2 border-border bg-background px-4 py-3 font-mono text-xs shadow-[3px_3px_0_0_var(--border)]">最近报告：{updatedAt?.toLocaleTimeString() ?? '等待中'}</div>
      </div>
      {error && <Alert variant="destructive"><AlertTitle>任务加载失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
      {jobs.length === 0 ? <div className="grid min-h-64 place-items-center border-4 border-dashed border-border bg-muted/40 p-8 text-center font-mono text-sm">暂无转写任务</div> : <div className="grid gap-5 xl:grid-cols-2">{jobs.map((job) => {
        const active = ['queued', 'processing', 'refining'].includes(job.status)
        const progress = job.status === 'completed' ? 100 : job.progress_percent
        return <Card key={job.id} className="border-4 shadow-[6px_6px_0_0_var(--border)] [--card-spacing:--spacing(6)]">
          <CardHeader className="gap-3"><div className="flex items-start justify-between gap-4"><div className="min-w-0"><CardTitle className="truncate font-head text-2xl">{job.source_path.split('/').at(-1)}</CardTitle><CardDescription className="mt-2 break-all font-mono text-xs">{job.source_path}</CardDescription></div><Badge className={job.status === 'completed' ? 'bg-green-300 text-foreground' : job.status === 'failed' ? 'bg-red-300 text-foreground' : ''} variant="outline"><StatusIcon status={job.status} />{statusLabel(job.status)}</Badge></div></CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-3 border-2 border-border bg-muted/30 p-4 font-mono text-sm sm:grid-cols-2"><span>语音模型：<TaskModelName name={job.provider_name} deleted={job.provider_deleted} /></span><span>文本模型：<TaskModelName name={job.text_provider_name ?? '未配置'} deleted={job.text_provider_deleted} /></span><span>人数：<strong>{speakerModeLabel[job.speaker_mode]}</strong></span><span>进度：<strong>{progress}%</strong></span></div>
            {job.has_asr_checkpoint && job.status !== 'completed' && <Alert status="success"><AlertTitle>语音解析结果已保存</AlertTitle><AlertDescription>{job.status === 'failed' ? '文本模型调用失败；重试只会重新执行文本整理，不会再次调用语音模型。' : '正在使用已保存的原始文本、时间戳和说话人提示进行文本整理。'}</AlertDescription></Alert>}
            <Progress value={progress} className={active ? 'animate-pulse' : ''} />
            <div className="flex flex-wrap gap-3"><Button onClick={() => onOpenTask(job.id)}><Eye />查看独立任务页面</Button><Button variant="destructive" disabled={deleting === job.id} onClick={() => setPendingDelete(job)}><Trash2 />{deleting === job.id ? '删除中…' : '删除'}</Button>{active && <Button variant="outline" onClick={() => action(job, 'cancel')}>取消</Button>}{job.status === 'failed' && <Button variant="outline" onClick={() => action(job, 'retry')}><RotateCcw />{job.has_asr_checkpoint ? '重试文本整理' : '重试语音解析'}</Button>}</div>
          </CardContent>
        </Card>
      })}</div>}
    </div>
  )
}
