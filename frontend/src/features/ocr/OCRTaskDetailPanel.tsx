import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, CheckCircle2, Download, FileImage, FileText, LoaderCircle, RotateCcw, XCircle } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { apiDownload, apiRequest, type AuthPayload, type OCRJobDetail } from '@/lib/api'
import { TaskIdentifier } from '@/features/transcription/TaskIdentifier'

import { originalDocumentName, summarizeDocumentName } from './documentName'

type Props = { session: AuthPayload; jobId: string; onBack: () => void }

export function OCRTaskDetailPanel({ session, jobId, onBack }: Props) {
  const [job, setJob] = useState<OCRJobDetail | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    apiRequest<OCRJobDetail>(`/ocr/jobs/${jobId}`, { token: session.access_token })
      .then(setJob)
      .catch((reason: Error) => setError(reason.message))
  }, [jobId, session.access_token])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 5000)
    return () => window.clearInterval(timer)
  }, [load])

  const retry = async () => {
    try {
      await apiRequest(`/ocr/jobs/${jobId}/retry`, { method: 'POST', token: session.access_token })
      load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'OCR 重试失败。')
    }
  }

  const download = async (format: 'md' | 'json') => {
    try {
      const blob = await apiDownload(`/ocr/jobs/${jobId}/export/${format}`, session.access_token)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `ocr-${jobId}.${format}`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'OCR 结果导出失败。')
    }
  }

  if (!job) return <div className="grid min-h-72 place-items-center"><LoaderCircle className="size-10 animate-spin" />{error && <p>{error}</p>}</div>
  const success = job.status === 'completed'
  const KindIcon = job.document_kind === 'pdf' ? FileText : FileImage
  const originalName = originalDocumentName(job.source_path)
  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <Button variant="outline" onClick={onBack}><ArrowLeft />返回 OCR 任务</Button>
      {error && <Alert variant="destructive"><AlertTitle>OCR 任务错误</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
      <Card className="border-4 shadow-[8px_8px_0_0_var(--border)] [--card-spacing:--spacing(7)]">
        <CardHeader className="gap-4"><div className="flex flex-wrap items-start justify-between gap-4"><div className="min-w-0"><p className="font-mono text-xs tracking-[0.2em] text-muted-foreground">OCR TASK</p><CardTitle className="mt-3 flex items-center gap-3 font-head text-3xl" title={originalName}><KindIcon className="shrink-0" />{summarizeDocumentName(job.source_path)}</CardTitle><CardDescription className="mt-2 break-all">{originalName}</CardDescription></div><Badge className={success ? 'bg-green-300 text-foreground' : job.status === 'failed' ? 'bg-red-300 text-foreground' : ''} variant="outline">{success ? <CheckCircle2 /> : job.status === 'failed' || job.status === 'cancelled' ? <XCircle /> : <LoaderCircle className="animate-spin" />}{success ? 'success' : job.status}</Badge></div><TaskIdentifier taskId={job.task_id} /></CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 border-2 border-border bg-muted/30 p-5 text-sm sm:grid-cols-2 lg:grid-cols-6"><div><p className="text-muted-foreground">OCR 模型</p><strong>{job.ocr_model_name}</strong></div><div><p className="text-muted-foreground">文本模型</p><strong>{job.text_model_name}</strong></div><div><p className="text-muted-foreground">类型</p><strong>{job.document_kind === 'pdf' ? 'PDF' : '图片'}</strong></div><div><p className="text-muted-foreground">属性</p><strong>{job.file_attribute === 'resume' ? '简历' : '文档'}</strong></div><div><p className="text-muted-foreground">进度</p><strong>{success ? 100 : job.progress_percent}%</strong></div><div><p className="text-muted-foreground">页数</p><strong>{job.page_count || '-'}</strong></div></div>
          {job.has_ocr_checkpoint && !success && <Alert status="success"><AlertTitle>OCR 结果已保存</AlertTitle><AlertDescription>后续重试只执行文本校对，不会再次提交 PaddleOCR。</AlertDescription></Alert>}
          {job.error_message && <Alert variant="destructive"><AlertTitle>执行失败 · {job.task_id}</AlertTitle><AlertDescription>{job.error_message}<br />请使用以上任务 ID 检索 Worker 日志。</AlertDescription></Alert>}
          {job.status === 'failed' && <Button variant="outline" onClick={retry}><RotateCcw />{job.has_ocr_checkpoint ? '重试文本校对' : '重试 OCR'}</Button>}
          {success && <div className="flex flex-wrap gap-3"><Button variant="outline" onClick={() => download('md')}><Download />MARKDOWN</Button><Button variant="outline" onClick={() => download('json')}><Download />JSON</Button></div>}
          {job.markdown_text && <section className="border-4 border-border bg-background p-5 shadow-[5px_5px_0_0_var(--border)]"><div className="mb-4 border-b-4 border-border pb-3"><h2 className="font-head text-2xl">OCR 解析结果</h2><p className="mt-1 text-sm text-muted-foreground">已由文本模型校对的 Markdown 内容</p></div><pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-sm leading-7">{job.markdown_text}</pre></section>}
        </CardContent>
      </Card>
    </div>
  )
}
