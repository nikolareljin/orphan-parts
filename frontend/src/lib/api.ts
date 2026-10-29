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

// Inventory: how a value is known, what the owner means to do, whether a plan may count on it.
export type Provenance = 'observed' | 'owner_reported' | 'documented' | 'tested' | 'estimated'
export type Intent = 'keep' | 'build' | 'sell' | 'give'
export type Availability = 'available' | 'reserved' | 'gone'
export type Review = 'proposed' | 'accepted' | 'rejected'

export interface Assertion {
  id: number
  field: string
  value: string
  unit: string
  provenance: Provenance
  confidence: number
  source: Source
  raw: string
  review: Review
  at: string
}

export interface ItemSummary {
  id: number
  name: string
  item_type: string
  condition: string
  intent: Intent
  availability: Availability
  parent_id: number | null
  field_count: number
  version: number
  updated_at: string
}

export interface Item extends ItemSummary {
  faults: string
  tests_done: string
  accessories: string
  location: string
  notes: string
  created_at: string
  fields: Record<string, Assertion>
  assertions: Assertion[]
  components: number[]
}

export type ItemDetails = Pick<
  Item,
  'name' | 'item_type' | 'condition' | 'faults' | 'tests_done' | 'accessories' | 'location' | 'notes' | 'intent' | 'availability'
>

export interface ItemCreate extends Partial<ItemDetails> {
  extraction?: Extraction
  parent_id?: number | null
}

export type ItemPatch = Partial<ItemDetails> & { version?: number }

export interface FieldCreate {
  field: string
  value: string
  unit?: string
  provenance?: Provenance
  raw?: string
}

export interface ComponentCreate {
  name: string
  item_type?: string
  condition?: string
  notes?: string
}

export interface ItemEvent {
  id: number
  item_id: number
  at: string
  actor: string
  change: string
  version: number
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

async function sendJson<T>(method: 'POST' | 'PATCH' | 'DELETE', path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(apiUrl(path), { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  if (!res.ok) throw new ApiError(res.status, await detailOf(res, path))
  if (res.status === 204) return undefined as T
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
  items: {
    list: () => getJson<ItemSummary[]>('/api/items'),
    get: (id: number) => getJson<Item>(`/api/items/${id}`),
    create: (spec: ItemCreate) => sendJson<Item>('POST', '/api/items', spec),
    update: (id: number, patch: ItemPatch) => sendJson<Item>('PATCH', `/api/items/${id}`, patch),
    remove: (id: number) => sendJson<void>('DELETE', `/api/items/${id}`),
    addField: (id: number, spec: FieldCreate) => sendJson<Item>('POST', `/api/items/${id}/fields`, spec),
    review: (id: number, assertionId: number, review: Review) =>
      sendJson<Item>('POST', `/api/items/${id}/assertions/${assertionId}/review`, { review }),
    addComponent: (id: number, spec: ComponentCreate) => sendJson<Item>('POST', `/api/items/${id}/components`, spec),
    events: (id: number) => getJson<ItemEvent[]>(`/api/items/${id}/events`),
  },
}
