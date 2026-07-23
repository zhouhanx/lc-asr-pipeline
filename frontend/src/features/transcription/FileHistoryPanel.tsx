import { useCallback, useEffect, useMemo, useState } from 'react'
import { FileAudio, FileImage, FileText, History, Play, Trash2 } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { apiRequest, type AuthPayload, type HistoricalFile, type ModelProvider, type OCRJob, type TranscriptionJob } from '@/lib/api'

type HistoryKind = 'audio' | 'image' | 'pdf'
type Props = {
  session: AuthPayload
  fileKind: HistoryKind
  onOpenTask: (jobId: string) => void
  onOpenOCRTask: (jobId: string) => void
}
type SpeakerMode = 'single' | 'double' | 'multiple'

export function FileHistoryPanel({ session, fileKind, onOpenTask, onOpenOCRTask }: Props) {
  const [files, setFiles] = useState<HistoricalFile[]>([])
  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [providerId, setProviderId] = useState('')
  const [textProviderId, setTextProviderId] = useState('')
  const [speakerMode, setSpeakerMode] = useState<SpeakerMode | ''>('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [pendingDelete, setPendingDelete] = useState<HistoricalFile | null>(null)
  const [pendingReprocess, setPendingReprocess] = useState<HistoricalFile | null>(null)

  const load = useCallback(() => {
    Promise.all([
      apiRequest<HistoricalFile[]>(`/uploads/history?file_kind=${fileKind}`, { token: session.access_token }),
      apiRequest<ModelProvider[]>('/models', { token: session.access_token }),
    ]).then(([historyFiles, modelProviders]) => {
      const enabled = modelProviders.filter((provider) => provider.is_enabled)
      setFiles(historyFiles)
      setProviders(enabled)
    }).catch((reason: Error) => setError(reason.message))
  }, [fileKind, session.access_token])

  useEffect(() => {
    load()
  }, [load])

  const selectedProvider = useMemo(() => providers.find((provider) => provider.id === providerId), [providerId, providers])
  const speechProviders = providers.filter((provider) => provider.model_kind === 'speech')
  const ocrProviders = providers.filter((provider) => provider.model_kind === 'ocr')
  const textProviders = providers.filter((provider) => provider.model_kind === 'text')

  const openReprocess = (file: HistoricalFile) => {
    setProviderId('')
    setTextProviderId('')
    setSpeakerMode('')
    setError('')
    setMessage('')
    setPendingReprocess(file)
  }

  const closeReprocess = () => {
    setPendingReprocess(null)
    setProviderId('')
    setTextProviderId('')
    setSpeakerMode('')
  }

  const reprocess = async () => {
    const file = pendingReprocess
    if (!file || !providerId || !textProviderId || (fileKind === 'audio' && !speakerMode)) return
    setBusy(file.id)
    setError('')
    try {
      const jobs = fileKind === 'audio'
        ? await apiRequest<TranscriptionJob[]>('/jobs', {
            method: 'POST',
            token: session.access_token,
            body: {
              provider_id: providerId,
              text_provider_id: textProviderId,
              uploaded_file_ids: [file.id],
              language: 'Chinese',
              diarize: speakerMode !== 'single' && (selectedProvider?.capabilities.includes('diarization') ?? false),
              speaker_mode: speakerMode,
            },
          })
        : await apiRequest<OCRJob[]>('/ocr/jobs', {
            method: 'POST',
            token: session.access_token,
            body: {
              ocr_provider_id: providerId,
              text_provider_id: textProviderId,
              uploaded_file_ids: [file.id],
              document_kind: fileKind,
            },
          })
      setMessage(`已为 ${file.original_name} 创建新的解析任务。`)
      closeReprocess()
      if (jobs[0]) {
        if (fileKind === 'audio') onOpenTask(jobs[0].id)
        else onOpenOCRTask(jobs[0].id)
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '重新解析失败。请检查模型和说话人数选择。')
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

  return <div className="mx-auto w-full max-w-[1920px] space-y-7">
    <AlertDialog open={pendingDelete !== null} onOpenChange={(open) => { if (!open) setPendingDelete(null) }}>
      <AlertDialogContent>
        <AlertDialogTitle>删除这个历史文件？</AlertDialogTitle>
        <AlertDialogDescription>“{pendingDelete?.original_name}”、全部相关任务、转写文本和导出数据都会被永久删除。此操作无法撤销。</AlertDialogDescription>
        <AlertDialogFooter><AlertDialogCancel>取消</AlertDialogCancel><AlertDialogAction onClick={() => { if (pendingDelete) void deleteFile(pendingDelete) }}><Trash2 />确认删除</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    <Sheet open={pendingReprocess !== null} onOpenChange={(open) => { if (!open && !busy) closeReprocess() }}>
      <SheetContent className="border-l-4 shadow-[-8px_0_0_0_var(--border)] data-[side=right]:w-[calc(100vw-1rem)] data-[side=right]:sm:w-[min(calc(45vw+20px),64rem)] data-[side=right]:sm:max-w-[64rem]">
        <SheetHeader className="border-b-4 border-border bg-primary p-6">
          <div className="mb-3 grid size-12 place-items-center border-2 border-border bg-background shadow-[4px_4px_0_0_var(--border)]"><Play /></div>
          <SheetTitle className="font-head text-2xl">重新解析{fileKind === 'audio' ? '音频' : fileKind === 'pdf' ? 'PDF' : '图片'}</SheetTitle>
          <SheetDescription className="break-all">为“{pendingReprocess?.original_name}”单独选择识别模型和文本模型。</SheetDescription>
        </SheetHeader>
        <div className="grid gap-5 overflow-y-auto p-6">
          {error && <Alert variant="destructive"><AlertTitle>重新解析失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
          {((fileKind === 'audio' ? speechProviders : ocrProviders).length === 0 || textProviders.length === 0) && <Alert variant="destructive"><AlertTitle>模型配置不完整</AlertTitle><AlertDescription>请先在“模型”页面配置可用的{fileKind === 'audio' ? '语音' : 'OCR'}模型和文本模型。</AlertDescription></Alert>}
          <div className="space-y-2"><Label htmlFor="history-provider">{fileKind === 'audio' ? '语音模型' : 'OCR 模型'}</Label><Select value={providerId} onValueChange={setProviderId}><SelectTrigger id="history-provider"><SelectValue placeholder={`请选择${fileKind === 'audio' ? '语音' : 'OCR'}模型`} /></SelectTrigger><SelectContent><SelectGroup>{(fileKind === 'audio' ? speechProviders : ocrProviders).map((provider) => <SelectItem key={provider.id} value={provider.id}>{provider.name} · {provider.model_name}</SelectItem>)}</SelectGroup></SelectContent></Select></div>
          <div className="space-y-2"><Label htmlFor="history-text-provider">文本模型</Label><Select value={textProviderId} onValueChange={setTextProviderId}><SelectTrigger id="history-text-provider"><SelectValue placeholder="请选择文本模型" /></SelectTrigger><SelectContent><SelectGroup>{textProviders.map((provider) => <SelectItem key={provider.id} value={provider.id}>{provider.name} · {provider.model_name}</SelectItem>)}</SelectGroup></SelectContent></Select></div>
          {fileKind === 'audio' && <div className="space-y-2"><Label htmlFor="history-speaker-mode">说话人数</Label><Select value={speakerMode} onValueChange={(value) => setSpeakerMode(value as SpeakerMode)}><SelectTrigger id="history-speaker-mode"><SelectValue placeholder="请选择单人、双人或多人" /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="single">单人</SelectItem><SelectItem value="double">双人</SelectItem><SelectItem value="multiple">多人</SelectItem></SelectGroup></SelectContent></Select></div>}
          <p className="border-2 border-border bg-muted/40 p-4 text-xs leading-6 text-muted-foreground">每次只为当前文件创建任务。{fileKind === 'audio' ? '选择双人或多人时，支持说话人分离的语音模型会同时启用分离能力。' : 'OCR 原始 Markdown 会在识别后交给所选文本模型校对。'}</p>
        </div>
        <SheetFooter className="mt-8 flex-row items-center justify-end border-t-4 border-border">
          <Button className="min-w-24" variant="outline" disabled={Boolean(busy)} onClick={closeReprocess}>取消</Button>
          <Button className="min-w-40" disabled={Boolean(busy) || !providerId || !textProviderId || (fileKind === 'audio' && !speakerMode) || (fileKind === 'audio' ? speechProviders : ocrProviders).length === 0 || textProviders.length === 0} onClick={() => void reprocess()}><Play />{busy ? '创建中…' : '创建解析任务'}</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
    <div><p className="font-mono text-xs tracking-[0.25em] text-muted-foreground">WORKSPACE / HISTORY / {fileKind === 'audio' ? 'VIDEO' : fileKind === 'image' ? 'PICTURE' : 'PDF'}</p><h1 className="mt-2 font-head text-4xl">{fileKind === 'audio' ? 'VIDEO' : fileKind === 'image' ? 'PICTURE' : 'PDF'} 历史文件</h1><p className="mt-2 text-base text-muted-foreground">相同内容只保存一份；可以从历史文件选择其他模型重新解析，无需再次上传。</p></div>
    {message && <Alert className="border-4 bg-green-100"><AlertTitle>任务已创建</AlertTitle><AlertDescription>{message}</AlertDescription></Alert>}
    {error && <Alert variant="destructive"><AlertTitle>操作失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
    {files.length === 0 ? <div className="grid min-h-64 place-items-center border-4 border-dashed border-border bg-muted/40"><div className="text-center"><History className="mx-auto size-10" /><p className="mt-3 font-head">暂无历史文件</p></div></div> : <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">{files.map((file) => {
      const KindIcon = file.file_kind === 'audio' ? FileAudio : file.file_kind === 'image' ? FileImage : FileText
      return <Card key={file.id} className="flex h-full flex-col border-4 shadow-[5px_5px_0_0_var(--border)] [--card-spacing:--spacing(5)]"><CardHeader><div className="flex items-start gap-3"><div className="grid size-12 shrink-0 place-items-center border-2 border-border bg-primary shadow-sm"><KindIcon /></div><div className="min-w-0"><CardTitle className="truncate font-head text-lg">{file.original_name}</CardTitle><CardDescription className="mt-2 line-clamp-2 break-all font-mono text-xs">{file.relative_path}</CardDescription></div></div></CardHeader><CardContent className="flex flex-1 flex-col gap-4"><div className="flex flex-wrap gap-2"><Badge variant="outline">{file.file_kind === 'audio' ? 'VIDEO' : file.file_kind === 'image' ? 'PICTURE' : 'PDF'}</Badge><Badge variant="outline">{(file.size_bytes / 1024 ** 2).toFixed(1)} MiB</Badge><Badge variant="outline">解析 {file.job_count} 次</Badge>{file.latest_job_status && <Badge variant="outline">最近：{file.latest_job_status === 'completed' ? 'success' : file.latest_job_status}</Badge>}</div><p className="truncate font-mono text-xs text-muted-foreground">SHA-256 {file.sha256}</p><div className="mt-auto grid gap-3"><Button className="w-full" disabled={busy === file.id} onClick={() => openReprocess(file)}><Play />使用模型重新解析</Button><Button className="w-full" variant="destructive" disabled={busy === file.id} onClick={() => setPendingDelete(file)}><Trash2 />{busy === file.id ? '处理中…' : '删除'}</Button></div></CardContent></Card>
    })}</div>}
  </div>
}
