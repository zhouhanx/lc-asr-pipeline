import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, Download, FileText, Globe2, LoaderCircle } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  apiDownload,
  apiRequest,
  type AuthPayload,
  type PublicTranscriptionJob,
  type PublicTranscriptionJobDetail,
} from '@/lib/api'

import { DialogueTranscript } from './DialogueTranscript'
import { TaskModelName } from './TaskModelName'

export function PublicTaskPanel({ session }: { session: AuthPayload }) {
  const [jobs, setJobs] = useState<PublicTranscriptionJob[]>([])
  const [selected, setSelected] = useState<PublicTranscriptionJobDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setJobs(await apiRequest<PublicTranscriptionJob[]>('/jobs/public', { token: session.access_token }))
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '公开任务加载失败。')
    } finally {
      setLoading(false)
    }
  }, [session.access_token])

  useEffect(() => { void load() }, [load])

  const openTask = async (jobId: string) => {
    try {
      setSelected(await apiRequest<PublicTranscriptionJobDetail>(`/jobs/public/${jobId}`, { token: session.access_token }))
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '公开任务详情加载失败。')
    }
  }

  const download = async (format: 'txt' | 'json' | 'srt' | 'vtt' | 'html') => {
    if (!selected) return
    try {
      const blob = await apiDownload(`/jobs/public/${selected.id}/export/${format}`, session.access_token)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `transcript-${selected.id}.${format}`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '导出失败。')
    }
  }

  if (selected) {
    return (
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <Button variant="outline" onClick={() => setSelected(null)}><ArrowLeft />返回公开任务</Button>
        {error && <Alert status="error"><AlertTitle>操作失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
        <Card className="border-4 shadow-[8px_8px_0_0_var(--border)]">
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <Badge className="mb-3 bg-green-200 text-foreground" variant="outline"><Globe2 />公开 · {selected.tenant_name}</Badge>
                <CardTitle className="break-all font-head text-3xl">{selected.source_path.split('/').at(-1)}</CardTitle>
                <CardDescription className="mt-2">{selected.tenant_slug} · {new Date(selected.queued_at).toLocaleString()}</CardDescription>
              </div>
              <Badge variant="outline">{selected.status}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-4 border-2 border-border bg-muted/30 p-4 text-sm sm:grid-cols-2">
              <div><p className="text-muted-foreground">语音模型</p><TaskModelName name={selected.provider_name} deleted={selected.provider_deleted} /></div>
              <div><p className="text-muted-foreground">文本模型</p><TaskModelName name={selected.text_provider_name ?? '未配置'} deleted={selected.text_provider_deleted} /></div>
            </div>
            {selected.status === 'completed' && (
              <div className="flex flex-wrap gap-3">
                {(['txt', 'json', 'srt', 'vtt', 'html'] as const).map((format) => (
                  <Button key={format} variant="outline" onClick={() => download(format)}><Download />{format.toUpperCase()}</Button>
                ))}
              </div>
            )}
            {selected.transcript_text
              ? <DialogueTranscript transcript={selected.transcript_text} />
              : <div className="border-2 border-dashed border-border p-8 text-center text-muted-foreground">暂无转写内容</div>}
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <div>
        <p className="font-mono text-xs tracking-[0.2em] text-muted-foreground">SHARED / TRANSCRIPTS</p>
        <h1 className="mt-2 font-head text-3xl">公开转写任务</h1>
        <p className="mt-2 text-muted-foreground">查看所有组织主动公开的转写结果；私有任务不会出现在这里。</p>
      </div>
      {error && <Alert status="error"><AlertTitle>加载失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
      {loading ? (
        <div className="grid min-h-64 place-items-center"><LoaderCircle className="size-10 animate-spin" /></div>
      ) : jobs.length === 0 ? (
        <Card className="border-4"><CardContent className="grid min-h-64 place-items-center text-center"><div><Globe2 className="mx-auto size-10" /><p className="mt-4 font-head text-xl">暂无公开任务</p></div></CardContent></Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {jobs.map((job) => (
            <Card key={job.id} className="border-4 shadow-[5px_5px_0_0_var(--border)]">
              <CardHeader>
                <div className="flex flex-wrap gap-2"><Badge className="bg-green-200 text-foreground" variant="outline">{job.tenant_name}</Badge><Badge variant="outline">{job.status}</Badge></div>
                <CardTitle className="mt-3 break-all text-xl">{job.source_path.split('/').at(-1)}</CardTitle>
                <CardDescription>{new Date(job.queued_at).toLocaleString()}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="line-clamp-3 min-h-16 text-sm leading-6 text-muted-foreground">{job.transcript_text || '暂无转写内容'}</p>
                <Button className="w-full" variant="outline" onClick={() => openTask(job.id)}><FileText />查看公开转写</Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
