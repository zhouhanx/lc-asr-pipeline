import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ResumeDocument } from '@/lib/api'

import { ResumePreview } from './ResumePreview'

const document: ResumeDocument = {
  id: '00000000-0000-0000-0000-000000000001',
  source_resume_profile_id: null,
  source_path: null,
  title: '平台工程师简历',
  template_key: 'local-template-05',
  theme_color: '#465A73',
  has_photo: true,
  created_at: '2026-07-24T00:00:00Z',
  updated_at: '2026-07-24T00:00:00Z',
  content: {
    personal: {
      name: '张三',
      headline: '平台工程师',
      phone: '',
      email: 'person@example.com',
      location: '',
      website: '',
      summary: '关注可靠交付。',
    },
    education: [],
    work: [],
    projects: [
      {
        id: 'project-1',
        source_project_id: null,
        name: '语音平台',
        company: 'LC',
        role: '工程师',
        start_date: '2025',
        end_date: '至今',
        summary: '建设多租户平台。',
        highlights: ['实现租户隔离'],
        technologies: ['FastAPI', 'PostgreSQL'],
      },
    ],
    skills: ['Python'],
    certificates: [],
    self_evaluation: '',
    source_markdown: '',
  },
}

describe('resume preview', () => {
  it('renders selected template content and a private portrait URL', () => {
    render(<ResumePreview document={document} photoUrl="blob:tenant-photo" />)
    expect(screen.getByRole('heading', { name: '张三' })).toBeInTheDocument()
    expect(screen.getByText('语音平台')).toBeInTheDocument()
    expect(screen.getByText('FastAPI')).toBeInTheDocument()
    expect(screen.getByText('PostgreSQL')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '个人照片预览' })).toHaveAttribute(
      'src',
      'blob:tenant-photo',
    )
  })
})
