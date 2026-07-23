import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { Cloud, Cpu, FileScan, FileText, Pencil, Plus, Trash2 } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { apiRequest, type AuthPayload, type ModelProvider } from '@/lib/api'

type Props = { session: AuthPayload }
type ModelKind = 'speech' | 'text' | 'ocr'
type ApiProviderType = 'stepfun' | 'openai_compatible' | 'deepseek' | 'paddleocr'
type ProviderHealth = { status: 'available' | 'unavailable' | 'misconfigured'; latency_ms: number | null; detail: string }
type FormValues = { name: string; baseUrl: string; modelName: string; apiKey: string }

const defaults: Record<ModelKind, Record<string, FormValues>> = {
  speech: {
    stepfun: { name: 'StepFun 云端 ASR', baseUrl: 'https://api.stepfun.com/v1', modelName: 'stepaudio-2.5-asr', apiKey: '' },
    openai_compatible: { name: 'OpenAI 兼容语音模型', baseUrl: 'https://api.example.com/v1', modelName: 'whisper-1', apiKey: '' },
  },
  text: {
    deepseek: { name: 'DeepSeek 文本整理', baseUrl: 'https://api.deepseek.com', modelName: 'deepseek-v4-flash', apiKey: '' },
    openai_compatible: { name: 'OpenAI 兼容文本模型', baseUrl: 'https://api.example.com/v1', modelName: 'chat-model-id', apiKey: '' },
  },
  ocr: {
    paddleocr: { name: 'PaddleOCR 文档识别', baseUrl: 'https://paddleocr.aistudio-app.com/api/v2/ocr', modelName: 'PaddleOCR-VL-1.6', apiKey: '' },
  },
}

export function ModelPanel({ session }: Props) {
  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<ModelProvider | null>(null)
  const [saving, setSaving] = useState(false)
  const [health, setHealth] = useState<Record<string, ProviderHealth>>({})
  const [testing, setTesting] = useState('')
  const [deleting, setDeleting] = useState('')
  const [pendingDelete, setPendingDelete] = useState<ModelProvider | null>(null)
  const [modelKind, setModelKind] = useState<ModelKind>('speech')
  const [providerType, setProviderType] = useState<ApiProviderType>('stepfun')
  const [formValues, setFormValues] = useState<FormValues>(defaults.speech.stepfun)
  const canWrite = session.permissions.includes('models:write')

  const load = useCallback(() => {
    apiRequest<ModelProvider[]>('/models', { token: session.access_token }).then(setProviders).catch((reason: Error) => setError(reason.message))
  }, [session.access_token])

  useEffect(load, [load])

  const chooseType = (kind: ModelKind, type: ApiProviderType) => {
    const validType: ApiProviderType = kind === 'speech'
      ? type === 'openai_compatible' ? 'openai_compatible' : 'stepfun'
      : kind === 'text'
        ? type === 'openai_compatible' ? 'openai_compatible' : 'deepseek'
        : 'paddleocr'
    setModelKind(kind)
    setProviderType(validType)
    setFormValues(defaults[kind][validType])
  }

  const startCreate = () => {
    setEditing(null)
    chooseType('speech', 'stepfun')
    setShowForm(true)
  }

  const startEdit = (provider: ModelProvider) => {
    setEditing(provider)
    setModelKind(provider.model_kind)
    setProviderType(provider.provider_type as ApiProviderType)
    setFormValues({ name: provider.name, baseUrl: provider.base_url, modelName: provider.model_name, apiKey: '' })
    setShowForm(true)
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      await apiRequest(editing ? `/models/${editing.id}` : '/models', {
        method: editing ? 'PUT' : 'POST',
        token: session.access_token,
        body: {
          name: formValues.name,
          base_url: formValues.baseUrl,
          model_name: formValues.modelName,
          ...(!editing ? { model_kind: modelKind, provider_type: providerType } : {}),
          ...(formValues.apiKey ? { api_key: formValues.apiKey } : {}),
        },
      })
      setShowForm(false)
      setEditing(null)
      load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存失败。')
    } finally {
      setSaving(false)
    }
  }

  const testProvider = async (providerId: string) => {
    setTesting(providerId)
    try {
      const result = await apiRequest<ProviderHealth>(`/models/${providerId}/test`, { method: 'POST', token: session.access_token })
      setHealth((current) => ({ ...current, [providerId]: result }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '测试失败。')
    } finally {
      setTesting('')
    }
  }

  const setDefaultProvider = async (providerId: string) => {
    try {
      await apiRequest(`/models/${providerId}/default`, { method: 'POST', token: session.access_token })
      load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '默认模型设置失败。')
    }
  }

  const deleteProvider = async () => {
    if (!pendingDelete) return
    setDeleting(pendingDelete.id)
    setError('')
    try {
      await apiRequest(`/models/${pendingDelete.id}`, {
        method: 'DELETE',
        token: session.access_token,
      })
      setHealth((current) => {
        const next = { ...current }
        delete next[pendingDelete.id]
        return next
      })
      setPendingDelete(null)
      load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '模型删除失败。')
    } finally {
      setDeleting('')
    }
  }

  const renderProviders = (kind: ModelKind) => {
    const items = providers.filter((provider) => provider.model_kind === kind)
    if (items.length === 0) return <div className="grid min-h-40 place-items-center border-4 border-dashed border-border bg-muted/40 p-6 text-center"><p className="font-mono text-sm">尚未配置{kind === 'speech' ? '语音' : kind === 'text' ? '文本' : 'OCR'}模型</p></div>
    return <div className="grid gap-4 md:grid-cols-2">{items.map((provider) => {
      const ProviderIcon = provider.provider_type === 'local' ? Cpu : kind === 'text' ? FileText : kind === 'ocr' ? FileScan : Cloud
      return <Card key={provider.id} className="border-4 shadow-[5px_5px_0_0_var(--border)]"><CardHeader><div className="flex items-start justify-between gap-3"><div className="flex gap-3"><div className="grid size-11 place-items-center border-2 border-border bg-primary shadow-sm"><ProviderIcon /></div><div><CardTitle className="font-head text-xl">{provider.name}</CardTitle><CardDescription>{provider.model_name}</CardDescription></div></div>{provider.is_default && <Badge>默认{kind === 'speech' ? '语音' : kind === 'text' ? '文本' : 'OCR'}</Badge>}</div></CardHeader><CardContent className="space-y-3 font-mono text-xs"><div className="flex justify-between border-b-2 border-border pb-2"><span>模型分类</span><strong>{kind === 'speech' ? '语音模型' : kind === 'text' ? '文本模型' : 'OCR 模型'}</strong></div><div className="flex justify-between border-b-2 border-border pb-2"><span>调用方式</span><strong>{provider.provider_type === 'local' ? '本地 MLX' : provider.provider_type === 'deepseek' ? 'DeepSeek API' : provider.provider_type === 'paddleocr' ? 'PaddleOCR API' : 'API 接口'}</strong></div><div className="break-all text-muted-foreground">{provider.base_url}</div><div className="flex flex-wrap gap-2">{provider.capabilities.map((item) => <Badge key={item} variant="outline">{item}</Badge>)}<Badge variant="outline">密钥：{provider.has_api_key ? '已配置' : '未配置'}</Badge></div>{health[provider.id] && <div className={`border-t-2 border-border pt-2 font-semibold ${health[provider.id].status === 'available' ? 'text-emerald-700' : 'text-destructive'}`}>{health[provider.id].status} · {health[provider.id].latency_ms ?? '-'} ms · {health[provider.id].detail}</div>}{canWrite && <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" disabled={testing === provider.id} onClick={() => testProvider(provider.id)}>{testing === provider.id ? '测试中…' : '测试连接'}</Button>{!provider.is_default && <Button size="sm" variant="outline" onClick={() => setDefaultProvider(provider.id)}>设为默认</Button>}{(!provider.is_system || kind === 'ocr') && <Button size="sm" variant="outline" onClick={() => startEdit(provider)}><Pencil />编辑配置</Button>}<Button size="sm" variant="destructive" disabled={deleting === provider.id} onClick={() => setPendingDelete(provider)}><Trash2 />{deleting === provider.id ? '删除中…' : '删除模型'}</Button></div>}</CardContent></Card>
    })}</div>
  }

  return <div className="mx-auto w-full max-w-7xl space-y-8">
    <div className="flex flex-wrap items-center justify-between gap-5"><div><h1 className="font-head text-4xl">模型方案</h1><p className="mt-2 text-base text-muted-foreground">语音模型识别音频，OCR 模型解析图片/PDF，文本模型负责结果校对；配置按租户隔离。</p></div>{canWrite && <Button className="h-12 px-6 text-base" onClick={startCreate}><Plus className="size-5" />添加 API 模型</Button>}</div>
    {error && <Alert variant="destructive"><AlertTitle>模型配置错误</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
    {showForm && <Card className="border-4 py-8 shadow-[8px_8px_0_0_var(--border)] [--card-spacing:--spacing(8)]"><CardHeader className="gap-3"><CardTitle className="font-head text-3xl">{editing ? '编辑 API 模型' : '添加 API 模型'}</CardTitle><CardDescription className="max-w-3xl text-base leading-7">API 密钥将在后端加密后保存到当前租户的 PostgreSQL 数据中，页面和后续接口不会返回密钥原文。</CardDescription></CardHeader><CardContent><form onSubmit={submit} className="grid gap-7 md:grid-cols-2">
      <div className="space-y-3"><Label className="text-base" htmlFor="model-kind">模型分类</Label><Select disabled={Boolean(editing)} value={modelKind} onValueChange={(value) => chooseType(value as ModelKind, value === 'speech' ? 'stepfun' : value === 'ocr' ? 'paddleocr' : 'deepseek')}><SelectTrigger id="model-kind"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="speech">语音模型</SelectItem><SelectItem value="text">文本模型</SelectItem><SelectItem value="ocr">OCR 模型</SelectItem></SelectGroup></SelectContent></Select><p className="text-sm leading-6 text-muted-foreground">语音模型识别音频；OCR 模型解析图片/PDF；文本模型校对两类识别结果。</p></div>
      <div className="space-y-3"><Label className="text-base" htmlFor="provider-type">API 类型</Label><Select disabled={Boolean(editing)} value={providerType} onValueChange={(value) => chooseType(modelKind, value as ApiProviderType)}><SelectTrigger id="provider-type"><SelectValue /></SelectTrigger><SelectContent><SelectGroup>{modelKind === 'speech' ? <><SelectItem value="stepfun">StepFun 语音 ASR</SelectItem><SelectItem value="openai_compatible">OpenAI 兼容语音 API</SelectItem></> : modelKind === 'text' ? <><SelectItem value="deepseek">DeepSeek 文本 API</SelectItem><SelectItem value="openai_compatible">OpenAI 兼容文本 API</SelectItem></> : <SelectItem value="paddleocr">PaddleOCR 文档解析 API</SelectItem>}</SelectGroup></SelectContent></Select><p className="text-sm leading-6 text-muted-foreground">选择后会填入适合该服务的 URL 和模型 ID 示例。</p></div>
      <div className="space-y-3"><Label className="text-base" htmlFor="display-name">显示名称</Label><Input id="display-name" value={formValues.name} onChange={(event) => setFormValues({ ...formValues, name: event.target.value })} required placeholder="例如：生产环境 DeepSeek" autoComplete="off" /><p className="text-sm text-muted-foreground">显示在模型卡片、提交页面和任务记录中，建议包含用途或环境。</p></div>
      <div className="space-y-3"><Label className="text-base" htmlFor="model-id">模型 ID</Label><Input id="model-id" value={formValues.modelName} onChange={(event) => setFormValues({ ...formValues, modelName: event.target.value })} required placeholder={modelKind === 'speech' ? '例如：stepaudio-2.5-asr' : modelKind === 'ocr' ? '例如：PaddleOCR-VL-1.6' : '例如：deepseek-v4-flash'} autoComplete="off" spellCheck={false} /><p className="text-sm text-muted-foreground">填写供应商控制台或文档中用于 API 请求的准确模型标识。</p></div>
      <div className="space-y-3 md:col-span-2"><Label className="text-base" htmlFor="base-url">API Base URL</Label><Input id="base-url" value={formValues.baseUrl} onChange={(event) => setFormValues({ ...formValues, baseUrl: event.target.value })} type="url" required placeholder="例如：https://api.deepseek.com" autoComplete="url" spellCheck={false} /><p className="text-sm text-muted-foreground">填写服务根地址，不要填写具体的 `/chat/completions` 或 `/audio/transcriptions` 路径；外部地址必须使用 HTTPS。</p></div>
      <div className="space-y-3 md:col-span-2"><Label className="text-base" htmlFor="api-key">API Key</Label><Input id="api-key" value={formValues.apiKey} onChange={(event) => setFormValues({ ...formValues, apiKey: event.target.value })} type="password" required={!editing} placeholder={editing ? '留空表示保留当前密钥；输入新值则覆盖' : '粘贴供应商生成的 API Key'} autoComplete="new-password" spellCheck={false} /><p className="text-sm text-muted-foreground">密钥只在本次保存请求中提交；保存后仅显示“已配置”，无法从页面读取原值。</p></div>
      <div className="flex flex-wrap gap-3 md:col-span-2"><Button className="h-14 px-7 text-base" disabled={saving}>{saving ? '保存中…' : editing ? '保存修改' : '保存 API 模型'}</Button><Button className="h-14" type="button" variant="outline" onClick={() => { setShowForm(false); setEditing(null) }}>取消</Button></div>
    </form></CardContent></Card>}
    <section className="space-y-4"><h2 className="font-head text-3xl">语音模型</h2>{renderProviders('speech')}</section>
    <section className="space-y-4"><h2 className="font-head text-3xl">文本模型</h2>{renderProviders('text')}</section>
    <section className="space-y-4"><h2 className="font-head text-3xl">OCR 模型</h2>{renderProviders('ocr')}</section>
    <AlertDialog open={Boolean(pendingDelete)} onOpenChange={(open) => { if (!open && !deleting) setPendingDelete(null) }}>
      <AlertDialogContent>
        <AlertDialogTitle>确认删除模型？</AlertDialogTitle>
        <AlertDialogDescription>
          将删除“{pendingDelete?.name}”的配置和加密凭据。若该模型已被历史转写任务引用，系统会拒绝删除，以保留任务与模型的可追溯关系。
        </AlertDialogDescription>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={Boolean(deleting)}>取消</AlertDialogCancel>
          <AlertDialogAction disabled={Boolean(deleting)} onClick={(event) => { event.preventDefault(); void deleteProvider() }}>
            {deleting ? '删除中…' : '确认删除'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
}
