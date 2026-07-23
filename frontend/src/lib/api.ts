export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

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

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
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
    refreshInFlight = fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
      .then(async (response) => {
        const payload = await responsePayload(response)
        if (!response.ok) throw new ApiError(response.status, errorMessage(payload))
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

  const response = await fetchWithAuthRetry(path, {
    ...requestInit,
    body: body === undefined ? undefined : JSON.stringify(body),
    headers,
  }, token)

  const payload = await responsePayload(response)
  if (!response.ok) throw new ApiError(response.status, errorMessage(payload))
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
    throw new ApiError(response.status, errorMessage(payload))
  }
}

export async function apiDownload(path: string, token: string): Promise<Blob> {
  const response = await fetchWithAuthRetry(path, {}, token)
  if (!response.ok) {
    const payload = await responsePayload(response)
    throw new ApiError(response.status, errorMessage(payload))
  }
  return response.blob()
}

export type ModelProvider = {
  id: string
  name: string
  provider_type: 'local' | 'openai_compatible' | 'stepfun' | 'deepseek'
  model_kind: 'speech' | 'text'
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
  size_bytes: number
  chunk_size: number
  expected_chunks: number
  received_chunks: number
  status: string
  deduplicated: boolean
}

export type TranscriptionJob = {
  id: string
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
  max_attempts: number
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
  size_bytes: number
  sha256: string
  created_at: string
  job_count: number
  latest_job_id: string | null
  latest_job_status: string | null
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
