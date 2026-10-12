import type {
  ResumeDocument,
  ResumeProjectEntry,
  ResumeTemplateDefinition,
  ResumeWorkEntry,
} from '@/lib/api'

type Props = {
  document: ResumeDocument
  photoUrl: string | null
  template?: ResumeTemplateDefinition
}

const fallbackTemplate: ResumeTemplateDefinition = {
  key: 'local-template-05',
  name: '本地模板 05 · 技术履历优化',
  description: '',
  group: 'local',
  layout: 'local_05',
  header_style: 'resume_mark',
  section_style: 'tracked_ribbon',
  density: 'compact',
  default_color: '#465A73',
  variant: 5,
}

function Period({ start, end }: { start: string; end: string }) {
  const value = [start, end].filter(Boolean).join(' — ')
  return value ? <span className="shrink-0 text-[7px] text-slate-500">{value}</span> : null
}

function TechnologyTags({ values }: { values: string[] }) {
  const technologies = values.map((value) => value.trim()).filter(Boolean)
  if (technologies.length === 0) return null
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[6px]">
      <strong className="mr-0.5 text-[var(--resume-accent)]">技术栈</strong>
      {technologies.map((technology, index) => (
        <span className="border border-current/25 bg-white px-1.5 py-0.5 text-slate-600" key={`${technology}-${index}`}>
          {technology}
        </span>
      ))}
    </div>
  )
}

function Section({
  title,
  templateKey,
  children,
}: {
  title: string
  templateKey: string
  children: React.ReactNode
}) {
  const titleClass = templateKey === 'local-template-01'
    ? 'inline-block min-w-28 bg-[var(--resume-accent)] px-3 py-1 text-white after:absolute after:-right-4 after:top-0 after:border-y-[10px] after:border-l-[16px] after:border-y-transparent after:border-l-[var(--resume-accent)]'
    : templateKey === 'local-template-02'
      ? 'bg-[var(--resume-tint)] px-3 py-1 text-[var(--resume-accent)] before:absolute before:inset-y-0 before:left-0 before:w-24 before:bg-[var(--resume-accent)] before:content-[""]'
      : templateKey === 'local-template-05'
        ? 'inline-block min-w-36 bg-[var(--resume-accent)] px-4 py-1 text-white after:absolute after:-right-5 after:top-0 after:border-y-[10px] after:border-l-[20px] after:border-y-transparent after:border-l-[var(--resume-accent)]'
        : 'border-b-2 pb-1 text-[var(--resume-accent)]'
  return (
    <section className={`relative break-inside-avoid ${templateKey === 'local-template-05' ? 'mb-3 pl-4' : 'mb-3'}`}>
      {templateKey === 'local-template-05' && <span className="absolute -bottom-3 left-1 top-5 w-px bg-slate-300" aria-hidden="true" />}
      <h2 className={`relative mb-2 text-[10px] font-bold tracking-wide ${titleClass}`} style={{ borderColor: 'var(--resume-accent)' }}>
        <span className={templateKey === 'local-template-02' ? 'relative z-10 text-white' : ''}>{title}</span>
      </h2>
      <div className={templateKey === 'local-template-05' ? 'pl-2' : ''}>{children}</div>
    </section>
  )
}

function WorkList({ values, tracked }: { values: ResumeWorkEntry[]; tracked: boolean }) {
  return <div className="space-y-2">{values.map((item) => (
    <article className="break-inside-avoid" key={item.id}>
      <div className="flex items-start justify-between gap-3">
        <div><h3 className="text-[8px] font-bold">{item.role}</h3><p className="text-[7px] text-slate-500">{item.company}</p></div>
        <Period start={item.start_date} end={item.end_date} />
      </div>
      {item.highlights.length > 0 && <ul className={`${tracked ? 'list-[disclosure-closed]' : 'list-disc'} mt-1 pl-4 text-[7px] leading-[1.65]`}>{item.highlights.filter(Boolean).map((value, index) => <li key={index}>{value}</li>)}</ul>}
    </article>
  ))}</div>
}

function ProjectList({ values, tracked }: { values: ResumeProjectEntry[]; tracked: boolean }) {
  return <div className="space-y-2.5">{values.map((item) => (
    <article className="break-inside-avoid" key={item.id}>
      <div className="flex items-start justify-between gap-3">
        <div><h3 className="text-[8px] font-bold">{item.name}</h3><p className="text-[7px] text-slate-500">{[item.company, item.role].filter(Boolean).join(' · ')}</p></div>
        <Period start={item.start_date} end={item.end_date} />
      </div>
      {item.summary && <p className="mt-1 whitespace-pre-wrap text-[7px] leading-[1.65]">{item.summary}</p>}
      {item.highlights.length > 0 && <ul className={`${tracked ? 'list-[disclosure-closed]' : 'list-disc'} mt-1 pl-4 text-[7px] leading-[1.65]`}>{item.highlights.filter(Boolean).map((value, index) => <li key={index}>{value}</li>)}</ul>}
      <TechnologyTags values={item.technologies} />
    </article>
  ))}</div>
}

export function ResumePreview({ document, photoUrl, template }: Props) {
  const selected = template ?? fallbackTemplate
  const key = selected.key
  const { content } = document
  const personal = content.personal
  const contacts = [personal.phone, personal.email, personal.location, personal.website].filter(Boolean)
  const tracked = key === 'local-template-05'
  const trackedSummary = [personal.summary, content.self_evaluation].filter(Boolean).join('\n')
  const style = {
    '--resume-accent': document.theme_color,
    '--resume-tint': `${document.theme_color}22`,
  } as React.CSSProperties

  const portrait = photoUrl
    ? <img src={photoUrl} alt="个人照片预览" className="aspect-[4/5] w-20 shrink-0 object-cover" />
    : <div className="grid aspect-[4/5] w-20 shrink-0 place-items-center border border-dashed border-slate-300 text-[6px] text-slate-400">照片</div>

  const header = key === 'local-template-01' ? (
    <header className="mb-4">
      <div className="flex items-center justify-between gap-4"><div><div className="flex items-end gap-3"><h1 className="text-2xl font-semibold tracking-widest">{personal.name || '个人简历'}</h1><span className="border-l-2 pl-3 text-[9px] text-[var(--resume-accent)]">{personal.headline || 'Personal resume'}</span></div><div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[7px] text-slate-600">{contacts.map((item) => <span key={item}>{item}</span>)}</div></div>{portrait}</div>
      <div className="mt-3 flex h-2"><span className="w-3/5 bg-[var(--resume-accent)]" /><span className="flex-1 bg-[#C8A66A]" /></div>
    </header>
  ) : key === 'local-template-02' ? (
    <header className="relative mb-4 min-h-24 text-center"><div className="px-24"><h1 className="text-2xl font-semibold text-[var(--resume-accent)]">{personal.name || '个人简历'}</h1><p className="mt-1 text-[8px] text-slate-500">{personal.headline || '每天进步一点点'}</p><div className="mt-3 flex flex-wrap justify-center gap-x-4 gap-y-1 text-[7px]">{contacts.map((item) => <span key={item}>{item}</span>)}</div></div><div className="absolute right-2 top-0">{portrait}</div></header>
  ) : key === 'local-template-03' ? (
    <header className="mb-4"><div className="mb-4 bg-[var(--resume-accent)] px-4 py-1 text-sm tracking-widest text-white">PERSONAL RESUME</div><div className="flex items-start justify-between gap-5"><div className="flex-1"><div className="flex items-end gap-5 border-b pb-2"><h1 className="text-xl font-bold text-[var(--resume-accent)]">{personal.name || '姓名'}</h1><strong className="text-[8px] text-[var(--resume-accent)]">{personal.headline || '求职方向'}</strong></div><div className="mt-3 grid grid-cols-2 gap-x-8 gap-y-2 text-[7px]">{contacts.map((item) => <span className="break-all" key={item}>◆ {item}</span>)}</div></div>{portrait}</div></header>
  ) : key === 'local-template-04' ? (
    <header className="relative mb-4 min-h-24 text-center"><div className="px-24"><h1 className="text-2xl font-bold">{personal.name || '个人简历'}</h1><p className="mt-2 text-[8px]">{personal.headline || '求职方向'}</p><div className="mt-2 flex flex-wrap justify-center gap-x-2 text-[7px] text-slate-600">{contacts.map((item, index) => <span key={item}>{index > 0 && ' | '}{item}</span>)}</div></div><div className="absolute right-2 top-0">{portrait}</div></header>
  ) : (
    <header className="mb-4 flex min-h-32 items-start justify-between gap-6">
      <div className="min-w-0 flex-1"><div className="mb-2 inline-block bg-[var(--resume-accent)] px-3 py-2 text-sm font-black tracking-widest text-white">RESUME</div><div className="flex items-end gap-5 border-b pb-2"><h1 className="text-2xl font-bold tracking-[0.2em]">{personal.name || '姓名'}</h1><strong className="pb-1 text-[8px] text-[var(--resume-accent)]">{personal.headline || '求职方向'}</strong></div><div className="mt-3 grid grid-cols-2 gap-x-8 gap-y-2 text-[7px] text-slate-600">{contacts.map((item) => <span className="break-all" key={item}>● {item}</span>)}</div></div>{portrait}
    </header>
  )

  const commonSections = (
    <>
      {(tracked ? trackedSummary : personal.summary) && <Section title={tracked ? '自我评价' : '个人简介'} templateKey={key}><p className="whitespace-pre-wrap text-[7px] leading-[1.7]">{tracked ? trackedSummary : personal.summary}</p></Section>}
      {content.work.length > 0 && <Section title="工作经历" templateKey={key}><WorkList values={content.work} tracked={tracked} /></Section>}
      {content.projects.length > 0 && <Section title={tracked ? '代表项目' : '项目经历'} templateKey={key}><ProjectList values={content.projects} tracked={tracked} /></Section>}
      {content.education.length > 0 && <Section title="教育背景" templateKey={key}><div className="space-y-2">{content.education.map((item) => <article className="break-inside-avoid" key={item.id}><div className="flex justify-between gap-3"><div><h3 className="text-[8px] font-bold">{item.school}</h3><p className="text-[7px] text-slate-500">{[item.degree, item.major].filter(Boolean).join(' · ')}</p></div><Period start={item.start_date} end={item.end_date} /></div>{item.description && <p className="mt-1 whitespace-pre-wrap text-[7px] leading-[1.65]">{item.description}</p>}</article>)}</div></Section>}
      {content.skills.length > 0 && <Section title={tracked ? '技能优势' : '专业技能'} templateKey={key}><div className="flex flex-wrap gap-1">{content.skills.filter(Boolean).map((value, index) => <span className="border border-current/25 px-1.5 py-0.5 text-[6.5px]" key={index}>{value}</span>)}</div></Section>}
      {content.certificates.length > 0 && <Section title="证书荣誉" templateKey={key}><ul className="list-disc pl-4 text-[7px] leading-[1.7]">{content.certificates.filter(Boolean).map((value, index) => <li key={index}>{value}</li>)}</ul></Section>}
      {!tracked && content.self_evaluation && <Section title="自我评价" templateKey={key}><p className="whitespace-pre-wrap text-[7px] leading-[1.7]">{content.self_evaluation}</p></Section>}
    </>
  )

  return (
    <div data-template={key} className={`mx-auto aspect-[210/297] w-full max-w-[700px] bg-white p-7 text-slate-900 shadow-xl ${tracked ? 'text-[95%]' : ''}`} style={style}>
      {header}
      <main>{commonSections}</main>
    </div>
  )
}
