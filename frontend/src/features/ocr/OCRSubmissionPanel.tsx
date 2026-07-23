import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, FileImage, FileText, Files, Play, Upload } from 'lucide-react'
import { createSHA256 } from 'hash-wasm'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
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
  type OCRJob,
  type UploadBatch,
} from '@/lib/api'

const MAX_BATCH_BYTES = 5 * 1024 ** 3
const HASH_CHUNK_BYTES = 8 * 1024 ** 2
type DocumentKind = 'pdf' | 'image'
type FileAttribute = 'resume' | 'document'
type PendingUpload = { fingerprint: string; batch: UploadBatch }

type Props = {
  session: AuthPayload
  onOpenTasks: () => void
  onOpenHistory: (kind: DocumentKind) => void
}

function selectionFingerprint(files: File[]) {
  return JSON.stringify(
    files
      .map((file) => [file.name, file.size, file.lastModified])
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

function matchesKind(file: File, kind: DocumentKind) {
  const name = file.name.toLowerCase()
  if (kind === 'pdf') return file.type === 'application/pdf' || name.endsWith('.pdf')
  return file.type.startsWith('image/') || /\.(png|jpe?g|webp|bmp|tiff?)$/.test(name)
}

export function OCRSubmissionPanel({ session, onOpenTasks, onOpenHistory }: Props) {
  const uploadController = useRef<AbortController | null>(null)
  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [ocrProviderId, setOcrProviderId] = useState('')
  const [textProviderId, setTextProviderId] = useState('')
  const [documentKind, setDocumentKind] = useState<DocumentKind>('pdf')
  const [fileAttribute, setFileAttribute] = useState<FileAttribute>('resume')
  const [files, setFiles] = useState<File[]>([])
  const [progress, setProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState(0)
  const [pendingUpload, setPendingUpload] = useState<PendingUpload | null>(null)
  const pendingKey = `ocr:pending-upload:${session.tenant.id}`

  useEffect(() => {
    apiRequest<ModelProvider[]>('/models', { token: session.access_token })
      .then((items) => {
        const enabled = items.filter((item) => item.is_enabled)
        setProviders(enabled)
        const ocr = enabled.filter((item) => item.model_kind === 'ocr')
        const text = enabled.filter((item) => item.model_kind === 'text')
        setOcrProviderId(ocr.find((item) => item.is_default)?.id ?? ocr[0]?.id ?? '')
        setTextProviderId(text.find((item) => item.is_default)?.id ?? text[0]?.id ?? '')
      })
      .catch((reason: Error) => setError(reason.message))
  }, [session.access_token])

  const ocrProviders = providers.filter((provider) => provider.model_kind === 'ocr')
  const textProviders = providers.filter((provider) => provider.model_kind === 'text')
  const totalBytes = useMemo(() => files.reduce((sum, file) => sum + file.size, 0), [files])

  const chooseFiles = (incoming: FileList | null) => {
    if (!incoming) return
    const selected = Array.from(incoming)
    if (selected.some((file) => !matchesKind(file, documentKind))) {
      setFiles([])
      setError(documentKind === 'pdf' ? '当前模式只能选择 PDF 文件。' : '当前模式只能选择图片文件。')
      return
    }
    const size = selected.reduce((sum, file) => sum + file.size, 0)
    setError(size > MAX_BATCH_BYTES ? '单次上传总量不能超过 5 GiB。' : '')
    setFiles(selected)
    setProgress(0)
    setSubmitted(0)
    setMessage('')
    try {
      const stored = localStorage.getItem(pendingKey)
      const pending = stored ? JSON.parse(stored) as PendingUpload : null
      if (pending?.fingerprint === selectionFingerprint(selected)) {
        setPendingUpload(pending)
        setMessage('检测到相同文件的未完成批次，将继续上传已有分块。')
      } else {
        setPendingUpload(null)
      }
    } catch {
      localStorage.removeItem(pendingKey)
      setPendingUpload(null)
    }
  }

  const changeKind = (kind: DocumentKind) => {
    setDocumentKind(kind)
    setFiles([])
    setPendingUpload(null)
    setProgress(0)
    setMessage('')
    setError('')
  }

  const submit = async () => {
    if (!ocrProviderId || !textProviderId || files.length === 0 || totalBytes > MAX_BATCH_BYTES) return
    setBusy(true)
    setProgress(0)
    setSubmitted(0)
    setError('')
    const controller = new AbortController()
    uploadController.current = controller
    try {
      setMessage('正在计算文档指纹并准备上传…')
      const fingerprinted = await Promise.all(files.map(async (file) => ({ file, sha256: await fileSha256(file) })))
      let batch = pendingUpload?.fingerprint === selectionFingerprint(files) ? pendingUpload.batch : null
      if (!batch) {
        batch = await apiRequest<UploadBatch>('/uploads/batches', {
          method: 'POST',
          token: session.access_token,
          body: {
            name: `OCR 识别 ${new Date().toLocaleString()}`,
            files: fingerprinted.map(({ file, sha256 }) => ({
              relative_path: file.name,
              size_bytes: file.size,
              media_type: file.type || null,
              file_kind: documentKind,
              sha256,
            })),
          },
        })
        const pending = { fingerprint: selectionFingerprint(files), batch }
        localStorage.setItem(pendingKey, JSON.stringify(pending))
        setPendingUpload(pending)
      }
      const freshRecords = batch.files.filter((record) => !record.deduplicated)
      const uploadTotal = freshRecords.reduce((sum, record) => sum + record.size_bytes, 0)
      let uploadedBytes = 0
      const readyFileIds = batch.files.filter((record) => record.deduplicated).map((record) => record.id)
      for (const record of freshRecords) {
        const file = files.find((item) => item.name === record.relative_path)
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
          setProgress(uploadTotal ? Math.round((uploadedBytes / uploadTotal) * 100) : 100)
        }
        const completed = await apiRequest<{ ready_file_ids: string[] }>(`/uploads/files/${record.id}/complete`, {
          method: 'POST',
          token: session.access_token,
        })
        readyFileIds.push(...completed.ready_file_ids)
      }
      const jobs = await apiRequest<OCRJob[]>('/ocr/jobs', {
        method: 'POST',
        token: session.access_token,
        body: {
          ocr_provider_id: ocrProviderId,
          text_provider_id: textProviderId,
          uploaded_file_ids: [...new Set(readyFileIds)],
          document_kind: documentKind,
          file_attribute: fileAttribute,
        },
      })
      setProgress(100)
      setSubmitted(jobs.length)
      setFiles([])
      setMessage(`解析任务已创建：${jobs.length} 个${documentKind === 'pdf' ? 'PDF' : '图片'}文件。`)
      localStorage.removeItem(pendingKey)
      setPendingUpload(null)
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === 'AbortError') {
        setMessage('上传已暂停；再次点击“解析”会从服务器已有分块继续。')
      } else {
        setError(reason instanceof Error ? reason.message : 'OCR 任务创建失败。')
      }
    } finally {
      uploadController.current = null
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <Card className="border-4 py-7 shadow-[8px_8px_0_0_var(--border)] [--card-spacing:--spacing(7)]">
        <CardHeader className="gap-3">
          <CardTitle className="font-head text-3xl">OCR 识别</CardTitle>
          <CardDescription className="text-base leading-7">选择 OCR 模型与文本校对模型，可一次解析单个或多个 PDF/图片文件；每个文件生成独立工作空间任务。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-7">
          <div className="space-y-3"><Label className="text-base" htmlFor="ocr-provider">OCR 模型</Label><Select value={ocrProviderId} onValueChange={setOcrProviderId}><SelectTrigger id="ocr-provider"><SelectValue placeholder="选择 OCR 模型" /></SelectTrigger><SelectContent><SelectGroup>{ocrProviders.map((provider) => <SelectItem key={provider.id} value={provider.id}>PaddleOCR · {provider.name}</SelectItem>)}</SelectGroup></SelectContent></Select>{ocrProviders.length === 0 && <Alert variant="destructive"><AlertTitle>尚未配置 OCR 模型</AlertTitle><AlertDescription>请先前往“模型”页面添加 PaddleOCR 模型。</AlertDescription></Alert>}</div>
          <div className="space-y-3"><Label className="text-base" htmlFor="ocr-text-provider">文本模型</Label><Select value={textProviderId} onValueChange={setTextProviderId}><SelectTrigger id="ocr-text-provider"><SelectValue placeholder="选择文本校对模型" /></SelectTrigger><SelectContent><SelectGroup>{textProviders.map((provider) => <SelectItem key={provider.id} value={provider.id}>{provider.name} · {provider.model_name}</SelectItem>)}</SelectGroup></SelectContent></Select>{textProviders.length === 0 && <Alert variant="destructive"><AlertTitle>尚未配置文本模型</AlertTitle><AlertDescription>OCR 原始结果需要文本模型完成结构与错字校对。</AlertDescription></Alert>}</div>
          <div className="space-y-3"><Label className="text-base" htmlFor="document-kind">文件类型</Label><Select value={documentKind} onValueChange={(value) => changeKind(value as DocumentKind)}><SelectTrigger id="document-kind"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="pdf">PDF</SelectItem><SelectItem value="image">图片</SelectItem></SelectGroup></SelectContent></Select></div>
          <div className="space-y-3"><Label className="text-base" htmlFor="file-attribute">文件属性</Label><Select value={fileAttribute} onValueChange={(value) => setFileAttribute(value as FileAttribute)}><SelectTrigger id="file-attribute"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="resume">简历</SelectItem><SelectItem value="document">文档</SelectItem></SelectGroup></SelectContent></Select></div>
          <div className="grid gap-5 sm:grid-cols-2">
            <Label className="grid min-h-44 cursor-pointer place-items-center border-4 border-dashed border-border bg-muted/40 p-6 text-center shadow-[5px_5px_0_0_var(--border)]"><span>{documentKind === 'pdf' ? <FileText className="mx-auto mb-3 size-9" /> : <FileImage className="mx-auto mb-3 size-9" />}选择单个{documentKind === 'pdf' ? 'PDF' : '图片'}</span><Input className="hidden" type="file" accept={documentKind === 'pdf' ? 'application/pdf,.pdf' : 'image/*,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff'} onChange={(event) => chooseFiles(event.target.files)} /></Label>
            <Label className="grid min-h-44 cursor-pointer place-items-center border-4 border-dashed border-border bg-muted/40 p-6 text-center shadow-[5px_5px_0_0_var(--border)]"><span><Files className="mx-auto mb-3 size-9" />选择多个{documentKind === 'pdf' ? 'PDF' : '图片'}</span><Input className="hidden" type="file" multiple accept={documentKind === 'pdf' ? 'application/pdf,.pdf' : 'image/*,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff'} onChange={(event) => chooseFiles(event.target.files)} /></Label>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4 border-2 border-border bg-background p-4 font-mono text-sm"><span>{files.length} 个文件 · {(totalBytes / 1024 ** 2).toFixed(1)} MiB</span><span>{documentKind === 'pdf' ? 'PDF 文档解析' : '图片文字识别'}</span></div>
          {(busy || progress > 0) && <div className="space-y-2"><div className="flex justify-between font-mono text-xs"><span>{busy ? '上传处理中' : '上传完成'}</span><strong>{progress}%</strong></div><Progress value={progress} /></div>}
          {error && <Alert variant="destructive"><AlertTitle>操作失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
          {message && <Alert status={submitted ? 'success' : undefined} className={submitted ? 'border-4 shadow-[5px_5px_0_0_var(--border)]' : ''}><AlertTitle>{submitted ? <span className="flex items-center gap-2"><CheckCircle2 />任务已创建</span> : '任务状态'}</AlertTitle><AlertDescription className="mt-2 gap-4 text-sm leading-6"><p>{message}</p>{submitted > 0 && <div className="flex flex-wrap gap-3"><Button onClick={onOpenTasks}>前往工作空间查看</Button><Button variant="outline" onClick={() => onOpenHistory(documentKind)}>查看历史文件</Button></div>}</AlertDescription></Alert>}
          <div className="flex flex-wrap gap-3"><Button className="h-12 px-8 text-base" disabled={busy || !ocrProviderId || !textProviderId || files.length === 0 || totalBytes > MAX_BATCH_BYTES} onClick={submit}>{busy ? <Upload className="animate-pulse" /> : <Play />}解析</Button>{busy && <Button className="h-12" variant="outline" onClick={() => uploadController.current?.abort()}>暂停上传</Button>}</div>
        </CardContent>
      </Card>
    </div>
  )
}
