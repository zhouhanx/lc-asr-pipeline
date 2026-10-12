import { useCallback, useEffect, useMemo, useState } from 'react'
import { BriefcaseBusiness, Building2, CalendarRange, Check, Clipboard, Eye, Search, UserRound, type LucideIcon } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { originalDocumentName } from '@/features/ocr/documentName'
import { maskedCandidateName } from '@/features/projects/candidateName'
import {
  apiRequest,
  type AuthPayload,
  type ResumeProject,
  type ResumeProjectSummary,
} from '@/lib/api'

type Props = {
  session: AuthPayload
  onOpenOCRTask: (jobId: string) => void
}

function projectPeriod(project: ResumeProject) {
  const start = project.start_date || '未标注'
  const end = project.is_current ? '至今' : (project.end_date || '未标注')
  return `${start} — ${end}`
}

function projectCopyText(project: ResumeProject) {
  const lines = [
    project.project_name,
    `候选人：${maskedCandidateName(project.candidate_name)}`,
    project.company_name ? `公司名称：${project.company_name}` : '',
    project.role_name ? `项目角色：${project.role_name}` : '',
    `项目时间：${projectPeriod(project)}`,
  ]
  const addText = (title: string, value: string | null) => {
    if (value?.trim()) lines.push('', `${title}：`, value.trim())
  }
  const addList = (title: string, values: string[]) => {
    if (values.length > 0) lines.push('', `${title}：`, ...values.map((value) => `- ${value}`))
  }
  if (project.technologies.length > 0) {
    lines.push('', `技术栈：${project.technologies.join(' / ')}`)
  }
  addList('主要职责', project.responsibilities)
  addText('项目背景', project.project_background)
  addList('项目职责', project.project_responsibilities)
  addList('项目成果', project.project_outcomes)
  addText('项目描述', project.description)
  return lines.filter((line, index) => line !== '' || lines[index - 1] !== '').join('\n')
}

function DetailSection({ title, text, items, horizontal = false }: { title: string; text?: string | null; items?: string[]; horizontal?: boolean }) {
  if (!text?.trim() && (!items || items.length === 0)) return null
  return (
    <section className="grid gap-2 border-t-2 border-border pt-5">
      <h3 className="font-head text-lg">{title}</h3>
      {text?.trim() && <p className="whitespace-pre-wrap leading-7">{text.trim()}</p>}
      {items && items.length > 0 && (horizontal
        ? <div className="flex flex-wrap gap-2">{items.map((item, index) => <Badge variant="outline" key={`${title}-${index}`}>{item}</Badge>)}</div>
        : <ul className="grid list-disc gap-2 pl-5 leading-7">{items.map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}</ul>)}
    </section>
  )
}

function ScoreRow({ label, score, reason, risk = false }: { label: string; score: number | null; reason: string | null; risk?: boolean }) {
  return (
    <div className="grid gap-1 border-t-2 border-border pt-3 first:border-0 first:pt-0">
      <div className="flex items-center justify-between gap-3"><strong>{label}</strong><Badge variant="outline">{score === null ? '未评分' : `${score} / 10`}</Badge></div>
      <p className="text-xs text-muted-foreground">{risk ? '分数越高，美化风险越高。' : '分数越高，评价越好。'}</p>
      {reason && <p className="text-sm leading-6">{reason}</p>}
    </div>
  )
}

export function ResumeProjectPanel({ session, onOpenOCRTask }: Props) {
  const [projects, setProjects] = useState<ResumeProject[]>([])
  const [summary, setSummary] = useState<ResumeProjectSummary | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [selectedProject, setSelectedProject] = useState<ResumeProject | null>(null)
  const [copied, setCopied] = useState(false)

  const load = useCallback(() => {
    Promise.all([
      apiRequest<ResumeProject[]>('/resume-projects', { token: session.access_token }),
      apiRequest<ResumeProjectSummary>('/resume-projects/summary', { token: session.access_token }),
    ])
      .then(([items, totals]) => {
        setProjects(items)
        setSummary(totals)
      })
      .catch((reason: Error) => setError(reason.message))
  }, [session.access_token])

  useEffect(load, [load])

  const filtered = useMemo(() => {
    const keyword = query.trim().toLocaleLowerCase()
    if (!keyword) return projects
    return projects.filter((project) => [
      project.candidate_name,
      project.project_name,
      project.company_name,
      project.role_name,
      ...project.technologies,
    ].some((value) => value?.toLocaleLowerCase().includes(keyword)))
  }, [projects, query])
  const metrics: Array<{ label: string; value: number; icon: LucideIcon }> = [
    { label: '项目记录', value: summary?.project_count ?? 0, icon: BriefcaseBusiness },
    { label: '简历档案', value: summary?.candidate_count ?? 0, icon: UserRound },
    { label: '关联公司', value: summary?.company_count ?? 0, icon: Building2 },
  ]

  return (
    <div className="mx-auto w-full max-w-[1920px] space-y-7">
      <div>
        <p className="font-mono text-xs tracking-[0.25em] text-muted-foreground">WORKSPACE / PROJECTS / RESUME</p>
        <h1 className="mt-2 font-head text-4xl">数据简历项目</h1>
        <p className="mt-2 text-base text-muted-foreground">从简历 OCR 结果中抽取项目经历；每条记录都可追溯到候选人、OCR 任务和原始文件。</p>
      </div>
      {error && <Alert variant="destructive"><AlertTitle>项目数据加载失败</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
      <div className="grid gap-4 sm:grid-cols-3">
        {metrics.map(({ label, value, icon: Icon }) => <Card key={label} className="border-4 shadow-[5px_5px_0_0_var(--border)]"><CardContent className="flex items-center justify-between p-5"><div><p className="font-mono text-xs text-muted-foreground">{label}</p><strong className="font-head text-3xl">{value}</strong></div><Icon className="size-8" /></CardContent></Card>)}
      </div>
      <div className="relative max-w-xl">
        <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2" />
        <Input className="h-12 pl-12" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索姓名、项目、公司、角色或技术栈" />
      </div>
      {filtered.length === 0 ? (
        <div className="grid min-h-64 place-items-center border-4 border-dashed border-border bg-muted/40 p-8 text-center">
          <div><BriefcaseBusiness className="mx-auto size-10" /><p className="mt-3 font-head text-xl">暂无数据简历项目</p><p className="mt-2 text-sm text-muted-foreground">完成一条“文件属性为简历”的 OCR 任务后，项目会自动出现在这里。</p></div>
        </div>
      ) : (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {filtered.map((project) => (
            <Card key={project.id} className="flex h-full flex-col border-4 shadow-[6px_6px_0_0_var(--border)] [--card-spacing:--spacing(5)]">
              <CardHeader className="gap-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0"><CardTitle className="line-clamp-2 font-head text-xl">{project.project_name}</CardTitle><CardDescription className="mt-2 flex items-center gap-2"><UserRound className="size-4 shrink-0" />{maskedCandidateName(project.candidate_name)}</CardDescription></div>
                  <Badge variant="outline">#{project.project_index + 1}</Badge>
                </div>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col gap-4">
                <div className="grid gap-2 border-2 border-border bg-muted/30 p-4 text-sm">
                  <span className="flex items-start gap-2"><Building2 className="mt-0.5 size-4 shrink-0" /><strong>{project.company_name || '公司未标注'}</strong></span>
                  <span className="flex items-start gap-2"><BriefcaseBusiness className="mt-0.5 size-4 shrink-0" />{project.role_name || '角色未标注'}</span>
                  <span className="flex items-start gap-2"><CalendarRange className="mt-0.5 size-4 shrink-0" />{projectPeriod(project)}</span>
                </div>
                {project.description && <p className="line-clamp-4 text-sm leading-6 text-muted-foreground">{project.description}</p>}
                {project.technologies.length > 0 && <div className="flex flex-wrap gap-2">{project.technologies.slice(0, 8).map((item) => <Badge key={item} variant="outline">{item}</Badge>)}</div>}
                <div className="mt-auto border-t-2 border-border pt-4">
                  <p className="truncate font-mono text-[11px] text-muted-foreground" title={originalDocumentName(project.source_path)}>来源：{originalDocumentName(project.source_path)}</p>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <Popover>
                      <PopoverTrigger asChild><Button variant="secondary">评分 {project.overall_score ?? '—'}</Button></PopoverTrigger>
                      <PopoverContent align="start" className="grid w-96 gap-3">
                        <div><p className="font-head text-lg">项目评分说明</p><p className="mt-1 text-xs text-muted-foreground">评分只依据简历原文，适合作为人工复核线索。</p></div>
                        <ScoreRow label="项目架构合理性" score={project.architecture_score} reason={project.architecture_reason} />
                        <ScoreRow label="描述可信度" score={project.credibility_score} reason={project.credibility_reason} />
                        <ScoreRow label="项目美化风险" score={project.embellishment_risk_score} reason={project.embellishment_risk_reason} risk />
                      </PopoverContent>
                    </Popover>
                    <Button onClick={() => { setCopied(false); setSelectedProject(project) }}><Eye />查看详情</Button>
                  </div>
                  <Button className="mt-2 w-full" variant="outline" onClick={() => onOpenOCRTask(project.ocr_job_id)}><Eye />查看源 OCR</Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <Dialog open={selectedProject !== null} onOpenChange={(open) => { if (!open) setSelectedProject(null) }}>
        {selectedProject && (
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{selectedProject.project_name}</DialogTitle>
              <DialogDescription>独立项目详情 · 仅展示简历原文中已抽取的内容</DialogDescription>
            </DialogHeader>
            <div className="select-text border-2 border-border bg-background p-5 sm:p-7">
              <div className="grid gap-3 sm:grid-cols-2">
                <p><span className="text-sm text-muted-foreground">候选人</span><br /><strong>{maskedCandidateName(selectedProject.candidate_name)}</strong></p>
                <p><span className="text-sm text-muted-foreground">项目时间</span><br /><strong>{projectPeriod(selectedProject)}</strong></p>
                {selectedProject.company_name && <p><span className="text-sm text-muted-foreground">公司名称</span><br /><strong>{selectedProject.company_name}</strong></p>}
                {selectedProject.role_name && <p><span className="text-sm text-muted-foreground">项目角色</span><br /><strong>{selectedProject.role_name}</strong></p>}
              </div>
              <div className="mt-6 grid gap-5">
                <DetailSection title="技术栈" items={selectedProject.technologies} horizontal />
                <DetailSection title="主要职责" items={selectedProject.responsibilities} />
                <DetailSection title="项目背景" text={selectedProject.project_background} />
                <DetailSection title="项目职责" items={selectedProject.project_responsibilities} />
                <DetailSection title="项目成果" items={selectedProject.project_outcomes} />
                <DetailSection title="项目描述" text={selectedProject.description} />
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={async () => {
                  await navigator.clipboard.writeText(projectCopyText(selectedProject))
                  setCopied(true)
                }}
              >
                {copied ? <Check /> : <Clipboard />}{copied ? '已复制' : '复制项目内容'}
              </Button>
              <Button onClick={() => onOpenOCRTask(selectedProject.ocr_job_id)}><Eye />查看源 OCR</Button>
            </DialogFooter>
          </DialogContent>
        )}
      </Dialog>
    </div>
  )
}
