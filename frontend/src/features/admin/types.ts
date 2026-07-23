import type { TranscriptSegment, TranscriptionJob } from '@/lib/api'

export type AdminAuth = {
  access_token: string
  expires_at: string
  username: string
  password_change_required: boolean
}

export type AdminUser = {
  id: string
  tenant_id: string
  tenant_name: string
  tenant_slug: string
  email: string
  display_name: string
  status: 'active' | 'disabled'
  membership_status: string
  must_change_password: boolean
  created_at: string
}

export type AdminTenant = {
  id: string
  slug: string
  name: string
  status: 'active' | 'suspended'
  created_at: string
  users: AdminUser[]
}

export type AdminJob = TranscriptionJob & {
  tenant_id: string
  tenant_slug: string
  tenant_name: string
  created_by_email: string
  created_by_name: string
}

export type AdminJobDetail = AdminJob & {
  segments: TranscriptSegment[]
}

export type AdminRecording = {
  id: string
  tenant_id: string
  tenant_slug: string
  tenant_name: string
  tenant_status: 'active' | 'suspended' | 'deleted'
  original_name: string
  relative_path: string
  media_type: string | null
  size_bytes: number
  sha256: string | null
  created_at: string
  job_count: number
}

export type CredentialNotice = {
  organization: string
  login: string
  password: string
}

export type AdminView = 'overview' | 'organizations' | 'tasks' | 'recordings'
