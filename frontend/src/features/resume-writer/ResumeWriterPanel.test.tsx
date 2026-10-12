import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  apiRequest,
  type AuthPayload,
  type ResumeDocument,
  type ResumeProject,
  type ResumeTemplateDefinition,
} from '@/lib/api'

import { ResumeWriterPanel } from './ResumeWriterPanel'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    apiRequest: vi.fn(),
    apiDownload: vi.fn(),
  }
})

const session = {
  access_token: 'test-access-token',
  tenant: { id: 'tenant-1' },
  user: { id: 'user-1' },
  permissions: ['jobs:read', 'jobs:write'],
} as AuthPayload

const document: ResumeDocument = {
  id: 'document-1',
  source_resume_profile_id: 'profile-1',
  source_path: 'resumes/source.pdf',
  title: '平台工程师简历',
  template_key: 'local-template-05',
  theme_color: '#465A73',
  has_photo: false,
  created_at: '2026-07-24T00:00:00Z',
  updated_at: '2026-07-24T00:00:00Z',
  content: {
    personal: {
      name: '张三', headline: '平台工程师', phone: '', email: '',
      location: '', website: '', summary: '',
    },
    education: [],
    work: [],
    projects: [],
    skills: [],
    certificates: [],
    self_evaluation: '',
    source_markdown: '',
  },
}

const projects: ResumeProject[] = [
  {
    id: 'project-a',
    resume_profile_id: 'profile-1',
    ocr_job_id: 'ocr-a',
    uploaded_file_id: 'file-a',
    candidate_name: '张三',
    phone: null,
    email: null,
    project_index: 0,
    project_name: '当前候选人项目',
    company_name: 'LC',
    role_name: '工程师',
    start_date: '2025',
    end_date: null,
    is_current: true,
    description: '当前项目',
    responsibilities: [],
    technologies: ['Python'],
    project_background: null,
    project_responsibilities: [],
    project_outcomes: [],
    architecture_score: null,
    architecture_reason: null,
    credibility_score: null,
    credibility_reason: null,
    embellishment_risk_score: null,
    embellishment_risk_reason: null,
    overall_score: null,
    source_excerpt: null,
    source_path: 'resumes/a.pdf',
    extraction_model_name: 'test',
    ocr_completed_at: null,
    extracted_at: '2026-07-24T00:00:00Z',
  },
  {
    id: 'project-b',
    resume_profile_id: 'profile-2',
    ocr_job_id: 'ocr-b',
    uploaded_file_id: 'file-b',
    candidate_name: '李四',
    phone: null,
    email: null,
    project_index: 0,
    project_name: '跨候选人项目',
    company_name: 'Example',
    role_name: '负责人',
    start_date: '2024',
    end_date: '2025',
    is_current: false,
    description: '跨候选人素材',
    responsibilities: ['平台建设'],
    technologies: ['React', 'PostgreSQL'],
    project_background: '项目背景',
    project_responsibilities: [],
    project_outcomes: ['完成交付'],
    architecture_score: null,
    architecture_reason: null,
    credibility_score: null,
    credibility_reason: null,
    embellishment_risk_score: null,
    embellishment_risk_reason: null,
    overall_score: null,
    source_excerpt: null,
    source_path: 'resumes/b.pdf',
    extraction_model_name: 'test',
    ocr_completed_at: null,
    extracted_at: '2026-07-24T00:00:00Z',
  },
]

const templates: ResumeTemplateDefinition[] = [
  {
    key: 'local-template-01', name: '本地模板 01', description: '绶带分节', group: 'local',
    layout: 'local_01', header_style: 'banner', section_style: 'ribbon',
    density: 'compact', default_color: '#4F7180', variant: 1,
  },
  {
    key: 'local-template-02', name: '本地模板 02', description: '浅蓝通栏', group: 'local',
    layout: 'local_02', header_style: 'centered', section_style: 'band',
    density: 'compact', default_color: '#3C82B4', variant: 2,
  },
  {
    key: 'local-template-03', name: '本地模板 03', description: '蓝色页眉', group: 'local',
    layout: 'local_03', header_style: 'topbar', section_style: 'underline',
    density: 'compact', default_color: '#5576B6', variant: 3,
  },
  {
    key: 'local-template-04', name: '本地模板 04', description: '黑白极简', group: 'local',
    layout: 'local_04', header_style: 'minimal', section_style: 'line',
    density: 'compact', default_color: '#262626', variant: 4,
  },
  {
    key: 'local-template-05', name: '本地模板 05 · 技术履历优化',
    description: '项目技术优先', group: 'local', layout: 'local_05',
    header_style: 'resume_mark', section_style: 'tracked_ribbon',
    density: 'compact', default_color: '#465A73', variant: 5,
  },
]

describe('resume writer template and project materials', () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockImplementation(async (path) => {
      if (path === '/resume-writer/documents/document-1') return structuredClone(document)
      if (path === '/resume-projects') return structuredClone(projects)
      if (path === '/resume-writer/templates') return structuredClone(templates)
      throw new Error(`unexpected API path: ${path}`)
    })
  })

  it('uses another candidate project directly and edits technologies as horizontal tokens', async () => {
    const user = userEvent.setup()
    render(<ResumeWriterPanel session={session} documentId="document-1" onOpenDocument={vi.fn()} onBack={vi.fn()} />)

    await user.click(await screen.findByRole('button', { name: '项目经历' }))
    await user.click(screen.getByRole('button', { name: /从全部数据项目填充/ }))
    expect(screen.getByText('当前候选人项目')).toBeInTheDocument()
    const otherProject = screen.getByText('跨候选人项目').closest('article')
    expect(otherProject).not.toBeNull()
    expect(within(otherProject!).getByText('李*')).toBeInTheDocument()
    await user.click(within(otherProject!).getByRole('button', { name: /直接填充此项目/ }))
    await user.click(screen.getByRole('button', { name: '完成' }))

    expect(screen.getByDisplayValue('跨候选人项目')).toBeInTheDocument()
    expect(screen.getAllByText('React').length).toBeGreaterThan(0)
    await user.type(screen.getByLabelText('添加技术栈'), 'TypeScript{Enter}')
    expect(screen.getAllByText('TypeScript').length).toBeGreaterThan(0)
  })

  it('searches and switches templates from the library', async () => {
    const user = userEvent.setup()
    const { container } = render(<ResumeWriterPanel session={session} documentId="document-1" onOpenDocument={vi.fn()} onBack={vi.fn()} />)

    await user.click(await screen.findByRole('button', { name: /本地模板 05/ }))
    expect(screen.getByRole('heading', { name: '选择简历模板' })).toBeInTheDocument()
    expect(screen.getByText('全部 5 套 · 本地模板')).toBeInTheDocument()
    await user.type(screen.getByLabelText('搜索模板'), '蓝色页眉')
    await user.click(screen.getByRole('button', { name: /本地模板 03/ }))
    expect(container.querySelector('[data-template="local-template-03"]')).toBeInTheDocument()
    expect(screen.queryByText('经典简约')).not.toBeInTheDocument()
  })

  it('confirms and deletes a recent draft, then refreshes its source state', async () => {
    const user = userEvent.setup()
    let deleted = false
    vi.mocked(apiRequest).mockImplementation(async (path, options) => {
      if (path.startsWith('/resume-writer/sources')) {
        return [{
          id: 'profile-1',
          candidate_name: '张三',
          source_path: 'resumes/source.pdf',
          extracted_at: '2026-07-24T00:00:00Z',
          project_count: 1,
          draft_id: deleted ? null : document.id,
        }]
      }
      if (path === '/resume-writer/documents' && !options?.method) {
        return deleted ? [] : [structuredClone(document)]
      }
      if (path === '/resume-writer/documents/document-1' && options?.method === 'DELETE') {
        deleted = true
        return undefined
      }
      throw new Error(`unexpected API path: ${path}`)
    })

    render(<ResumeWriterPanel session={session} documentId={null} onOpenDocument={vi.fn()} onBack={vi.fn()} />)

    await user.click(await screen.findByRole('button', { name: '删除草稿 平台工程师简历' }))
    expect(screen.getByRole('heading', { name: '删除简历草稿？' })).toBeInTheDocument()
    expect(screen.getByText(/原始 OCR 简历和数据简历项目不会被删除/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '确认删除' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: '删除草稿 平台工程师简历' })).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: '基于此简历修改' })).toBeInTheDocument()
    expect(apiRequest).toHaveBeenCalledWith(
      '/resume-writer/documents/document-1',
      expect.objectContaining({ method: 'DELETE', token: session.access_token }),
    )
  })
})
