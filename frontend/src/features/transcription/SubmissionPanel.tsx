import { useEffect, useMemo, useRef, useState } from 'react'
import { Archive, CheckCircle2, FileAudio, FolderOpen, Play, Upload } from 'lucide-react'
import { createSHA256 } from 'hash-wasm'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  apiBinaryRequest,
  apiRequest,
  type AuthPayload,
  type ModelProvider,
  type TranscriptionJob,
  type UploadBatch,
} from '@/lib/api'

import { MAX_BATCH_BYTES, uploadBatchSizeError } from './upload-limits'

const HASH_CHUNK_BYTES = 8 * 1024 ** 2

type Props = { session: AuthPayload; onOpenTasks: () => void; onOpenHistory: () => void }
type BrowserFile = File & { webkitRelativePath?: string }
type PendingUpload = { fingerprint: string; batch: UploadBatch }
type SpeakerMode = 'single' | 'double' | 'multiple'

function relativePath(file: BrowserFile) {
  return file.webkitRelativePath || file.name
}

function archiveType(name: string): 'zip' | 'tar' | 'tar.gz' | 'tgz' | undefined {
  const lower = name.toLowerCase()
  if (lower.endsWith('.tar.gz')) return 'tar.gz'
  if (lower.endsWith('.tgz')) return 'tgz'
  if (lower.endsWith('.zip')) return 'zip'
  if (lower.endsWith('.tar')) return 'tar'
  return undefined
}

function selectionFingerprint(files: BrowserFile[]) {
  return JSON.stringify(
    files
      .map((file) => [relativePath(file), file.size, file.lastModified])
      .sort(([left], [right]) => String(left).localeCompare(String(right))),
  )
}

async function blobSha256(blob: Blob) {
  const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0')).join('')
}

async function fileSha256(file: File) {
  const hasher = await createSHA256()
  hasher.init()
  for (let offset = 0; offset < file.size; offset += HASH_CHUNK_BYTES) {
    const chunk = file.slice(offset, Math.min(offset + HASH_CHUNK_BYTES, file.size))
    hasher.update(new Uint8Array(await chunk.arrayBuffer()))
  }
  return hasher.digest()
}

export function SubmissionPanel({ session, onOpenTasks, onOpenHistory }: Props) {
  const folderInput = useRef<HTMLInputElement>(null)
  const uploadController = useRef<AbortController | null>(null)
  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [providerId, setProviderId] = useState('')
  const [textProviderId, setTextProviderId] = useState('')
  const [files, setFiles] = useState<BrowserFile[]>([])
  const [speakerMode, setSpeakerMode] = useState<SpeakerMode>('single')
  const [progress, setProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState(0)
  const [skippedDuplicates, setSkippedDuplicates] = useState(0)
  const [pendingUpload, setPendingUpload] = useState<PendingUpload | null>(null)
  const pendingKey = `transcription:pending-upload:${session.tenant.id}`

  useEffect(() => {
    folderInput.current?.setAttribute('webkitdirectory', '')
    apiRequest<ModelProvider[]>('/models', { token: session.access_token })
      .then((items) => {
        const enabled = items.filter((item) => item.is_enabled)
        setProviders(enabled)
        const speech = enabled.filter((item) => item.model_kind === 'speech')
        const text = enabled.filter((item) => item.model_kind === 'text')
        setProviderId(speech.find((item) => item.is_default)?.id ?? speech[0]?.id ?? '')
        setTextProviderId(text.find((item) => item.is_default)?.id ?? text[0]?.id ?? '')
      })
      .catch((reason: Error) => setError(reason.message))
  }, [session.access_token])

  const totalBytes = useMemo(() => files.reduce((sum, file) => sum + file.size, 0), [files])
  const selectedProvider = providers.find((provider) => provider.id === providerId)
  const speechProviders = providers.filter((provider) => provider.model_kind === 'speech')
  const textProviders = providers.filter((provider) => provider.model_kind === 'text')
  const supportsDiarization = selectedProvider?.capabilities.includes('diarization') ?? false
  const diarize = speakerMode !== 'single' && supportsDiarization

  const chooseFiles = (incoming: FileList | null) => {
    if (!incoming) return
    const selected = Array.from(incoming) as BrowserFile[]
    const size = selected.reduce((sum, file) => sum + file.size, 0)
    setError(uploadBatchSizeError(size))
    setFiles(selected)
    setProgress(0)
    setSubmitted(0)
    setSkippedDuplicates(0)
    setMessage('')
    try {
      const stored = localStorage.getItem(pendingKey)
      const pending = stored ? JSON.parse(stored) as PendingUpload : null
      if (pending?.fingerprint === selectionFingerprint(selected)) {
        setPendingUpload(pending)
        setMessage('检测到相同文件的未完成批次，将从服务器已有分块继续上传。')
      } else {
        setPendingUpload(null)
      }
    } catch {
      localStorage.removeItem(pendingKey)
      setPendingUpload(null)
    }
  }

  const submit = async () => {
    if (!providerId || !textProviderId || files.length === 0 || totalBytes > MAX_BATCH_BYTES) return
    setBusy(true)
    setSubmitted(0)
    setSkippedDuplicates(0)
    setProgress(0)
    setError('')
    const controller = new AbortController()
    uploadController.current = controller
    try {
      setMessage('正在计算文件指纹并检查历史文件…')
      const fingerprinted: Array<{ file: BrowserFile; sha256: string }> = []
      const seen = new Set<string>()
      let duplicateSelectionCount = 0
      for (const file of files) {
        const sha256 = await fileSha256(file)
        const key = `${file.size}:${sha256}`
        if (seen.has(key)) {
          duplicateSelectionCount += 1
          continue
        }
        seen.add(key)
        fingerprinted.push({ file, sha256 })
      }
      const activeFiles = fingerprinted.map((item) => item.file)
      if (duplicateSelectionCount) setFiles(activeFiles)
      let batch = pendingUpload?.fingerprint === selectionFingerprint(activeFiles)
        ? pendingUpload.batch
        : null
      if (!batch) {
        batch = await apiRequest<UploadBatch>('/uploads/batches', {
          method: 'POST',
          token: session.access_token,
          body: {
            name: `转写任务 ${new Date().toLocaleString()}`,
            files: fingerprinted.map(({ file, sha256 }) => ({
              relative_path: relativePath(file),
              size_bytes: file.size,
              media_type: file.type || null,
              archive_type: archiveType(file.name),
              sha256,
            })),
          },
        })
        const pending = { fingerprint: selectionFingerprint(activeFiles), batch }
        localStorage.setItem(pendingKey, JSON.stringify(pending))
        setPendingUpload(pending)
      }
      const freshRecords = batch.files.filter((file) => !file.deduplicated)
      const reused = batch.files.length - freshRecords.length
      const skipped = reused + duplicateSelectionCount
      setSkippedDuplicates(skipped)
      if (freshRecords.length === 0) {
        setFiles([])
        setMessage(`检测到 ${skipped} 个完全相同的历史文件，已阻止重复上传和重复解析。可前往历史文件选择其他模型重新解析。`)
        localStorage.removeItem(pendingKey)
        setPendingUpload(null)
        return
      }
      const uploadTotal = freshRecords.reduce((sum, record) => sum + record.size_bytes, 0)
      setMessage(skipped ? `已跳过 ${skipped} 个重复文件，正在上传其余新文件…` : '正在上传文件…')
      let uploadedBytes = 0
      const readyFileIds: string[] = []
      for (const record of freshRecords) {
        const file = activeFiles.find((item) => relativePath(item) === record.relative_path)
        if (!file) throw new Error(`找不到本地文件：${record.relative_path}`)
        const state = await apiRequest<{ received_chunks: number[] }>(`/uploads/files/${record.id}`, {
          token: session.access_token,
        })
        const received = new Set(state.received_chunks)
        for (let index = 0; index < record.expected_chunks; index += 1) {
          const start = index * record.chunk_size
          const chunk = file.slice(start, Math.min(start + record.chunk_size, file.size))
          if (!received.has(index)) {
            await apiBinaryRequest(
              `/uploads/files/${record.id}/chunks/${index}`,
              chunk,
              session.access_token,
              { 'Content-Type': 'application/octet-stream', 'X-Chunk-SHA256': await blobSha256(chunk) },
              controller.signal,
            )
          }
          uploadedBytes += chunk.size
          setProgress(Math.round((uploadedBytes / uploadTotal) * 100))
        }
        const completed = await apiRequest<{ ready_file_ids: string[] }>(`/uploads/files/${record.id}/complete`, {
          method: 'POST',
          token: session.access_token,
        })
        readyFileIds.push(...completed.ready_file_ids)
      }
      const jobs = await apiRequest<TranscriptionJob[]>('/jobs', {
        method: 'POST',
        token: session.access_token,
        body: {
          provider_id: providerId,
          text_provider_id: textProviderId,
          uploaded_file_ids: [...new Set(readyFileIds)],
          language: 'Chinese',
          diarize,
          speaker_mode: speakerMode,
        },
      })
      setProgress(100)
      setSubmitted(jobs.length)
      setMessage(`提交成功：${jobs.length} 个新录音已生成独立任务，工作空间每 5 秒更新进度。${skipped ? ` 已跳过 ${skipped} 个重复文件。` : ''}`)
      localStorage.removeItem(pendingKey)
      setPendingUpload(null)
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === 'AbortError') {
        setMessage('上传已暂停。再次点击上传会查询服务端分块并继续。')
      } else {
        setError(reason instanceof Error ? reason.message : '上传失败。')
      }
    } finally {
      uploadController.current = null
      setBusy(false)
    }
  }

  const cancelPendingUpload = async () => {
    if (!pendingUpload) return
    try {
      await apiRequest(`/uploads/batches/${pendingUpload.batch.id}/cancel`, {
        method: 'POST',
        token: session.access_token,
      })
      localStorage.removeItem(pendingKey)
      setPendingUpload(null)
      setProgress(0)
      setMessage('未提交的上传批次已取消，服务器暂存分块已清理。')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '取消上传失败。')
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <Card className="border-4 py-7 shadow-[8px_8px_0_0_var(--border)] [--card-spacing:--spacing(7)]">
        <CardHeader className="gap-3">
          <CardTitle className="font-head text-3xl">提交转写任务</CardTitle>
          <CardDescription className="text-base leading-7">一次可选择多个录音；提交后每个录音都会成为工作空间中的独立任务和独立详情页。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-7">
          <div className="space-y-3">
            <Label className="text-base" htmlFor="provider">语音模型方案</Label>
            <Select value={providerId} onValueChange={(value) => setProviderId(value)}><SelectTrigger id="provider"><SelectValue placeholder="选择语音识别模型" /></SelectTrigger><SelectContent><SelectGroup>{speechProviders.map((provider) => <SelectItem key={provider.id} value={provider.id}>{provider.provider_type === 'local' ? '本地模型' : provider.provider_type === 'stepfun' ? 'StepFun' : 'API 语音模型'} · {provider.name}</SelectItem>)}</SelectGroup></SelectContent></Select>
          </div>
          <div className="space-y-3">
            <Label className="text-base" htmlFor="text-provider">文本模型方案</Label>
            <Select value={textProviderId} onValueChange={(value) => setTextProviderId(value)}><SelectTrigger id="text-provider"><SelectValue placeholder="选择文本整理模型" /></SelectTrigger><SelectContent><SelectGroup>{textProviders.map((provider) => <SelectItem key={provider.id} value={provider.id}>{provider.provider_type === 'deepseek' ? 'DeepSeek' : 'API 文本模型'} · {provider.name}</SelectItem>)}</SelectGroup></SelectContent></Select>
            {textProviders.length === 0 && <Alert variant="destructive"><AlertTitle>尚未配置文本模型</AlertTitle><AlertDescription>请先前往“模型”页面添加 DeepSeek 或 OpenAI 兼容文本模型，配置 API 地址、模型 ID 和密钥。</AlertDescription></Alert>}
          </div>
          <div className="space-y-3">
            <Label className="text-base" htmlFor="speaker-mode">录音人数</Label>
            <Select value={speakerMode} onValueChange={(value) => setSpeakerMode(value as SpeakerMode)}><SelectTrigger id="speaker-mode"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="single">单人</SelectItem><SelectItem value="double">双人</SelectItem><SelectItem value="multiple">多人</SelectItem></SelectGroup></SelectContent></Select>
            <p className="font-mono text-xs leading-5 text-muted-foreground">ASR 完成后，DeepSeek 会按所选人数恢复用户轮次，并修正明确的关键词和专业术语。</p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <Label className="grid min-h-44 cursor-pointer place-items-center border-4 border-dashed border-border bg-muted/40 p-6 text-center shadow-[5px_5px_0_0_var(--border)]">
              <span><FileAudio className="mx-auto mb-3 size-9" />选择多个音频或压缩包</span>
              <Input className="hidden" type="file" multiple accept="audio/*,.zip,.tar,.tar.gz,.tgz" onChange={(event) => chooseFiles(event.target.files)} />
            </Label>
            <Label className="grid min-h-44 cursor-pointer place-items-center border-4 border-dashed border-border bg-muted/40 p-6 text-center shadow-[5px_5px_0_0_var(--border)]">
              <span><FolderOpen className="mx-auto mb-3 size-9" />选择文件夹</span>
              <Input ref={folderInput} className="hidden" type="file" multiple onChange={(event) => chooseFiles(event.target.files)} />
            </Label>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4 border-2 border-border bg-background p-4 font-mono text-sm">
            <span>{files.length} 个文件 · {(totalBytes / 1024 ** 2).toFixed(1)} MiB</span>
            <span>{speakerMode === 'single' ? '单人整理' : supportsDiarization ? 'ASR 说话人分离 + DeepSeek 整理' : 'DeepSeek 语义拆分'}</span>
          </div>
          {files.some((file) => archiveType(file.name)) && <Badge><Archive className="size-3" />包含压缩包</Badge>}
          {(busy || progress > 0) && <div className="space-y-2"><div className="flex justify-between font-mono text-xs"><span>{busy ? '上传处理中' : '上传完成'}</span><strong>{progress}%</strong></div><Progress value={progress} /></div>}
          {error && <Alert variant="destructive"><AlertTitle>操作失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
          {message && <Alert status={submitted ? 'success' : skippedDuplicates ? 'warning' : undefined} className={submitted || skippedDuplicates ? 'border-4 shadow-[5px_5px_0_0_var(--border)]' : ''}><AlertTitle>{submitted ? <span className="flex items-center gap-2"><CheckCircle2 />提交成功</span> : skippedDuplicates ? '已跳过重复文件' : '任务状态'}</AlertTitle><AlertDescription className="mt-2 gap-4 text-sm leading-6"><p>{message}</p>{submitted > 0 && <Button onClick={onOpenTasks}>前往工作空间监测任务</Button>}{submitted === 0 && skippedDuplicates > 0 && <Button onClick={onOpenHistory}>前往历史文件</Button>}</AlertDescription></Alert>}
          <div className="flex flex-wrap gap-3"><Button className="h-12 px-6 text-base" disabled={busy || !providerId || !textProviderId || files.length === 0 || totalBytes > MAX_BATCH_BYTES} onClick={submit}>{busy ? <Upload className="animate-pulse" /> : <Play />}上传并开始转写</Button>{busy && <Button className="h-12" variant="outline" onClick={() => uploadController.current?.abort()}>暂停上传</Button>}{pendingUpload && !busy && <Button className="h-12" variant="outline" onClick={cancelPendingUpload}>取消批次</Button>}</div>
        </CardContent>
      </Card>
    </div>
  )
}
