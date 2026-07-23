import { useCallback, useEffect, useMemo, useState } from 'react'
import { FileAudio, History, Play, Trash2 } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { apiRequest, type AuthPayload, type HistoricalFile, type ModelProvider, type TranscriptionJob } from '@/lib/api'

type Props = { session: AuthPayload; onOpenTask: (jobId: string) => void }

export function FileHistoryPanel({ session, onOpenTask }: Props) {
  const [files, setFiles] = useState<HistoricalFile[]>([])
  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [providerId, setProviderId] = useState('')
  const [textProviderId, setTextProviderId] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [pendingDelete, setPendingDelete] = useState<HistoricalFile | null>(null)

  const load = useCallback(() => {
    Promise.all([
      apiRequest<HistoricalFile[]>('/uploads/history', { token: session.access_token }),
      apiRequest<ModelProvider[]>('/models', { token: session.access_token }),
    ]).then(([historyFiles, modelProviders]) => {
      const enabled = modelProviders.filter((provider) => provider.is_enabled)
      setFiles(historyFiles)
      setProviders(enabled)
      const speech = enabled.filter((provider) => provider.model_kind === 'speech')
      const text = enabled.filter((provider) => provider.model_kind === 'text')
      setProviderId(speech.find((provider) => provider.is_default)?.id ?? speech[0]?.id ?? '')
      setTextProviderId(text.find((provider) => provider.is_default)?.id ?? text[0]?.id ?? '')
    }).catch((reason: Error) => setError(reason.message))
  }, [session.access_token])

  useEffect(() => {
    load()
  }, [load])

  const selectedProvider = useMemo(() => providers.find((provider) => provider.id === providerId), [providerId, providers])
  const speechProviders = providers.filter((provider) => provider.model_kind === 'speech')
  const textProviders = providers.filter((provider) => provider.model_kind === 'text')

  const reprocess = async (file: HistoricalFile) => {
    if (!providerId || !textProviderId) return
    setBusy(file.id)
    setError('')
    try {
      const jobs = await apiRequest<TranscriptionJob[]>('/jobs', {
        method: 'POST',
        token: session.access_token,
        body: { provider_id: providerId, text_provider_id: textProviderId, uploaded_file_ids: [file.id], language: 'Chinese', diarize: selectedProvider?.capabilities.includes('diarization') ?? false },
      })
      setMessage(`已使用 ${selectedProvider?.name} 创建新的解析任务。`)
      if (jobs[0]) onOpenTask(jobs[0].id)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '重新解析失败。请选择尚未用于该文件的其他模型。')
    } finally {
      setBusy('')
    }
  }

  const deleteFile = async (file: HistoricalFile) => {
    setBusy(file.id)
    setPendingDelete(null)
    setError('')
    setMessage('')
    try {
      await apiRequest(`/uploads/history/${file.id}`, {
        method: 'DELETE',
        token: session.access_token,
      })
      setMessage(`历史文件 ${file.original_name} 及其相关内容已删除。`)
      load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除历史文件失败。')
    } finally {
      setBusy('')
    }
  }

  return <div className="mx-auto w-full max-w-7xl space-y-7">
    <AlertDialog open={pendingDelete !== null} onOpenChange={(open) => { if (!open) setPendingDelete(null) }}>
      <AlertDialogContent>
        <AlertDialogTitle>删除这个历史文件？</AlertDialogTitle>
        <AlertDialogDescription>“{pendingDelete?.original_name}”、全部相关任务、转写文本和导出数据都会被永久删除。此操作无法撤销。</AlertDialogDescription>
        <AlertDialogFooter><AlertDialogCancel>取消</AlertDialogCancel><AlertDialogAction onClick={() => { if (pendingDelete) void deleteFile(pendingDelete) }}><Trash2 />确认删除</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    <div><p className="font-mono text-xs tracking-[0.25em] text-muted-foreground">WORKSPACE / HISTORY</p><h1 className="mt-2 font-head text-4xl">历史文件</h1><p className="mt-2 text-base text-muted-foreground">相同内容只保存一份；可直接选择其他模型重新解析，无需再次上传。</p></div>
    <Card className="border-4 shadow-[6px_6px_0_0_var(--border)]"><CardHeader><CardTitle className="font-head text-2xl">重新解析模型</CardTitle><CardDescription>分别选择语音识别模型和文本整理模型，再从历史文件卡片发起新任务。</CardDescription></CardHeader><CardContent className="grid gap-5 md:grid-cols-2"><div><Label className="mb-3 text-base" htmlFor="history-provider">语音模型方案</Label><Select value={providerId} onValueChange={setProviderId}><SelectTrigger id="history-provider"><SelectValue placeholder="选择语音模型" /></SelectTrigger><SelectContent><SelectGroup>{speechProviders.map((provider) => <SelectItem key={provider.id} value={provider.id}>{provider.name} · {provider.model_name}</SelectItem>)}</SelectGroup></SelectContent></Select></div><div><Label className="mb-3 text-base" htmlFor="history-text-provider">文本模型方案</Label><Select value={textProviderId} onValueChange={setTextProviderId}><SelectTrigger id="history-text-provider"><SelectValue placeholder="选择文本模型" /></SelectTrigger><SelectContent><SelectGroup>{textProviders.map((provider) => <SelectItem key={provider.id} value={provider.id}>{provider.name} · {provider.model_name}</SelectItem>)}</SelectGroup></SelectContent></Select></div>{textProviders.length === 0 && <Alert variant="destructive" className="md:col-span-2"><AlertTitle>尚未配置文本模型</AlertTitle><AlertDescription>请先在“模型”页面添加文本模型后再重新解析。</AlertDescription></Alert>}</CardContent></Card>
    {message && <Alert className="border-4 bg-green-100"><AlertTitle>任务已创建</AlertTitle><AlertDescription>{message}</AlertDescription></Alert>}
    {error && <Alert variant="destructive"><AlertTitle>操作失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
    {files.length === 0 ? <div className="grid min-h-64 place-items-center border-4 border-dashed border-border bg-muted/40"><div className="text-center"><History className="mx-auto size-10" /><p className="mt-3 font-head">暂无历史文件</p></div></div> : <div className="grid gap-5 lg:grid-cols-2">{files.map((file) => <Card key={file.id} className="border-4 shadow-[5px_5px_0_0_var(--border)]"><CardHeader><div className="flex items-start gap-4"><div className="grid size-14 shrink-0 place-items-center border-2 border-border bg-primary shadow-sm"><FileAudio /></div><div className="min-w-0"><CardTitle className="truncate font-head text-xl">{file.original_name}</CardTitle><CardDescription className="mt-2 break-all font-mono text-xs">{file.relative_path}</CardDescription></div></div></CardHeader><CardContent className="space-y-4"><div className="flex flex-wrap gap-2"><Badge variant="outline">{(file.size_bytes / 1024 ** 2).toFixed(1)} MiB</Badge><Badge variant="outline">解析 {file.job_count} 次</Badge>{file.latest_job_status && <Badge variant="outline">最近：{file.latest_job_status === 'completed' ? 'success' : file.latest_job_status}</Badge>}</div><p className="truncate font-mono text-xs text-muted-foreground">SHA-256 {file.sha256}</p><div className="flex flex-wrap gap-3"><Button disabled={busy === file.id || !providerId || !textProviderId} onClick={() => reprocess(file)}><Play />{busy === file.id ? '处理中…' : '使用所选模型重新解析'}</Button><Button variant="destructive" disabled={busy === file.id} onClick={() => setPendingDelete(file)}><Trash2 />{busy === file.id ? '处理中…' : '删除'}</Button></div></CardContent></Card>)}</div>}
  </div>
}
