// All calls to the backend go through here. In dev, Vite proxies these paths to :8000;
// in production the frontend and the API share an origin behind nginx.

export interface Readiness {
  status: 'ok' | 'degraded'
  model_api: 'live' | 'fixture' | 'record'
  data_dir_writable: boolean
  spend_usd: number
  spend_cap_usd: number
  paused: boolean
}

export interface Limits {
  max_photos: number
  max_upload_mb: number
}

export interface Version {
  name: string
  version: string
  models: Record<string, string>
  limits: Limits
}

export type Source = 'photo' | 'label_crop' | 'grounding_citation' | 'voice_note' | 'user_edit' | 'video_frame'

export interface Evidence {
  value: string
  unit: string
  confidence: number
  source: Source
  raw: string
}

export interface Extraction {
  item_type: string
  label_text: string
  fields: Record<string, Evidence>
  warnings: string[]
  photos: number
  crops: number
  model: string
  from_fixture: boolean
  cost_usd: number
}

export interface Box {
  left: number
  top: number
  right: number
  bottom: number
}

export interface Region {
  concept: string
  phrase: string
  object_id: string
  box: Box
  confidence: number | null
  coverage: number
  crop: string
  svg_path: string
}

export interface Segmentation {
  width: number
  height: number
  regions: Region[]
  overlay: string
  warnings: string[]
  model: string
  from_fixture: boolean
  cost_usd: number
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export const apiBase = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export function apiUrl(path: string): string {
  return `${apiBase}${path.startsWith('/') ? path : `/${path}`}`
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(apiUrl(path), { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new ApiError(res.status, `${path}: HTTP ${res.status}`)
  return (await res.json()) as T
}

// The backend answers errors as {"detail": "..."}; the text is written to be shown. A request
// the backend could not parse (422) carries one {loc, msg} per problem instead.
async function detailOf(res: Response, path: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map((problem) => (problem as { msg?: unknown }).msg)
        .filter((msg): msg is string => typeof msg === 'string')
      if (messages.length > 0) return messages.join('; ')
    }
  } catch {
    // not JSON: fall through to the generic message
  }
  return `${path}: HTTP ${res.status}`
}

export type FormPart = [field: string, value: File | string]

async function postForm<T>(path: string, parts: FormPart[]): Promise<T> {
  const form = new FormData()
  for (const [field, value] of parts) {
    if (typeof value === 'string') form.append(field, value)
    else form.append(field, value, value.name)
  }
  const res = await fetch(apiUrl(path), { method: 'POST', body: form, headers: { Accept: 'application/json' } })
  if (!res.ok) throw new ApiError(res.status, await detailOf(res, path))
  return (await res.json()) as T
}

// A data URL from the API back into a File the API can take as an upload.
export function dataUrlToFile(dataUrl: string, name: string): File {
  const comma = dataUrl.indexOf(',')
  const mime = /^data:([^;]+);base64$/.exec(dataUrl.slice(0, comma))?.[1] ?? 'application/octet-stream'
  const binary = atob(dataUrl.slice(comma + 1))
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new File([bytes], name, { type: mime })
}

export const api = {
  readiness: () => getJson<Readiness>('/readyz'),
  version: () => getJson<Version>('/api/version'),
  extract: (photos: File[], crops: File[] = []) =>
    postForm<Extraction>('/api/extract', [
      ...photos.map((p): FormPart => ['photos', p]),
      ...crops.map((c): FormPart => ['crops', c]),
    ]),
  segment: (photo: File, concepts: string[] = []) =>
    postForm<Segmentation>('/api/segment', [['photo', photo], ...concepts.map((c): FormPart => ['concepts', c])]),
}
