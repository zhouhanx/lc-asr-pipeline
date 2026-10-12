export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
export const CSRF_COOKIE_NAME = import.meta.env.VITE_AUTH_CSRF_COOKIE_NAME ?? 'lc_asr_csrf'
export const OPERATION_ID_HEADER = 'X-Operation-ID'

export type User = {
  id: string
  email: string
  display_name: string
  email_verified: boolean
}

export type Tenant = {
  id: string
  slug: string
  name: string
}

export type AuthPayload = {
  access_token: string
  token_type: 'bearer'
  expires_at: string
  user: User
  tenant: Tenant
  permissions: string[]
  password_change_required: boolean
}

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown
  token?: string
}

type AuthSessionListener = (payload: AuthPayload | null) => void

let authSessionListener: AuthSessionListener | null = null
let refreshInFlight: Promise<AuthPayload> | null = null

export function csrfTokenFromCookie(cookieValue = document.cookie): string | null {
  for (const part of cookieValue.split(';')) {
    const [name, ...valueParts] = part.trim().split('=')
    if (name === CSRF_COOKIE_NAME) return decodeURIComponent(valueParts.join('='))
  }
  return null
}

function addCsrfHeader(headers: Headers): void {
  const csrfToken = csrfTokenFromCookie()
  if (csrfToken) headers.set('X-CSRF-Token', csrfToken)
}

export class ApiError extends Error {
  readonly status: number
  readonly operationId: string | null

  constructor(status: number, message: string, operationId: string | null = null) {
    super(operationId ? `${message}（操作 ID：${operationId}）` : message)
    this.name = 'ApiError'
    this.status = status
    this.operationId = operationId
  }
}

function operationIdFromResponse(response: Response): string | null {
  const value = response.headers.get(OPERATION_ID_HEADER)?.trim()
  return value || null
}

function apiError(response: Response, payload: unknown): ApiError {
  return new ApiError(
    response.status,
    errorMessage(payload),
    operationIdFromResponse(response),
  )
}

function errorMessage(payload: unknown): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((entry) => {
          if (entry && typeof entry === 'object' && 'msg' in entry) {
            return String((entry as { msg: unknown }).msg)
          }
          return String(entry)
        })
        .join('；')
    }
  }
  return '请求失败，请稍后重试。'
}

async function responsePayload(response: Response): Promise<unknown> {
  return response.status === 204 ? null : response.json().catch(() => null)
}

export function setAuthSessionListener(listener: AuthSessionListener | null): () => void {
  authSessionListener = listener
  return () => {
    if (authSessionListener === listener) authSessionListener = null
  }
}

export function refreshAuthSession(): Promise<AuthPayload> {
  if (!refreshInFlight) {
    const headers = new Headers()
    addCsrfHeader(headers)
    refreshInFlight = fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers,
    })
      .then(async (response) => {
        const payload = await responsePayload(response)
        if (!response.ok) throw apiError(response, payload)
        return payload as AuthPayload
      })
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

async function fetchWithAuthRetry(
  path: string,
  init: RequestInit,
  token?: string,
): Promise<Response> {
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers,
  })
  if (response.status !== 401 || !token) return response

  try {
    const refreshed = await refreshAuthSession()
    authSessionListener?.(refreshed)
    headers.set('Authorization', `Bearer ${refreshed.access_token}`)
    return fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: 'include',
      headers,
    })
  } catch (error) {
    authSessionListener?.(null)
    throw error
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, token, ...requestInit } = options
  const headers = new Headers(options.headers)
  if (body !== undefined) headers.set('Content-Type', 'application/json')
  if (path === '/auth/logout' && options.method === 'POST') addCsrfHeader(headers)

  const response = await fetchWithAuthRetry(path, {
    ...requestInit,
    body: body === undefined ? undefined : JSON.stringify(body),
    headers,
  }, token)

  const payload = await responsePayload(response)
  if (!response.ok) throw apiError(response, payload)
  return payload as T
}

export async function apiBinaryRequest(
  path: string,
  body: Blob,
  token: string,
  headers: Record<string, string>,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetchWithAuthRetry(path, {
    method: 'PUT',
    body,
    headers,
    signal,
  }, token)
  if (!response.ok) {
    const payload = await responsePayload(response)
    throw apiError(response, payload)
  }
}

export async function apiDownload(path: string, token: string): Promise<Blob> {
  const response = await fetchWithAuthRetry(path, {}, token)
  if (!response.ok) {
    const payload = await responsePayload(response)
    throw apiError(response, payload)
  }
  return response.blob()
}

export type ModelProvider = {
  id: string
  name: string
  provider_type: 'local' | 'openai_compatible' | 'stepfun' | 'deepseek' | 'paddleocr'
  model_kind: 'speech' | 'text' | 'ocr'
  base_url: string
  model_name: string
  capabilities: string[]
  is_enabled: boolean
  is_default: boolean
  is_system: boolean
  has_api_key: boolean
}

export type UploadFileRecord = {
  id: string
  relative_path: string
  file_kind: 'audio' | 'image' | 'pdf'
  size_bytes: number
  chunk_size: number
  expected_chunks: number
  received_chunks: number
  status: string
  deduplicated: boolean
}

export type TranscriptionJob = {
  id: string
  task_id: string
  uploaded_file_id: string
  provider_id: string
  text_provider_id: string | null
  provider_name: string
  text_provider_name: string | null
  provider_deleted: boolean
  text_provider_deleted: boolean
  provider_type: string
  model_name: string
  text_model_name: string | null
  source_path: string
  status: string
  visibility: 'private' | 'public'
  language: string | null
  diarize: boolean
  speaker_mode: 'single' | 'double' | 'multiple'
  progress_percent: number
  attempts: number
  refinement_attempts: number
  max_attempts: number
  has_asr_checkpoint: boolean
  asr_completed_at: string | null
  queued_at: string
  started_at: string | null
  completed_at: string | null
  transcript_id: string | null
  transcript_text: string | null
  error_message: string | null
}

export type TranscriptSegment = {
  segment_index: number
  start_seconds: number
  end_seconds: number
  speaker: string | null
  text: string
}

export type TranscriptionJobDetail = TranscriptionJob & {
  segments: TranscriptSegment[]
}

export type PublicTranscriptionJob = TranscriptionJob & {
  tenant_slug: string
  tenant_name: string
}

export type PublicTranscriptionJobDetail = PublicTranscriptionJob & {
  segments: TranscriptSegment[]
}

export type HistoricalFile = {
  id: string
  original_name: string
  relative_path: string
  file_kind: 'audio' | 'image' | 'pdf'
  size_bytes: number
  sha256: string
  created_at: string
  job_count: number
  latest_job_id: string | null
  latest_job_status: string | null
}

export type OCRJob = {
  id: string
  task_id: string
  uploaded_file_id: string
  ocr_provider_id: string
  text_provider_id: string
  ocr_provider_name: string
  text_provider_name: string
  ocr_provider_deleted: boolean
  text_provider_deleted: boolean
  ocr_model_name: string
  text_model_name: string
  source_path: string
  document_kind: 'image' | 'pdf'
  file_attribute: 'resume' | 'document'
  status: string
  progress_percent: number
  attempts: number
  refinement_attempts: number
  max_attempts: number
  has_ocr_checkpoint: boolean
  ocr_completed_at: string | null
  queued_at: string
  started_at: string | null
  completed_at: string | null
  result_id: string | null
  markdown_text: string | null
  page_count: number
  error_message: string | null
}

export type OCRJobDetail = OCRJob & {
  raw_result: Record<string, unknown>
}

export type ResumeProject = {
  id: string
  resume_profile_id: string
  ocr_job_id: string
  uploaded_file_id: string
  candidate_name: string
  phone: string | null
  email: string | null
  project_index: number
  project_name: string
  company_name: string | null
  role_name: string | null
  start_date: string | null
  end_date: string | null
  is_current: boolean
  description: string | null
  responsibilities: string[]
  technologies: string[]
  project_background: string | null
  project_responsibilities: string[]
  project_outcomes: string[]
  architecture_score: number | null
  architecture_reason: string | null
  credibility_score: number | null
  credibility_reason: string | null
  embellishment_risk_score: number | null
  embellishment_risk_reason: string | null
  overall_score: number | null
  source_excerpt: string | null
  source_path: string
  extraction_model_name: string
  ocr_completed_at: string | null
  extracted_at: string
}

export type ResumeProjectSummary = {
  project_count: number
  candidate_count: number
  company_count: number
}

export type ResumeTemplateKey = string

export type ResumeTemplateDefinition = {
  key: ResumeTemplateKey
  name: string
  description: string
  group: 'local'
  layout: 'local_01' | 'local_02' | 'local_03' | 'local_04' | 'local_05'
  header_style: 'banner' | 'centered' | 'topbar' | 'minimal' | 'resume_mark'
  section_style: 'ribbon' | 'band' | 'underline' | 'line' | 'tracked_ribbon'
  density: 'compact' | 'comfortable'
  default_color: string
  variant: number
}

export type ResumePersonalInfo = {
  name: string
  headline: string
  phone: string
  email: string
  location: string
  website: string
  summary: string
}

export type ResumeEducationEntry = {
  id: string
  school: string
  degree: string
  major: string
  start_date: string
  end_date: string
  description: string
}

export type ResumeWorkEntry = {
  id: string
  company: string
  role: string
  start_date: string
  end_date: string
  highlights: string[]
}

export type ResumeProjectEntry = {
  id: string
  source_project_id: string | null
  name: string
  company: string
  role: string
  start_date: string
  end_date: string
  summary: string
  highlights: string[]
  technologies: string[]
}

export type ResumeContent = {
  personal: ResumePersonalInfo
  education: ResumeEducationEntry[]
  work: ResumeWorkEntry[]
  projects: ResumeProjectEntry[]
  skills: string[]
  certificates: string[]
  self_evaluation: string
  source_markdown: string
}

export type ResumeSource = {
  id: string
  candidate_name: string
  source_path: string
  extracted_at: string
  project_count: number
  draft_id: string | null
}

export type ResumeDocument = {
  id: string
  source_resume_profile_id: string | null
  source_path: string | null
  title: string
  template_key: ResumeTemplateKey
  theme_color: string
  content: ResumeContent
  has_photo: boolean
  created_at: string
  updated_at: string
}

export type WorkspaceSummary = {
  running_tasks: number
  queued_tasks: number
  completed_tasks: number
  available_models: number
  historical_files: number
}

export type UploadBatch = {
  id: string
  name: string
  total_bytes: number
  received_bytes: number
  file_count: number
  status: string
  created_at: string
  files: UploadFileRecord[]
}
