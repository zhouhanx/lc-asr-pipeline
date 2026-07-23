import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, CheckCircle2, Download, Globe2, LoaderCircle, Lock, RotateCcw, XCircle } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { apiDownload, apiRequest, type AuthPayload, type TranscriptionJobDetail } from '@/lib/api'

import { DialogueTranscript } from './DialogueTranscript'
import { TaskModelName } from './TaskModelName'

type Props = { session: AuthPayload; jobId: string; onBack: () => void }

const speakerModeLabel = { single: '单人', double: '双人', multiple: '多人' } as const
const statusLabel = (status: string) => status === 'processing' ? '语音解析中' : status === 'refining' ? '文本整理中' : status === 'queued' ? '等待中' : status === 'failed' ? '失败' : status === 'cancelled' ? '已取消' : status

export function TaskDetailPanel({ session, jobId, onBack }: Props) {
  const [job, setJob] = useState<TranscriptionJobDetail | null>(null)
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)

  const load = useCallback(() => {
    apiRequest<TranscriptionJobDetail>(`/jobs/${jobId}?include_segments=false`, { token: session.access_token })
      .then((item) => {
        setJob(item)
        setUpdatedAt(new Date())
      })
      .catch((reason: Error) => setError(reason.message))
  }, [jobId, session.access_token])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 5000)
    return () => window.clearInterval(timer)
  }, [load])

  const download = async (format: 'txt' | 'json' | 'srt' | 'vtt' | 'html') => {
    try {
      const blob = await apiDownload(`/jobs/${jobId}/export/${format}`, session.access_token)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `transcript-${jobId}.${format}`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '导出失败。')
    }
  }

  const toggleVisibility = async () => {
    if (!job) return
    try {
      const updated = await apiRequest<TranscriptionJobDetail>(`/jobs/${jobId}/visibility`, {
        method: 'PATCH',
        token: session.access_token,
        body: { visibility: job.visibility === 'public' ? 'private' : 'public' },
      })
      setJob((current) => current ? { ...current, visibility: updated.visibility } : current)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '可见范围修改失败。')
    }
  }

  const retry = async () => {
    try {
      await apiRequest(`/jobs/${jobId}/retry`, { method: 'POST', token: session.access_token })
      load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '任务重试失败。')
    }
  }

  if (!job) return <div className="grid min-h-72 place-items-center"><LoaderCircle className="size-10 animate-spin" />{error && <p>{error}</p>}</div>
  const success = job.status === 'completed'
  const progress = success ? 100 : job.progress_percent
  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <Button variant="outline" onClick={onBack}><ArrowLeft />返回任务列表</Button>
      {error && <Alert variant="destructive"><AlertTitle>任务错误</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
      <Card className="border-4 shadow-[8px_8px_0_0_var(--border)] [--card-spacing:--spacing(7)]">
        <CardHeader className="gap-4"><div className="flex flex-wrap items-start justify-between gap-4"><div className="min-w-0"><p className="font-mono text-xs tracking-[0.2em] text-muted-foreground">TASK / {job.id}</p><CardTitle className="mt-3 break-all font-head text-3xl">{job.source_path.split('/').at(-1)}</CardTitle><CardDescription className="mt-2 break-all">{job.source_path}</CardDescription></div><Badge className={success ? 'bg-green-300 text-foreground' : job.status === 'failed' ? 'bg-red-300 text-foreground' : ''} variant="outline">{success ? <CheckCircle2 /> : job.status === 'failed' || job.status === 'cancelled' ? <XCircle /> : <LoaderCircle className="animate-spin" />}{success ? 'success' : statusLabel(job.status)}</Badge></div></CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 border-2 border-border bg-muted/30 p-5 text-sm sm:grid-cols-2 lg:grid-cols-6"><div><p className="text-muted-foreground">语音模型</p><TaskModelName name={job.provider_name} deleted={job.provider_deleted} /></div><div><p className="text-muted-foreground">文本模型</p><TaskModelName name={job.text_provider_name ?? '未配置'} deleted={job.text_provider_deleted} /></div><div><p className="text-muted-foreground">人数</p><strong>{speakerModeLabel[job.speaker_mode]}</strong></div><div><p className="text-muted-foreground">进度</p><strong>{progress}%</strong></div><div><p className="text-muted-foreground">开始时间</p><strong>{job.started_at ? new Date(job.started_at).toLocaleString() : '等待中'}</strong></div><div><p className="text-muted-foreground">最近报告</p><strong>{updatedAt?.toLocaleTimeString()}</strong></div></div>
          <Progress value={progress} className={!success ? 'animate-pulse' : ''} />
          {job.has_asr_checkpoint && !success && <Alert status="success"><AlertTitle>语音解析结果已保存</AlertTitle><AlertDescription>{job.status === 'failed' ? '可以直接重试文本整理，系统不会再次调用语音模型。' : '原始文本、时间戳和说话人提示已经持久化。'}</AlertDescription></Alert>}
          {job.error_message && <Alert variant="destructive"><AlertTitle>执行失败</AlertTitle><AlertDescription>{job.error_message}</AlertDescription></Alert>}
          <div className="flex flex-wrap items-center gap-3">
            <Button variant={job.visibility === 'public' ? 'default' : 'outline'} onClick={toggleVisibility}>
              {job.visibility === 'public' ? <Globe2 /> : <Lock />}
              {job.visibility === 'public' ? '公开任务' : '私有任务'}
            </Button>
            <p className="text-sm text-muted-foreground">
              {job.visibility === 'public' ? '所有已登录用户均可查看。' : '仅本组织成员和超级管理员可查看。'}
            </p>
            {job.status === 'failed' && <Button variant="outline" onClick={retry}><RotateCcw />{job.has_asr_checkpoint ? '重试文本整理' : '重试语音解析'}</Button>}
          </div>
          {success && <div className="flex flex-wrap gap-3">{(['txt', 'json', 'srt', 'vtt', 'html'] as const).map((format) => <Button key={format} variant="outline" onClick={() => download(format)}><Download />{format.toUpperCase()}</Button>)}</div>}
          {job.transcript_text && <DialogueTranscript transcript={job.transcript_text} />}
        </CardContent>
      </Card>
    </div>
  )
}
