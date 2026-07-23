import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Clock3, Eye, FileImage, FileText, LoaderCircle, RotateCcw, Trash2, XCircle } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { apiRequest, type AuthPayload, type OCRJob } from '@/lib/api'
import { TaskIdentifier } from '@/features/transcription/TaskIdentifier'

import { originalDocumentName, summarizeDocumentName } from './documentName'

type Props = { session: AuthPayload; onOpenTask: (jobId: string) => void }

function statusLabel(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'processing') return 'OCR 解析中'
  if (status === 'refining') return '文本校对中'
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

export function OCRTaskListPanel({ session, onOpenTask }: Props) {
  const [jobs, setJobs] = useState<OCRJob[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  const load = useCallback(() => {
    apiRequest<OCRJob[]>('/ocr/jobs', { token: session.access_token })
      .then(setJobs)
      .catch((reason: Error) => setError(reason.message))
  }, [session.access_token])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 5000)
    return () => window.clearInterval(timer)
  }, [load])

  const action = async (job: OCRJob, name: 'cancel' | 'retry' | 'delete') => {
    setBusy(job.id)
    setError('')
    try {
      await apiRequest(`/ocr/jobs/${job.id}${name === 'delete' ? '' : `/${name}`}`, {
        method: name === 'delete' ? 'DELETE' : 'POST',
        token: session.access_token,
      })
      load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'OCR 任务操作失败。')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="mx-auto w-full max-w-[1920px] space-y-7">
      <div><p className="font-mono text-xs tracking-[0.25em] text-muted-foreground">WORKSPACE / OCR</p><h1 className="mt-2 font-head text-4xl">OCR 任务</h1><p className="mt-2 text-base text-muted-foreground">每个 PDF 或图片对应一个独立解析任务；列表每 5 秒刷新。</p></div>
      {error && <Alert variant="destructive"><AlertTitle>OCR 任务错误</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
      {jobs.length === 0 ? <div className="grid min-h-64 place-items-center border-4 border-dashed border-border bg-muted/40 p-8 font-mono text-sm">暂无 OCR 任务</div> : <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">{jobs.map((job) => {
        const active = ['queued', 'processing', 'refining'].includes(job.status)
        const KindIcon = job.document_kind === 'pdf' ? FileText : FileImage
        const originalName = originalDocumentName(job.source_path)
        const summaryName = summarizeDocumentName(job.source_path)
        return <Card key={job.id} className="flex h-full flex-col border-4 shadow-[6px_6px_0_0_var(--border)] [--card-spacing:--spacing(5)]">
          <CardHeader className="gap-3"><div className="flex items-start gap-3"><div className="grid size-11 shrink-0 place-items-center border-2 border-border bg-primary"><KindIcon /></div><div className="min-w-0"><CardTitle className="line-clamp-2 font-head text-xl leading-tight" title={originalName}>{summaryName}</CardTitle><CardDescription className="mt-2 truncate font-mono text-xs" title={originalName}>{originalName}</CardDescription></div></div><Badge className={job.status === 'completed' ? 'w-fit bg-green-300 text-foreground' : job.status === 'failed' ? 'w-fit bg-red-300 text-foreground' : 'w-fit'} variant="outline"><StatusIcon status={job.status} />{statusLabel(job.status)}</Badge></CardHeader>
          <CardContent className="flex flex-1 flex-col gap-5">
            <TaskIdentifier taskId={job.task_id} />
            <div className="grid gap-2 border-2 border-border bg-muted/30 p-4 font-mono text-sm"><span>OCR：<strong>{job.ocr_model_name}</strong></span><span>文本：<strong>{job.text_model_name}</strong></span><span>类型：<strong>{job.document_kind === 'pdf' ? 'PDF' : '图片'}</strong></span><span>属性：<strong>{job.file_attribute === 'resume' ? '简历' : '文档'}</strong></span><span>进度：<strong>{job.status === 'completed' ? 100 : job.progress_percent}%</strong></span>{job.page_count > 0 && <span>页数：<strong>{job.page_count}</strong></span>}</div>
            {job.has_ocr_checkpoint && job.status !== 'completed' && <Alert status="success"><AlertTitle>OCR 原始结果已保存</AlertTitle><AlertDescription>文本校对失败或重试不会再次调用 PaddleOCR。</AlertDescription></Alert>}
            {job.status === 'failed' && <Alert variant="destructive"><AlertTitle>执行失败 · {job.task_id}</AlertTitle><AlertDescription>{job.error_message || '任务执行失败，请使用任务 ID 检索 Worker 日志。'}</AlertDescription></Alert>}
            <div className="mt-auto grid gap-3"><Button className="w-full" onClick={() => onOpenTask(job.id)}><Eye />查看解析结果</Button>{active && <Button className="w-full" variant="outline" onClick={() => action(job, 'cancel')}>取消</Button>}{job.status === 'failed' && <Button className="w-full" variant="outline" onClick={() => action(job, 'retry')}><RotateCcw />{job.has_ocr_checkpoint ? '重试文本校对' : '重试 OCR'}</Button>}<Button className="w-full" variant="destructive" disabled={busy === job.id || active} onClick={() => action(job, 'delete')}><Trash2 />{busy === job.id ? '处理中…' : '删除'}</Button></div>
          </CardContent>
        </Card>
      })}</div>}
    </div>
  )
}
