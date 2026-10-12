import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Download, FilePlus2, FolderSearch, ImagePlus, LayoutGrid, LibraryBig, Loader2, Plus, Save, Search, Trash2, X } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { maskedCandidateName } from '@/features/projects/candidateName'
import { ApiError, apiBinaryRequest, apiDownload, apiRequest, type AuthPayload, type ResumeContent, type ResumeDocument, type ResumeEducationEntry, type ResumeProject, type ResumeProjectEntry, type ResumeSource, type ResumeTemplateDefinition, type ResumeWorkEntry } from '@/lib/api'

import { ResumePreview } from './ResumePreview'

type Props = {
  session: AuthPayload
  documentId: string | null
  onOpenDocument: (id: string) => void
  onBack: () => void
}

const editorSections = [
  ['personal', '基本信息'],
  ['education', '教育背景'],
  ['work', '工作经历'],
  ['projects', '项目经历'],
  ['skills', '技能与证书'],
  ['source', '原文参考'],
] as const

type EditorSection = typeof editorSections[number][0]

function newId() {
  return crypto.randomUUID()
}

function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { className = '', ...rest } = props
  return <textarea className={`min-h-24 w-full resize-y border-2 border-border bg-input px-3 py-2 text-sm shadow-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${className}`} {...rest} />
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <Label className="grid gap-2"><span>{label}</span>{children}</Label>
}

function originalName(path: string) {
  return path.split('/').filter(Boolean).at(-1) ?? path
}

function sourceError(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return '请求失败，请稍后重试。'
}

const templateGroupNames: Record<ResumeTemplateDefinition['group'], string> = {
  local: '本地模板',
}

function TemplateThumbnail({ template }: { template: ResumeTemplateDefinition }) {
  const ribbon = template.key === 'local-template-01' || template.key === 'local-template-05'
  const band = template.key === 'local-template-02'
  const topbar = template.key === 'local-template-03'
  return (
    <div
      className="relative aspect-[210/297] overflow-hidden border border-slate-300 bg-white p-2"
      style={{ '--thumbnail-accent': template.default_color } as React.CSSProperties}
      aria-hidden="true"
    >
      {topbar && <div className="-mx-2 -mt-2 mb-2 h-3 bg-[var(--thumbnail-accent)]" />}
      {template.key === 'local-template-05' && <div className="absolute bottom-2 left-2 top-10 w-px bg-slate-300" />}
      <div>
        <div className={`h-2.5 w-2/5 bg-[var(--thumbnail-accent)] ${template.header_style === 'centered' || template.header_style === 'minimal' ? 'mx-auto' : ''}`} />
        <div className="mt-1 h-1 w-3/5 bg-slate-300" />
        {[0, 1, 2, 3].map((line) => <div className={`mt-2 ${template.key === 'local-template-05' ? 'pl-2' : ''}`} key={line}><div className={`h-1.5 ${ribbon ? 'w-2/5 bg-[var(--thumbnail-accent)]' : band ? 'w-full bg-[color-mix(in_srgb,var(--thumbnail-accent)_18%,white)]' : 'w-1/3 border-b-2 border-[var(--thumbnail-accent)]'}`} /><div className="mt-1 h-1 w-full bg-slate-200" /><div className="mt-1 h-1 w-5/6 bg-slate-200" /></div>)}
      </div>
    </div>
  )
}

function TemplateLibrary({
  open,
  onOpenChange,
  templates,
  selectedKey,
  onSelect,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  templates: ResumeTemplateDefinition[]
  selectedKey: string
  onSelect: (template: ResumeTemplateDefinition) => void
}) {
  const [query, setQuery] = useState('')
  const filtered = templates.filter((template) => {
    const value = query.trim().toLocaleLowerCase()
    return !value || `${template.name} ${template.description} ${template.layout}`.toLocaleLowerCase().includes(value)
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl">
        <DialogHeader>
          <DialogTitle>选择简历模板</DialogTitle>
          <DialogDescription>共 {templates.length} 套本地模板，05 为重点优化的技术履历与自然分页版本。</DialogDescription>
        </DialogHeader>
        <Badge variant="outline">全部 {templates.length} 套 · 本地模板</Badge>
        <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索模板名称、说明或结构" aria-label="搜索模板" />
        <div className="grid max-h-[62vh] gap-3 overflow-y-auto pr-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
          {filtered.map((template) => (
            <button
              type="button"
              className={`grid grid-cols-[72px_1fr] gap-3 border-2 p-2 text-left transition-transform hover:-translate-y-0.5 ${selectedKey === template.key ? 'border-border bg-primary shadow-sm' : 'border-muted bg-background'}`}
              onClick={() => { onSelect(template); onOpenChange(false) }}
              key={template.key}
            >
              <TemplateThumbnail template={template} />
              <span className="min-w-0">
                <strong className="line-clamp-2 text-sm">{template.name}</strong>
                <span className="mt-1 block text-[10px] text-muted-foreground">{template.description}</span>
              </span>
            </button>
          ))}
        </div>
        {filtered.length === 0 && <div className="border-2 border-dashed p-8 text-center text-muted-foreground">没有匹配的模板</div>}
      </DialogContent>
    </Dialog>
  )
}

function TechnologyEditor({
  values,
  onChange,
}: {
  values: string[]
  onChange: (values: string[]) => void
}) {
  const [draft, setDraft] = useState('')
  const addValues = (raw: string) => {
    const additions = raw.split(/[\n,，;；]+/).map((value) => value.trim()).filter(Boolean)
    if (additions.length === 0) return
    onChange([...new Set([...values.map((value) => value.trim()).filter(Boolean), ...additions])])
    setDraft('')
  }
  return (
    <div className="flex min-h-11 flex-wrap items-center gap-2 border-2 border-border bg-input p-2 shadow-sm">
      {values.map((technology, index) => technology.trim() && (
        <Badge className="gap-1" variant="outline" key={`${technology}-${index}`}>
          {technology}
          <button type="button" aria-label={`删除技术栈 ${technology}`} onClick={() => onChange(values.filter((_, itemIndex) => itemIndex !== index))}><X className="size-3" /></button>
        </Badge>
      ))}
      <input
        className="min-w-32 flex-1 bg-transparent px-1 text-sm outline-none"
        value={draft}
        onChange={(event) => {
          const value = event.target.value
          if (/[,，;；\n]/.test(value)) addValues(value)
          else setDraft(value)
        }}
        onBlur={() => addValues(draft)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            addValues(draft)
          }
        }}
        placeholder="输入后按回车或逗号添加"
        aria-label="添加技术栈"
      />
    </div>
  )
}

function projectToResumeEntry(project: ResumeProject): ResumeProjectEntry {
  return {
    id: newId(),
    source_project_id: project.id,
    name: project.project_name,
    company: project.company_name ?? '',
    role: project.role_name ?? '',
    start_date: project.start_date ?? '',
    end_date: project.is_current ? '至今' : (project.end_date ?? ''),
    summary: project.project_background ?? project.description ?? '',
    highlights: project.project_outcomes.length
      ? project.project_outcomes
      : project.project_responsibilities.length
        ? project.project_responsibilities
        : project.responsibilities,
    technologies: project.technologies,
  }
}

function ResumeSourceChooser({ session, onOpenDocument }: Pick<Props, 'session' | 'onOpenDocument'>) {
  const [sources, setSources] = useState<ResumeSource[]>([])
  const [documents, setDocuments] = useState<ResumeDocument[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [pendingDelete, setPendingDelete] = useState<ResumeDocument | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  const load = async (search = '') => {
    setLoading(true)
    setError('')
    try {
      const [sourceRows, documentRows] = await Promise.all([
        apiRequest<ResumeSource[]>(`/resume-writer/sources?limit=${search ? 20 : 5}&query=${encodeURIComponent(search)}`, { token: session.access_token }),
        apiRequest<ResumeDocument[]>('/resume-writer/documents', { token: session.access_token }),
      ])
      setSources(sourceRows)
      setDocuments(documentRows)
    } catch (requestError) {
      setError(sourceError(requestError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const create = async (sourceId: string | null) => {
    setCreating(sourceId ?? 'blank')
    setError('')
    try {
      const document = await apiRequest<ResumeDocument>('/resume-writer/documents', {
        method: 'POST',
        token: session.access_token,
        body: { source_resume_profile_id: sourceId, template_key: 'local-template-05' },
      })
      onOpenDocument(document.id)
    } catch (requestError) {
      setError(sourceError(requestError))
      setCreating(null)
    }
  }

  const deleteDocument = async () => {
    if (!pendingDelete) return
    setDeleting(true)
    setDeleteError('')
    try {
      await apiRequest<void>(`/resume-writer/documents/${pendingDelete.id}`, {
        method: 'DELETE',
        token: session.access_token,
      })
      setPendingDelete(null)
      await load(query)
    } catch (requestError) {
      setDeleteError(sourceError(requestError))
    } finally {
      setDeleting(false)
    }
  }

  return <div className="mx-auto max-w-7xl space-y-6">
    <Card>
      <CardHeader><div className="flex flex-wrap items-start justify-between gap-4"><div><CardTitle className="font-head text-3xl">简历撰写</CardTitle><CardDescription>从最近上传的简历继续，或搜索历史简历。内容会保存为租户内独立草稿。</CardDescription></div><Button variant="outline" onClick={() => create(null)} disabled={creating !== null}><FilePlus2 />新建空白简历</Button></div></CardHeader>
      <CardContent className="space-y-5">
        <form className="flex gap-3" onSubmit={(event) => { event.preventDefault(); void load(query) }}><Input className="h-11" aria-label="搜索简历" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索候选人姓名或原始文件名" /><Button type="submit" disabled={loading}><Search />搜索</Button>{query && <Button type="button" variant="ghost" onClick={() => { setQuery(''); void load('') }}><X />清除</Button>}</form>
        {error && <Alert variant="destructive"><AlertTitle>无法加载简历</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
        <div><h2 className="font-head text-xl">{query ? '搜索结果' : '最近上传的 5 份简历'}</h2><p className="mt-1 text-sm text-muted-foreground">这里只显示 OCR 文件属性为“简历”并已完成结构提取的文件。</p></div>
        {loading ? <div className="grid min-h-40 place-items-center"><Loader2 className="animate-spin" /></div> : sources.length === 0 ? <div className="grid min-h-44 place-items-center border-2 border-dashed border-border bg-muted/30 p-8 text-center"><div><FolderSearch className="mx-auto mb-3 size-9" /><p className="font-head">没有找到可编辑的上传简历</p><p className="mt-2 text-sm text-muted-foreground">请先在 OCR 识别中上传文件，并把文件属性选择为“简历”。</p></div></div> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">{sources.map((source) => <Card className="flex min-h-52 flex-col" key={source.id}><CardHeader className="flex-1"><div className="flex items-center justify-between gap-2"><Badge>{source.project_count} 个项目</Badge>{source.draft_id && <Badge variant="outline">已有草稿</Badge>}</div><CardTitle className="mt-3 truncate text-xl">{source.candidate_name}</CardTitle><CardDescription className="break-all">{originalName(source.source_path)}</CardDescription><p className="font-mono text-[11px] text-muted-foreground">{new Date(source.extracted_at).toLocaleString()}</p></CardHeader><CardContent><Button className="w-full" disabled={creating !== null} onClick={() => source.draft_id ? onOpenDocument(source.draft_id) : create(source.id)}>{creating === source.id ? <Loader2 className="animate-spin" /> : source.draft_id ? '继续编辑' : '基于此简历修改'}</Button></CardContent></Card>)}</div>}
      </CardContent>
    </Card>
    {documents.length > 0 && <Card><CardHeader><CardTitle className="font-head text-2xl">最近编辑的草稿</CardTitle><CardDescription>草稿按照最后保存时间排列，可继续编辑或永久删除。</CardDescription></CardHeader><CardContent className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">{documents.map((document) => <article className="flex items-center gap-2 border-2 border-border bg-background p-2 shadow-sm" key={document.id}><button className="min-w-0 flex-1 p-2 text-left transition-transform hover:translate-x-1" type="button" onClick={() => onOpenDocument(document.id)}><strong className="block truncate">{document.title}</strong><span className="mt-1 block truncate text-xs text-muted-foreground">{document.source_path ? originalName(document.source_path) : '空白简历'} · {new Date(document.updated_at).toLocaleString()}</span></button><Button size="icon" variant="destructive" aria-label={`删除草稿 ${document.title}`} onClick={() => { setDeleteError(''); setPendingDelete(document) }}><Trash2 /></Button></article>)}</CardContent></Card>}
    <AlertDialog open={pendingDelete !== null} onOpenChange={(open) => { if (!open && !deleting) setPendingDelete(null) }}>
      <AlertDialogContent>
        <AlertDialogTitle>删除简历草稿？</AlertDialogTitle>
        <AlertDialogDescription>
          将永久删除“{pendingDelete?.title}”及其草稿照片。原始 OCR 简历和数据简历项目不会被删除，此操作无法撤销。
        </AlertDialogDescription>
        {deleteError && <Alert variant="destructive" className="mt-4"><AlertTitle>删除失败</AlertTitle><AlertDescription>{deleteError}</AlertDescription></Alert>}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleting}>取消</AlertDialogCancel>
          <AlertDialogAction disabled={deleting} onClick={(event) => { event.preventDefault(); void deleteDocument() }}>
            {deleting ? <Loader2 className="animate-spin" /> : <Trash2 />}
            确认删除
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
}

function ResumeEditor({ session, documentId, onBack }: Props & { documentId: string }) {
  const [document, setDocument] = useState<ResumeDocument | null>(null)
  const [projects, setProjects] = useState<ResumeProject[]>([])
  const [templates, setTemplates] = useState<ResumeTemplateDefinition[]>([])
  const [activeSection, setActiveSection] = useState<EditorSection>('personal')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState<'html' | 'pdf' | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [photoUrl, setPhotoUrl] = useState<string | null>(null)
  const [materialOpen, setMaterialOpen] = useState(false)
  const [templateOpen, setTemplateOpen] = useState(false)
  const [materialQuery, setMaterialQuery] = useState('')
  const [selectedMaterials, setSelectedMaterials] = useState<Set<string>>(new Set())

  useEffect(() => {
    let objectUrl: string | null = null
    void Promise.all([
      apiRequest<ResumeDocument>(`/resume-writer/documents/${documentId}`, { token: session.access_token }),
      apiRequest<ResumeProject[]>('/resume-projects', { token: session.access_token }),
      apiRequest<ResumeTemplateDefinition[]>('/resume-writer/templates', { token: session.access_token }),
    ]).then(async ([draft, projectRows, templateRows]) => {
      setDocument(draft)
      setProjects(projectRows)
      setTemplates(templateRows)
      if (draft.has_photo) {
        const blob = await apiDownload(`/resume-writer/documents/${documentId}/photo`, session.access_token)
        objectUrl = URL.createObjectURL(blob)
        setPhotoUrl(objectUrl)
      }
    }).catch((requestError) => setError(sourceError(requestError)))
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [documentId, session.access_token])

  const change = (updater: (current: ResumeDocument) => ResumeDocument) => {
    setDocument((current) => current ? updater(current) : current)
    setDirty(true)
    setMessage('')
  }
  const changeContent = (updater: (current: ResumeContent) => ResumeContent) => change((current) => ({ ...current, content: updater(current.content) }))

  const save = async () => {
    if (!document) return null
    setSaving(true)
    setError('')
    try {
      const saved = await apiRequest<ResumeDocument>(`/resume-writer/documents/${document.id}`, {
        method: 'PUT',
        token: session.access_token,
        body: { title: document.title, template_key: document.template_key, theme_color: document.theme_color, content: document.content },
      })
      setDocument(saved)
      setDirty(false)
      setMessage('已保存到云端')
      return saved
    } catch (requestError) {
      setError(sourceError(requestError))
      return null
    } finally {
      setSaving(false)
    }
  }

  const download = async (format: 'html' | 'pdf') => {
    setExporting(format)
    setError('')
    try {
      const saved = dirty ? await save() : document
      if (!saved) return
      const blob = await apiDownload(`/resume-writer/documents/${saved.id}/export/${format}`, session.access_token)
      const url = URL.createObjectURL(blob)
      const anchor = window.document.createElement('a')
      anchor.href = url
      anchor.download = `resume-${saved.id}.${format}`
      anchor.click()
      URL.revokeObjectURL(url)
      setMessage(`${format.toUpperCase()} 已导出`)
    } catch (requestError) {
      setError(sourceError(requestError))
    } finally {
      setExporting(null)
    }
  }

  const uploadPhoto = async (file: File | undefined) => {
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
      setError('照片仅支持 5 MiB 以内的 JPG、PNG 或 WebP。')
      return
    }
    try {
      await apiBinaryRequest(`/resume-writer/documents/${documentId}/photo`, file, session.access_token, { 'Content-Type': file.type })
      if (photoUrl) URL.revokeObjectURL(photoUrl)
      setPhotoUrl(URL.createObjectURL(file))
      setDocument((current) => current ? { ...current, has_photo: true } : current)
      setMessage('照片已上传')
    } catch (requestError) {
      setError(sourceError(requestError))
    }
  }

  const deletePhoto = async () => {
    await apiRequest<void>(`/resume-writer/documents/${documentId}/photo`, { method: 'DELETE', token: session.access_token })
    if (photoUrl) URL.revokeObjectURL(photoUrl)
    setPhotoUrl(null)
    setDocument((current) => current ? { ...current, has_photo: false } : current)
  }

  const filteredProjects = useMemo(() => {
    const value = materialQuery.trim().toLocaleLowerCase()
    if (!value) return projects
    return projects.filter((project) => [project.project_name, project.company_name, project.role_name, project.candidate_name, ...project.technologies].some((field) => field?.toLocaleLowerCase().includes(value)))
  }, [materialQuery, projects])

  const importMaterials = () => {
    if (!document) return
    const existing = new Set(document.content.projects.map((item) => item.source_project_id).filter(Boolean))
    const additions = projects
      .filter((project) => selectedMaterials.has(project.id) && !existing.has(project.id))
      .map(projectToResumeEntry)
    changeContent((content) => ({ ...content, projects: [...content.projects, ...additions] }))
    setSelectedMaterials(new Set())
    setMaterialOpen(false)
    setMessage(`已引用 ${additions.length} 条项目素材，可继续编辑`)
  }

  const importOneMaterial = (project: ResumeProject) => {
    if (!document) return
    if (document.content.projects.some((item) => item.source_project_id === project.id)) {
      setMessage('该项目已经填充到当前简历')
      return
    }
    changeContent((content) => ({ ...content, projects: [...content.projects, projectToResumeEntry(project)] }))
    setMessage(`已填充项目“${project.project_name}”，可继续编辑`)
  }

  if (!document) return <div className="grid min-h-[60vh] place-items-center">{error ? <Alert variant="destructive" className="max-w-xl"><AlertTitle>无法打开简历</AlertTitle><AlertDescription>{error}</AlertDescription></Alert> : <Loader2 className="animate-spin" />}</div>

  const selectedTemplate = templates.find((template) => template.key === document.template_key)
  const updatePersonal = (key: keyof ResumeContent['personal'], value: string) => changeContent((content) => ({ ...content, personal: { ...content.personal, [key]: value } }))
  const updateEducation = (id: string, patch: Partial<ResumeEducationEntry>) => changeContent((content) => ({ ...content, education: content.education.map((item) => item.id === id ? { ...item, ...patch } : item) }))
  const updateWork = (id: string, patch: Partial<ResumeWorkEntry>) => changeContent((content) => ({ ...content, work: content.work.map((item) => item.id === id ? { ...item, ...patch } : item) }))
  const updateProject = (id: string, patch: Partial<ResumeProjectEntry>) => changeContent((content) => ({ ...content, projects: content.projects.map((item) => item.id === id ? { ...item, ...patch } : item) }))

  return <div className="space-y-3">
    <div className="sticky top-0 z-20 flex flex-wrap items-center gap-2 border-4 border-border bg-background p-3 shadow-md">
      <Button size="sm" variant="ghost" onClick={onBack}><ArrowLeft />返回</Button>
      <Input className="h-9 min-w-52 flex-1 font-head" value={document.title} aria-label="简历标题" onChange={(event) => change((current) => ({ ...current, title: event.target.value }))} />
      <span className="text-xs text-muted-foreground">{dirty ? '有未保存修改' : message || '内容已保存'}</span>
      <Button size="sm" onClick={() => void save()} disabled={saving || !document.title.trim()}>{saving ? <Loader2 className="animate-spin" /> : <Save />}保存</Button>
      <Button size="sm" variant="outline" onClick={() => void download('html')} disabled={exporting !== null}><Download />HTML</Button>
      <Button size="sm" variant="outline" onClick={() => void download('pdf')} disabled={exporting !== null}>{exporting === 'pdf' ? <Loader2 className="animate-spin" /> : <Download />}PDF</Button>
    </div>
    {error && <Alert variant="destructive"><AlertTitle>操作未完成</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
    <div className="grid min-h-[calc(100vh-8rem)] gap-3 xl:grid-cols-[minmax(520px,48%)_minmax(0,52%)]">
      <Card className="min-w-0">
        <CardHeader><CardTitle className="font-head text-2xl">内容编辑</CardTitle><CardDescription>按模块填写，右侧会实时预览最终版式。</CardDescription></CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap gap-2">{editorSections.map(([key, label]) => <Button size="sm" key={key} variant={activeSection === key ? 'default' : 'outline'} onClick={() => setActiveSection(key)}>{label}</Button>)}</div>
          {activeSection === 'personal' && <div className="grid gap-4 sm:grid-cols-2">
            <Field label="姓名"><Input value={document.content.personal.name} onChange={(event) => updatePersonal('name', event.target.value)} /></Field>
            <Field label="求职方向 / 职位"><Input value={document.content.personal.headline} onChange={(event) => updatePersonal('headline', event.target.value)} /></Field>
            <Field label="电话"><Input value={document.content.personal.phone} onChange={(event) => updatePersonal('phone', event.target.value)} /></Field>
            <Field label="邮箱"><Input type="email" value={document.content.personal.email} onChange={(event) => updatePersonal('email', event.target.value)} /></Field>
            <Field label="所在地"><Input value={document.content.personal.location} onChange={(event) => updatePersonal('location', event.target.value)} /></Field>
            <Field label="个人主页"><Input value={document.content.personal.website} onChange={(event) => updatePersonal('website', event.target.value)} /></Field>
            <div className="sm:col-span-2"><Field label="个人简介"><TextArea value={document.content.personal.summary} onChange={(event) => updatePersonal('summary', event.target.value)} /></Field></div>
            <div className="sm:col-span-2"><Label className="mb-2 block">个人照片</Label><div className="flex flex-wrap items-center gap-3">{photoUrl && <img src={photoUrl} className="h-28 w-24 border-2 border-border object-cover" alt="已上传个人照片" />}<Label className="inline-flex h-10 cursor-pointer items-center gap-2 border-2 border-border bg-background px-4 shadow-sm"><ImagePlus className="size-4" />{photoUrl ? '更换照片' : '上传照片'}<Input className="hidden" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => void uploadPhoto(event.target.files?.[0])} /></Label>{photoUrl && <Button variant="ghost" onClick={() => void deletePhoto()}><Trash2 />删除照片</Button>}<span className="text-xs text-muted-foreground">JPG / PNG / WebP，最大 5 MiB</span></div></div>
          </div>}
          {activeSection === 'education' && <DynamicSection title="教育经历" onAdd={() => changeContent((content) => ({ ...content, education: [...content.education, { id: newId(), school: '', degree: '', major: '', start_date: '', end_date: '', description: '' }] }))}>{document.content.education.map((item) => <EntryCard key={item.id} title={item.school || '新教育经历'} onDelete={() => changeContent((content) => ({ ...content, education: content.education.filter((entry) => entry.id !== item.id) }))}><div className="grid gap-3 sm:grid-cols-2"><Field label="学校"><Input value={item.school} onChange={(event) => updateEducation(item.id, { school: event.target.value })} /></Field><Field label="学历"><Input value={item.degree} onChange={(event) => updateEducation(item.id, { degree: event.target.value })} /></Field><Field label="专业"><Input value={item.major} onChange={(event) => updateEducation(item.id, { major: event.target.value })} /></Field><div className="grid grid-cols-2 gap-2"><Field label="开始时间"><Input value={item.start_date} onChange={(event) => updateEducation(item.id, { start_date: event.target.value })} /></Field><Field label="结束时间"><Input value={item.end_date} onChange={(event) => updateEducation(item.id, { end_date: event.target.value })} /></Field></div><div className="sm:col-span-2"><Field label="补充说明"><TextArea value={item.description} onChange={(event) => updateEducation(item.id, { description: event.target.value })} /></Field></div></div></EntryCard>)}</DynamicSection>}
          {activeSection === 'work' && <DynamicSection title="工作经历" onAdd={() => changeContent((content) => ({ ...content, work: [...content.work, { id: newId(), company: '', role: '', start_date: '', end_date: '', highlights: [] }] }))}>{document.content.work.map((item) => <EntryCard key={item.id} title={item.role || item.company || '新工作经历'} onDelete={() => changeContent((content) => ({ ...content, work: content.work.filter((entry) => entry.id !== item.id) }))}><div className="grid gap-3 sm:grid-cols-2"><Field label="公司"><Input value={item.company} onChange={(event) => updateWork(item.id, { company: event.target.value })} /></Field><Field label="职位"><Input value={item.role} onChange={(event) => updateWork(item.id, { role: event.target.value })} /></Field><Field label="开始时间"><Input value={item.start_date} onChange={(event) => updateWork(item.id, { start_date: event.target.value })} /></Field><Field label="结束时间"><Input value={item.end_date} onChange={(event) => updateWork(item.id, { end_date: event.target.value })} /></Field><div className="sm:col-span-2"><Field label="工作亮点（每行一条）"><TextArea value={item.highlights.join('\n')} onChange={(event) => updateWork(item.id, { highlights: event.target.value.split('\n') })} /></Field></div></div></EntryCard>)}</DynamicSection>}
          {activeSection === 'projects' && <DynamicSection title="项目经历" onAdd={() => changeContent((content) => ({ ...content, projects: [...content.projects, { id: newId(), source_project_id: null, name: '', company: '', role: '', start_date: '', end_date: '', summary: '', highlights: [], technologies: [] }] }))} extra={<Button variant="outline" onClick={() => setMaterialOpen(true)}><LibraryBig />从全部数据项目填充</Button>}>{document.content.projects.map((item) => <EntryCard key={item.id} title={item.name || '新项目经历'} badge={item.source_project_id ? '数据项目素材' : undefined} onDelete={() => changeContent((content) => ({ ...content, projects: content.projects.filter((entry) => entry.id !== item.id) }))}><div className="grid gap-3 sm:grid-cols-2"><Field label="项目名称"><Input value={item.name} onChange={(event) => updateProject(item.id, { name: event.target.value })} /></Field><Field label="公司 / 客户"><Input value={item.company} onChange={(event) => updateProject(item.id, { company: event.target.value })} /></Field><Field label="担任角色"><Input value={item.role} onChange={(event) => updateProject(item.id, { role: event.target.value })} /></Field><div className="grid grid-cols-2 gap-2"><Field label="开始时间"><Input value={item.start_date} onChange={(event) => updateProject(item.id, { start_date: event.target.value })} /></Field><Field label="结束时间"><Input value={item.end_date} onChange={(event) => updateProject(item.id, { end_date: event.target.value })} /></Field></div><div className="sm:col-span-2"><Field label="项目背景 / 简介"><TextArea value={item.summary} onChange={(event) => updateProject(item.id, { summary: event.target.value })} /></Field></div><div className="sm:col-span-2"><Field label="职责与成果（每行一条）"><TextArea value={item.highlights.join('\n')} onChange={(event) => updateProject(item.id, { highlights: event.target.value.split('\n') })} /></Field></div><div className="sm:col-span-2"><Field label="技术栈（横向标签）"><TechnologyEditor values={item.technologies} onChange={(technologies) => updateProject(item.id, { technologies })} /></Field></div></div></EntryCard>)}</DynamicSection>}
          {activeSection === 'skills' && <div className="space-y-4"><Field label="专业技能（每行一项）"><TextArea value={document.content.skills.join('\n')} onChange={(event) => changeContent((content) => ({ ...content, skills: event.target.value.split('\n') }))} /></Field><Field label="证书荣誉（每行一项）"><TextArea value={document.content.certificates.join('\n')} onChange={(event) => changeContent((content) => ({ ...content, certificates: event.target.value.split('\n') }))} /></Field><Field label="自我评价"><TextArea value={document.content.self_evaluation} onChange={(event) => changeContent((content) => ({ ...content, self_evaluation: event.target.value }))} /></Field></div>}
          {activeSection === 'source' && <div><Alert><AlertTitle>原始 OCR 内容仅供对照</AlertTitle><AlertDescription>这里保留上传简历的完整识别文本，避免结构化抽取遗漏。它不会直接出现在导出文件中。</AlertDescription></Alert><TextArea className="mt-4 min-h-[460px] font-mono text-xs" readOnly value={document.content.source_markdown || '此草稿没有上传简历来源。'} /></div>}
        </CardContent>
      </Card>
      <div className="min-w-0 space-y-3">
        <Card><CardContent className="flex flex-wrap items-center gap-3 p-4"><strong className="font-head">模板</strong><Button variant="outline" onClick={() => setTemplateOpen(true)}><LayoutGrid />{selectedTemplate?.name ?? document.template_key}<Badge variant="secondary">{templates.length || '…'} 款</Badge></Button>{selectedTemplate && <span className="text-xs text-muted-foreground">{templateGroupNames[selectedTemplate.group]} · {selectedTemplate.description}</span>}<Label className="ml-auto flex items-center gap-2">主题色<Input className="h-10 w-14 cursor-pointer p-1" type="color" value={document.theme_color} onChange={(event) => change((current) => ({ ...current, theme_color: event.target.value }))} /></Label></CardContent></Card>
        <div className="sticky top-20 rounded bg-slate-200 p-4"><ResumePreview document={document} photoUrl={photoUrl} template={selectedTemplate} /></div>
      </div>
    </div>
    <TemplateLibrary open={templateOpen} onOpenChange={setTemplateOpen} templates={templates} selectedKey={document.template_key} onSelect={(template) => change((current) => ({ ...current, template_key: template.key, theme_color: template.default_color }))} />
    <Dialog open={materialOpen} onOpenChange={setMaterialOpen}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>从全部数据简历项目填充</DialogTitle>
          <DialogDescription>这里展示本组织全部候选人的项目，不限于当前简历来源。单条可立即填充，也可多选后批量填充；填充内容可继续修改。</DialogDescription>
        </DialogHeader>
        <Input value={materialQuery} onChange={(event) => setMaterialQuery(event.target.value)} placeholder="搜索项目、公司、角色、候选人或技术栈" />
        {filteredProjects.length === 0 ? <div className="border-2 border-dashed p-8 text-center text-sm text-muted-foreground">没有匹配的数据简历项目</div> : (
          <div className="grid max-h-[58vh] gap-3 overflow-y-auto pr-2 md:grid-cols-2">
            {filteredProjects.map((project) => {
              const imported = document.content.projects.some((item) => item.source_project_id === project.id)
              return (
                <article className={`border-2 p-4 ${selectedMaterials.has(project.id) ? 'bg-primary shadow-sm' : 'bg-background'}`} key={project.id}>
                  <div className="flex items-start gap-3">
                    <input className="mt-1 size-4" type="checkbox" aria-label={`选择 ${project.project_name}`} disabled={imported} checked={selectedMaterials.has(project.id)} onChange={(event) => setSelectedMaterials((current) => { const next = new Set(current); if (event.target.checked) next.add(project.id); else next.delete(project.id); return next })} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2"><strong className="line-clamp-2">{project.project_name}</strong><Badge variant={imported ? 'secondary' : 'outline'}>{imported ? '已填充' : maskedCandidateName(project.candidate_name)}</Badge></div>
                      <span className="mt-1 block truncate text-xs text-muted-foreground">{project.company_name || '公司未注明'} · {project.role_name || '角色未注明'}</span>
                      <span className="block truncate text-[10px] text-muted-foreground">来源：{originalName(project.source_path)}</span>
                      <div className="mt-2 flex flex-wrap gap-1">{project.technologies.map((technology, index) => <Badge variant="outline" key={`${technology}-${index}`}>{technology}</Badge>)}</div>
                    </div>
                  </div>
                  <Button className="mt-3 w-full" size="sm" variant="outline" disabled={imported} onClick={() => importOneMaterial(project)}><Plus />{imported ? '已在当前简历中' : '直接填充此项目'}</Button>
                </article>
              )
            })}
          </div>
        )}
        <DialogFooter><Button variant="outline" onClick={() => setMaterialOpen(false)}>完成</Button><Button disabled={selectedMaterials.size === 0} onClick={importMaterials}><Plus />批量填充 {selectedMaterials.size} 条</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
}

function DynamicSection({ title, onAdd, extra, children }: { title: string; onAdd: () => void; extra?: React.ReactNode; children: React.ReactNode }) {
  return <div className="space-y-4"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-head text-xl">{title}</h3><div className="flex gap-2">{extra}<Button size="sm" onClick={onAdd}><Plus />新增</Button></div></div>{children}</div>
}

function EntryCard({ title, badge, onDelete, children }: { title: string; badge?: string; onDelete: () => void; children: React.ReactNode }) {
  return <div className="space-y-4 border-2 border-border bg-muted/20 p-4"><div className="flex items-center justify-between gap-3"><div className="flex items-center gap-2"><strong>{title}</strong>{badge && <Badge variant="outline">{badge}</Badge>}</div><Button size="icon-sm" variant="ghost" aria-label={`删除${title}`} onClick={onDelete}><Trash2 /></Button></div>{children}</div>
}

export function ResumeWriterPanel(props: Props) {
  if (!props.documentId) return <ResumeSourceChooser session={props.session} onOpenDocument={props.onOpenDocument} />
  return <ResumeEditor {...props} documentId={props.documentId} />
}
